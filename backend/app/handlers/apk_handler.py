#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APK analysis, decompile, recompile, and signing handlers.
"""

import base64
import os
import re
import zipfile

from app.tools.tool_manager import ToolManager
from app.common.base_executor import CommandExecutionContext
from app.common.task_manager import TaskManager
from app.common.exceptions import ToolNotFoundError, ToolException
from app.common.decorators import streaming, logs_errors
from app.utils.logger import Logger
from app.utils.env import get_output_dir, get_task_subdir
from app.utils.task_log_writer import append_task_log
from app.utils.file_utils import get_file_hash
from app.utils.apk_inspector import (
    enumerate_so_files,
    compare_so_across_arches,
    analyze_compression,
    check_16kb_page_support,
)

logger = Logger.get_logger("ApkHandler")
manager = ToolManager.instance()


def _extract_signature_hashes(apk_path: str) -> dict:
    """Extract certificate MD5, SHA-1, SHA-256 from APK using apksigner."""
    try:
        apksigner = manager.get_tool("apksigner")
        if not apksigner or not apksigner.is_valid:
            return {
                "sig_md5": "-", "sig_sha1": "-", "sig_sha256": "-",
                "sig_warning": "apksigner unavailable",
            }

        ctx = CommandExecutionContext(capture_output=True, log_output=False)
        result = apksigner.execute(["verify", "--print-certs", "--verbose", apk_path], ctx)

        if result.get("returncode", 1) != 0:
            return {
                "sig_md5": "-", "sig_sha1": "-", "sig_sha256": "-",
                "sig_warning": "unsigned or no certificate",
            }

        output = result.get("stdout", "") + result.get("stderr", "")

        md5_match = re.search(
            r"Signer #1 certificate MD5 digest:\s*([0-9a-fA-F:]+)", output
        )
        sha1_match = re.search(
            r"Signer #1 certificate SHA-1 digest:\s*([0-9a-fA-F:]+)", output
        )
        sha256_match = re.search(
            r"Signer #1 certificate SHA-256 digest:\s*([0-9a-fA-F:]+)", output
        )

        if not md5_match and not sha1_match and not sha256_match:
            return {
                "sig_md5": "-", "sig_sha1": "-", "sig_sha256": "-",
                "sig_warning": "unsigned or no certificate",
            }

        return {
            "sig_md5": md5_match.group(1).lower().replace(":", "") if md5_match else "-",
            "sig_sha1": sha1_match.group(1).lower().replace(":", "") if sha1_match else "-",
            "sig_sha256": sha256_match.group(1).lower().replace(":", "") if sha256_match else "-",
        }
    except Exception as e:
        logger.warning(f"Signature extraction failed: {e}")
        return {
            "sig_md5": "-", "sig_sha1": "-", "sig_sha256": "-",
            "sig_warning": f"Signature extraction failed: {e}",
        }


def _image_dimensions(data: bytes):
    """Best-effort intrinsic pixel size of a PNG/WebP, or None.

    Parsed straight from the file header (no external deps) so we can pick
    the genuinely largest launcher icon instead of trusting the density label.
    """
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        w = int.from_bytes(data[16:20], "big")
        h = int.from_bytes(data[20:24], "big")
        return w, h
    if len(data) >= 30 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        fmt = data[12:16]
        if fmt == b"VP8 ":
            w = int.from_bytes(data[26:28], "little") & 0x3FFF
            h = int.from_bytes(data[28:30], "little") & 0x3FFF
            return w, h
        if fmt == b"VP8X":
            w = int.from_bytes(data[24:27], "little") + 1
            h = int.from_bytes(data[27:30], "little") + 1
            return w, h
        # VP8L (lossless) is bit-packed; skip precise parse and fall back to density.
    return None


def _extract_app_icon(apk_path: str, badging_output: str, task_id: str = "") -> str:
    """Extract the launcher icon, preferring to persist it on disk.

    `aapt dump badging` reports candidate launcher icons as
    ``application-icon-NNN:'res/...'`` (NNN = density dpi). We prefer a
    raster asset (png/webp) — adaptive vector XML drawables
    (res/mipmap-anydpi-v26/*.xml) are skipped since they cannot be embedded
    directly — and among raster candidates pick the one with the largest
    intrinsic pixel area (read from the PNG/WebP header), falling back to
    density when dimensions can't be parsed.

    Output:
    * With a valid ``task_id`` the bytes are written to
      ``<BT_TASKS_DIR>/<task_id>/icon.<ext>`` and the **absolute file path**
      is returned. The renderer loads it via IPC, so the (potentially large)
      icon is never embedded as base64 in the persisted result HTML /
      localStorage.
    * Without a task_id (or if the file cannot be written) a ``data:`` URI is
      returned for backwards compatibility.
    * ``'-'`` is returned when no suitable icon is available.
    """
    icon_matches = re.findall(
        r"application-icon-(\d+):\s*'([^']+)'", badging_output
    )
    if not icon_matches:
        return "-"
    raster = [
        (int(d), p)
        for d, p in icon_matches
        if p.lower().endswith((".png", ".webp"))
    ]
    if not raster:
        return "-"
    # Pick the genuinely largest raster by intrinsic pixel area so the UI never
    # upscales a low-res asset. Reading every candidate is cheap (icons are
    # tiny) and beats trusting the density label (a lower-density PNG can be
    # physically larger than a higher-density one).
    best = None  # (score, path, data)
    try:
        with zipfile.ZipFile(apk_path) as zf:
            for d, p in raster:
                try:
                    data = zf.read(p)
                except Exception:
                    continue
                if not data:
                    continue
                dims = _image_dimensions(data)
                score = (dims[0] * dims[1]) if dims else int(d) * 1000
                if best is None or score > best[0]:
                    best = (score, p, data)
    except Exception:
        return "-"
    if best is None:
        return "-"
    icon_path = best[1]
    data = best[2]
    ext = "webp" if icon_path.lower().endswith(".webp") else "png"

    # Prefer writing to the task directory: the file is cleaned up together
    # with the task, and the (large) icon blob stays out of localStorage.
    if task_id:
        base = os.environ.get("BT_TASKS_DIR")
        if base:
            task_dir = os.path.join(base, str(task_id))
            try:
                os.makedirs(task_dir, exist_ok=True)
                out_path = os.path.join(task_dir, f"icon.{ext}")
                with open(out_path, "wb") as f:
                    f.write(data)
                return out_path
            except Exception:
                pass  # fall through to base64

    mime = "image/webp" if ext == "webp" else "image/png"
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


@streaming
@logs_errors("ApkHandler")
def apk_analyze(params, stream_handler):
    apk_path = params.get("apk_path")
    if not apk_path or not os.path.exists(apk_path):
        raise ToolException(f"APK path does not exist: {apk_path}")

    task_id = str(params.get("task_id", ""))
    task_manager = TaskManager()
    process_holder: dict = {}
    if task_id:
        task_manager.register(task_id, process_holder)

    try:
        aapt = manager.get_tool("aapt")
        if not aapt or not aapt.is_valid:
            raise ToolNotFoundError("aapt")

        context = CommandExecutionContext(stream=True, task_id=task_id, process_holder=process_holder)

        proc = aapt.execute(["dump", "badging", apk_path], context)
        output = ""
        for line in iter(proc.stdout.readline, ''):
            if task_id and task_manager.is_cancelled(task_id):
                proc.kill()
                stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
                return
            line = line.rstrip('\n')
            if line:
                if task_id:
                    append_task_log(task_id, line)
                stream_handler({"type": "log", "task_id": task_id, "line": line})
                output += line + "\n"
        proc.wait()

        if task_id and task_manager.is_cancelled(task_id):
            stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
            return

        if proc.returncode != 0:
            stream_handler({
                "type": "error",
                "payload": {"message": f"aapt dump badging failed (exit={proc.returncode})"},
            })
            return

        info = {}
        pkg_match = re.search(
            r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'",
            output,
        )
        if pkg_match:
            info["package_name"] = pkg_match.group(1)
            info["version_code"] = pkg_match.group(2)
            info["version_name"] = pkg_match.group(3)

        app_label = re.search(r"application-label:'([^']+)'", output)
        if app_label:
            info["application_label"] = app_label.group(1)

        sdk_match = re.search(r"minSdkVersion:'([^']+)'", output)
        if sdk_match:
            info["min_sdk_version"] = sdk_match.group(1)

        target_sdk = re.search(r"targetSdkVersion:'([^']+)'", output)
        if target_sdk:
            info["target_sdk_version"] = target_sdk.group(1)

        permissions = re.findall(
            r"uses-permission(?:-sdk-23)?: name='([^']+)'", output
        )
        info["permissions"] = permissions

        native_libs = re.findall(r"native-code:\s*(.+)", output)
        if native_libs:
            info["native_libs"] = [
                abi.strip("'") for abi in re.findall(r"'([^']+)'", native_libs[0])
            ]

        info["file_size"] = os.path.getsize(apk_path)

        # --- v2.1.1: deep APK analysis ---
        info["warnings"] = []

        # C0: Launcher icon — written to the task dir (path returned) so the
        # large image never lands in localStorage; falls back to base64.
        try:
            info["app_icon"] = _extract_app_icon(apk_path, output, task_id)
        except Exception as e:
            logger.warning(f"App icon extraction failed: {e}")
            info["app_icon"] = "-"

        # C1: SO file comparison across architectures
        stream_handler({"type": "log", "task_id": task_id, "line": "[SO Analysis] Starting..."})
        try:
            so_map = enumerate_so_files(apk_path)
            info["native_so_detail"] = so_map
            info["so_comparison"] = compare_so_across_arches(so_map)
        except Exception as e:
            logger.warning(f"SO analysis failed: {e}")
            info["warnings"].append(f"SO analysis failed: {e}")
            stream_handler({"type": "log", "task_id": task_id, "line": f"[SO Analysis] Failed: {e}"})

        # C2: Compression analysis (assets/lib/dex)
        stream_handler({"type": "log", "task_id": task_id, "line": "[Compression Analysis] Starting..."})
        try:
            info["compression_analysis"] = analyze_compression(apk_path)
        except Exception as e:
            logger.warning(f"Compression analysis failed: {e}")
            info["warnings"].append(f"Compression analysis failed: {e}")
            stream_handler({"type": "log", "task_id": task_id, "line": f"[Compression Analysis] Failed: {e}"})

        # C3: 16KB page size support for 64-bit .so files
        stream_handler({"type": "log", "task_id": task_id, "line": "[16KB Page Check] Starting..."})
        try:
            info["page_size_16kb"] = check_16kb_page_support(apk_path)
        except Exception as e:
            logger.warning(f"16KB page check failed: {e}")
            info["warnings"].append(f"16KB page check failed: {e}")
            stream_handler({"type": "log", "task_id": task_id, "line": f"[16KB Page Check] Failed: {e}"})

        # C4: Meta-data from AndroidManifest.xml
        stream_handler({"type": "log", "task_id": task_id, "line": "[Meta-data Extraction] Starting..."})
        try:
            info["meta_data"] = _parse_manifest_meta_data(apk_path, task_id=task_id)
            _resolve_resource_refs(apk_path, info["meta_data"], task_id=task_id)
        except Exception as e:
            logger.warning(f"Meta-data extraction failed: {e}")
            info["warnings"].append(f"Meta-data extraction failed: {e}")
            stream_handler({"type": "log", "task_id": task_id, "line": f"[Meta-data Extraction] Failed: {e}"})

        # C5: File hash and signature certificate extraction
        stream_handler({"type": "log", "task_id": task_id, "line": "[Signature] Extracting certs..."})
        try:
            info["file_md5"] = get_file_hash(apk_path, "md5") or "-"
        except Exception as e:
            logger.warning(f"File MD5 failed: {e}")
            info["file_md5"] = "-"
            info["warnings"].append(f"File MD5 failed: {e}")

        try:
            sig_info = _extract_signature_hashes(apk_path)
            info["sig_md5"] = sig_info.get("sig_md5", "-")
            info["sig_sha1"] = sig_info.get("sig_sha1", "-")
            info["sig_sha256"] = sig_info.get("sig_sha256", "-")
            if "sig_warning" in sig_info:
                info["warnings"].append(sig_info["sig_warning"])
            # Facebook Hash Key = base64( SHA1(cert DER) ).
            # apksigner's reported SHA-1 digest is computed over the DER-encoded
            # certificate, which is exactly what `keytool -exportcert | openssl
            # sha1 -binary | base64` produces. So we reuse the already-extracted
            # sig_sha1 (hex) and base64-encode its raw 20 bytes — no keystore
            # password or openssl/keytool needed.
            sha1_hex = info.get("sig_sha1", "-")
            if sha1_hex and sha1_hex != "-":
                try:
                    info["fb_hash_key"] = base64.b64encode(
                        bytes.fromhex(sha1_hex)
                    ).decode("ascii")
                except Exception:
                    info["fb_hash_key"] = "-"
            else:
                info["fb_hash_key"] = "-"
        except Exception as e:
            logger.warning(f"Signature extraction failed: {e}")
            info["sig_md5"] = "-"
            info["sig_sha1"] = "-"
            info["sig_sha256"] = "-"
            info["warnings"].append(f"Signature extraction failed: {e}")

        if task_id:
            append_task_log(task_id, f"[ANALYZE] package={info.get('package_name', '-')} version={info.get('version_name', '-')} (code={info.get('version_code', '-')})")
            append_task_log(task_id, f"[ANALYZE] app_label={info.get('application_label', '-')}")
            append_task_log(task_id, f"[ANALYZE] sdk: min={info.get('min_sdk_version', '-')} target={info.get('target_sdk_version', '-')}")
            append_task_log(task_id, f"[ANALYZE] file_md5={info.get('file_md5', '-')} size={info.get('file_size', 0)}")
            append_task_log(task_id, f"[ANALYZE] app_icon={'yes' if info.get('app_icon', '-') != '-' else 'no'}")
            append_task_log(task_id, f"[ANALYZE] sig_sha256={info.get('sig_sha256', '-')}")
            if info.get('fb_hash_key', '-') != '-':
                append_task_log(task_id, f"[ANALYZE] fb_hash_key={info.get('fb_hash_key', '-')}")
            append_task_log(task_id, f"[ANALYZE] permissions={len(info.get('permissions', []))}")
            if info.get('native_libs'):
                append_task_log(task_id, f"[ANALYZE] native_abis={info['native_libs']}")
            if info.get('warnings'):
                for w in info['warnings']:
                    append_task_log(task_id, f"[ANALYZE] warning: {w}")
        stream_handler({"type": "complete", "payload": info})
    except ToolException as e:
        logger.error(f"APK analysis tool error: {e}")
        stream_handler({"type": "error", "payload": {"message": str(e)}})
    except Exception as e:
        if task_id and task_manager.is_cancelled(task_id):
            stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
        else:
            logger.error(f"APK analysis failed: {e}")
            stream_handler({"type": "error", "payload": {"message": str(e)}})
    finally:
        if task_id:
            task_manager.unregister(task_id)


@streaming
@logs_errors("ApkHandler")
def apk_decompile(params, stream_handler):
    file_path = params.get("file_path")
    options = params.get("options", {})
    task_id = str(options.get("task_id", ""))
    if not file_path or not os.path.exists(file_path):
        raise ToolException("APK file does not exist")

    if not options.get("output_dir"):
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        if task_id:
            output_dir = os.path.join(get_task_subdir(task_id, "output"), "decompiled", base_name)
        else:
            output_dir = os.path.join(get_output_dir(), "decompiled", base_name)
    else:
        output_dir = options.get("output_dir")

    task_manager = TaskManager()
    process_holder: dict = {}
    if task_id:
        task_manager.register(task_id, process_holder, cleanup_paths=[output_dir])

    try:
        apktool = manager.get_tool("apktool")
        if not apktool or not apktool.is_valid:
            raise ToolNotFoundError("apktool")

        context = CommandExecutionContext(
            cwd=options.get("cwd"), timeout=600,
            stream=True,
            task_id=task_id,
            process_holder=process_holder,
        )
        proc = apktool.execute(
            ["d", file_path, "-f", "-o", output_dir], context
        )

        for line in iter(proc.stdout.readline, ''):
            if task_id and task_manager.is_cancelled(task_id):
                proc.kill()
                stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
                return
            line = line.rstrip('\n')
            if line:
                if task_id:
                    append_task_log(task_id, line)
                stream_handler({"type": "log", "task_id": task_id, "line": line})

        proc.wait()

        if task_id and task_manager.is_cancelled(task_id):
            stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
            return

        if proc.returncode != 0:
            stream_handler({
                "type": "error",
                "payload": {"message": f"Decompile failed (exit={proc.returncode})"},
            })
            return

        if task_id:
            append_task_log(task_id, f"[DECOMPILE] output_dir: {output_dir}")
        stream_handler({"type": "complete", "payload": {"output_dir": output_dir}})
    finally:
        if task_id:
            task_manager.unregister(task_id)


@streaming
@logs_errors("ApkHandler")
def apk_recompile(params, stream_handler):
    project_path = params.get("project_path")
    options = params.get("options", {})
    task_id = str(options.get("task_id", ""))
    if not project_path or not os.path.exists(project_path):
        raise ToolException("Project path does not exist")

    if not options.get("output_apk"):
        base_name = os.path.basename(project_path)
        if task_id:
            output_dir = get_task_subdir(task_id, "output")
            output_apk = os.path.join(output_dir, "recompiled", f"{base_name}.apk")
        else:
            output_apk = os.path.join(
                get_output_dir(), "recompiled", f"{base_name}.apk"
            )
        os.makedirs(os.path.dirname(output_apk), exist_ok=True)
    else:
        output_apk = options.get("output_apk")

    task_manager = TaskManager()
    process_holder: dict = {}
    if task_id:
        task_manager.register(task_id, process_holder, cleanup_paths=[output_apk])

    def _ctx():
        """Build a context that captures the process for cancellation."""
        return CommandExecutionContext(
            cwd=options.get("cwd"),
            stream=True,
            task_id=task_id,
            process_holder=process_holder,
        )

    try:
        apktool = manager.get_tool("apktool")
        if not apktool or not apktool.is_valid:
            raise ToolNotFoundError("apktool")

        proc = apktool.execute(
            ["b", project_path, "-o", output_apk], _ctx()
        )
        for line in iter(proc.stdout.readline, ''):
            if task_id and task_manager.is_cancelled(task_id):
                proc.kill()
                stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
                return
            line = line.rstrip('\n')
            if line:
                if task_id:
                    append_task_log(task_id, line)
                stream_handler({"type": "log", "task_id": task_id, "line": line})

        proc.wait()

        if task_id and task_manager.is_cancelled(task_id):
            stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
            return
        if proc.returncode != 0:
            stream_handler({
                "type": "error",
                "payload": {"message": f"Recompile failed (exit={proc.returncode})"},
            })
            return

        warnings = []
        if options.get("zipalign"):
            zipalign = manager.get_tool("zipalign")
            if zipalign and zipalign.is_valid:
                aligned_apk = output_apk.replace(".apk", "-aligned.apk")
                zproc = zipalign.execute(
                    ["-f", "4", output_apk, aligned_apk],
                    _ctx(),
                )
                for line in iter(zproc.stdout.readline, ''):
                    if task_id and task_manager.is_cancelled(task_id):
                        zproc.kill()
                        stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
                        return
                    line = line.rstrip('\n')
                    if line:
                        if task_id:
                            append_task_log(task_id, line)
                        stream_handler({"type": "log", "task_id": task_id, "line": line})

                zproc.wait()

                if task_id and task_manager.is_cancelled(task_id):
                    stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
                    return
                if zproc.returncode == 0:
                    output_apk = aligned_apk
                else:
                    msg = f"zipalign failed (exit={zproc.returncode}); using unaligned apk"
                    logger.warning(msg)
                    if task_id:
                        append_task_log(task_id, f"[WARNING] {msg}")
                    warnings.append(msg)

        if options.get("sign") and options.get("keystore"):
            keystore = options.get("keystore", {})
            apksigner = manager.get_tool("apksigner")
            if apksigner and apksigner.is_valid:
                args = [
                    "sign",
                    "--ks", keystore.get("path", ""),
                    "--ks-key-alias", keystore.get("alias", ""),
                    "--ks-pass", f"pass:{keystore.get('storepass', '')}",
                ]
                if keystore.get("keypass"):
                    args += [
                        "--key-pass",
                        f"pass:{keystore.get('keypass', '')}",
                    ]
                if options.get("v2") is False:
                    args += ["--v2-signing-enabled", "false"]
                args += [output_apk]
                sproc = apksigner.execute(args, _ctx())
                for line in iter(sproc.stdout.readline, ''):
                    if task_id and task_manager.is_cancelled(task_id):
                        sproc.kill()
                        stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
                        return
                    line = line.rstrip('\n')
                    if line:
                        if task_id:
                            append_task_log(task_id, line)
                        stream_handler({"type": "log", "task_id": task_id, "line": line})

                sproc.wait()

                if task_id and task_manager.is_cancelled(task_id):
                    stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
                    return
                if sproc.returncode != 0:
                    stream_handler({
                        "type": "error",
                        "payload": {"message": f"Signing failed (exit={sproc.returncode})"},
                    })
                    return

        if task_id:
            append_task_log(task_id, f"[RECOMPILE] output_apk: {output_apk}")
        payload = {"output_apk": output_apk}
        if warnings:
            payload["warnings"] = warnings
        stream_handler({"type": "complete", "payload": payload})
    finally:
        if task_id:
            task_manager.unregister(task_id)


def _get_task_id(params: dict) -> str:
    """Extract task_id from params, checking both options and keystore."""
    options = params.get("options", {}) or {}
    keystore = params.get("keystore", {}) or {}
    return str(options.get("task_id") or keystore.get("task_id", ""))


def _parse_manifest_meta_data(apk_path, task_id: str = ""):
    """
    Extract all <meta-data> entries from AndroidManifest.xml using aapt dump xmltree.
    Returns a list of dicts: [{parent, name, value}, ...]
    Groups metadata by parent element (application, activity, service, receiver, provider).
    """
    try:
        aapt = manager.get_tool("aapt")
        if not aapt or not aapt.is_valid:
            return []
        context = CommandExecutionContext(task_id=task_id, log_output=False)
        result = aapt.execute(["dump", "xmltree", "--file", "AndroidManifest.xml", apk_path], context)
        output = result.get("stdout", "")
        lines = output.split("\n")

        meta_list = []
        # Use indent-based stack to properly track parent scope
        # Format: indent 6=E:manifest, 8=E:application, 10=E:activity/meta-data/etc
        stack = [("manifest", 0)]
        in_meta = False
        meta_name = ""
        meta_value = ""
        meta_resource = ""

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            indent = len(line) - len(line.lstrip())

            if stripped.startswith("E: meta-data"):
                # Flush previous entry before starting new one
                if in_meta:
                    parent = stack[-1][0] if stack else "unknown"
                    meta_list.append({
                        "parent": parent,
                        "name": meta_name,
                        "value": meta_value,
                        "resource_ref": meta_resource if meta_resource else None
                    })
                in_meta = True
                meta_name = ""
                meta_value = ""
                meta_resource = ""
            elif stripped.startswith("E:"):
                # Pop stack until we're at the right depth (going back up)
                while stack and stack[-1][1] >= indent:
                    stack.pop()
                elem_name = stripped.split(" ")[1].split("(")[0].strip()
                stack.append((elem_name, indent))
                # Flush any pending meta-data before switching context
                if in_meta:
                    parent = stack[-2][0] if len(stack) >= 2 else stack[-1][0]
                    meta_list.append({
                        "parent": parent,
                        "name": meta_name,
                        "value": meta_value,
                        "resource_ref": meta_resource if meta_resource else None
                    })
                    in_meta = False
            elif in_meta and "android:name" in stripped:
                m = re.search(r'Raw: \"([^\"]*)\"', line)
                if m:
                    meta_name = m.group(1)
            elif in_meta and "android:value" in stripped:
                m = re.search(r'Raw: \"([^\"]*)\"', line)
                if m:
                    meta_value = m.group(1)
                else:
                    # Try numeric value (e.g. android:value=2.2) or empty string
                    m2 = re.search(r'android:value[^=]*=([^\s]+)', line)
                    if m2:
                        raw_val = m2.group(1)
                        meta_value = raw_val if raw_val != '""' else ""
            elif in_meta and "android:resource" in stripped:
                m = re.search(r'@(0x[0-9a-fA-F]+)', line)
                if m:
                    meta_resource = m.group(1)

        # Flush last entry
        if in_meta:
            parent = stack[-1][0] if stack else "unknown"
            meta_list.append({
                "parent": parent,
                "name": meta_name,
                "value": meta_value,
                "resource_ref": meta_resource if meta_resource else None
            })

        # Filter out entries with no name
        return [m for m in meta_list if m["name"]]
    except Exception as e:
        logger.warning(f"Meta-data parsing failed: {e}")
        return []


def _resolve_resource_refs(apk_path, meta_list, task_id: str = ""):
    """
    Resolve android:resource=@0xNNNNNNNN references to human-readable paths
    using aapt2 dump resources, then read actual XML content for xml/ resources.
    Mutates meta_list in-place, adding 'resource_resolved' and optionally
    'resource_content' to each entry that has a resource_ref.
    """
    if not meta_list:
        return
    # Collect unique resource refs (both android:resource and android:value @0x refs)
    refs = set()
    value_ref_map = {}  # entry index -> ref from android:value
    for i, m in enumerate(meta_list):
        if m.get("resource_ref"):
            refs.add(m["resource_ref"])
        # Also resolve android:value references like @0x7f0a00e7 (string/integer refs)
        val = m.get("value", "")
        if val and re.match(r'^@(0x[0-9a-fA-F]+)$', val):
            value_ref_map[i] = val[1:]  # strip @ prefix
            refs.add(value_ref_map[i])
    if not refs:
        return

    try:
        aapt = manager.get_tool("aapt")
        if not aapt or not aapt.is_valid:
            return
        context = CommandExecutionContext(task_id=task_id, log_output=False)
        result = aapt.execute(["dump", "resources", apk_path], context)
        output = result.get("stdout", "")
        lines = output.split("\n")

        # Build lookup for ONLY the refs we need: id -> {path, type, value}
        # aapt2 dump resources format:
        #   resource 0x7f0a0000 string/app_name
        #     () "My App"              ← value for string (next line)
        #   resource 0x7f0f0004 integer/google_play_services_version
        #     () 12451000              ← value for integer (next line)
        lookup = {}
        for i, line in enumerate(lines):
            m = re.search(r'resource (0x[0-9a-fA-F]+)\s+(\S+)', line)
            if m and m.group(1) in refs:
                rid = m.group(1)
                rpath = m.group(2)
                rtype = rpath.split("/")[0] if "/" in rpath else rpath
                rvalue = None
                # Check next line for scalar value (string/integer/bool)
                if i + 1 < len(lines):
                    nxt = lines[i + 1].strip()
                    ms = re.search(r'^\(\)\s*"([^"]*)"', nxt)
                    mi = re.search(r'^\(\)\s*(-?\d+)', nxt)
                    mb = re.search(r'^\(\)\s*(true|false)', nxt, re.I)
                    if ms:
                        rvalue = ms.group(1)
                    elif mi:
                        rvalue = mi.group(1)
                    elif mb:
                        rvalue = mb.group(1)
                lookup[rid] = {"path": rpath, "type": rtype, "value": rvalue}

        # Step 1: Resolve all refs — set resource_resolved (path) + resource_value (scalar)
        for i, m in enumerate(meta_list):
            ref = m.get("resource_ref") or value_ref_map.get(i)
            if ref and ref in lookup:
                entry = lookup[ref]
                m["resource_resolved"] = entry["path"]
                if entry.get("value") is not None:
                    m["resource_value"] = entry["value"]

        # Step 2: For xml/ resources, read actual content via aapt2 dump xmltree
        for m in meta_list:
            rpath = m.get("resource_resolved")
            if not rpath:
                continue
            rtype = rpath.split("/")[0] if "/" in rpath else rpath
            if rtype not in ("xml", "layout"):
                continue  # string/integer already resolved via resource_value

            xml_file = f"res/{rpath}.xml"
            try:
                r2 = aapt.execute(["dump", "xmltree", "--file", xml_file, apk_path], context)
                xml_out = r2.get("stdout", "")

                # Parse structured content: element + name + value from xmltree output
                # Format:
                # E: resources
                #     E: paths
                #         E: external-path
                #           A: name="camera_photos" (Raw: "camera_photos")
                #           A: path="." (Raw: ".")
                items = []
                current_elem = ""
                current_attrs = {}  # attribute name -> value

                for xline in xml_out.split("\n"):
                    xs = xline.strip()
                    if xs.startswith("E:"):
                        # Flush previous element
                        if current_elem and current_attrs:
                            items.append({
                                "element": current_elem,
                                "name": current_attrs.get("name", ""),
                                "value": current_attrs.get("path", current_attrs.get("value", ""))
                            })
                        current_elem = xs.split(" ")[1].split("(")[0].strip()
                        current_attrs = {}
                    elif "A: " in xs and current_elem and "android:" not in xs:
                        m_attr = re.search(r'A:\s+(\S+)="([^"]*)"', xs)
                        if m_attr:
                            current_attrs[m_attr.group(1)] = m_attr.group(2)

                # Flush last element
                if current_elem and current_attrs:
                    items.append({
                        "element": current_elem,
                        "name": current_attrs.get("name", ""),
                        "value": current_attrs.get("path", current_attrs.get("value", ""))
                    })

                if items:
                    m["resource_content"] = items
            except Exception:
                pass  # Non-critical: content is best-effort

    except Exception as e:
        logger.warning(f"Resource ref resolution failed: {e}")


@streaming
@logs_errors("ApkHandler")
def apk_sign(params, stream_handler):
    apk_path = params.get("apk_path")
    keystore = params.get("keystore", {})
    options = params.get("options", {})
    task_id = _get_task_id(params)
    if not apk_path or not os.path.exists(apk_path):
        raise ToolException("APK path does not exist")
    if not keystore.get("path") or not keystore.get("alias"):
        raise ToolException("Missing keystore info for signing")

    base_name = os.path.basename(apk_path)
    name_without_ext = os.path.splitext(base_name)[0]
    if task_id:
        dir_name = get_task_subdir(task_id, "output")
    else:
        dir_name = os.path.dirname(apk_path)
    if name_without_ext.endswith("-signed"):
        output_apk = os.path.join(dir_name, f"{name_without_ext}_new.apk")
    else:
        output_apk = os.path.join(
            dir_name, f"{name_without_ext}-signed.apk"
        )

    task_manager = TaskManager()
    process_holder: dict = {}
    if task_id:
        task_manager.register(task_id, process_holder, cleanup_paths=[output_apk])

    try:
        apksigner = manager.get_tool("apksigner")
        if not apksigner or not apksigner.is_valid:
            raise ToolNotFoundError("apksigner")

        args = [
            "sign",
            "--ks", keystore.get("path", ""),
            "--ks-key-alias", keystore.get("alias", ""),
            "--ks-pass", f"pass:{keystore.get('storepass', '')}",
        ]
        if keystore.get("keypass"):
            args += ["--key-pass", f"pass:{keystore.get('keypass', '')}"]
        if options.get("v2") is False:
            args += ["--v2-signing-enabled", "false"]
        if options.get("v3") is False:
            args += ["--v3-signing-enabled", "false"]

        args += ["--out", output_apk]
        args += [apk_path]

        context = CommandExecutionContext(
            stream=True,
            task_id=task_id,
            process_holder=process_holder,
        )
        proc = apksigner.execute(args, context)

        for line in iter(proc.stdout.readline, ''):
            if task_id and task_manager.is_cancelled(task_id):
                proc.kill()
                stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
                return
            line = line.rstrip('\n')
            if line:
                if task_id:
                    append_task_log(task_id, line)
                stream_handler({"type": "log", "task_id": task_id, "line": line})

        proc.wait()

        if task_id and task_manager.is_cancelled(task_id):
            stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
            return

        if proc.returncode != 0:
            stream_handler({
                "type": "error",
                "payload": {"message": f"Signing failed (exit={proc.returncode})"},
            })
            return

        if task_id:
            append_task_log(task_id, f"[SIGN] output: {output_apk}")
        stream_handler({"type": "complete", "payload": {"apk_path": output_apk}})
    finally:
        if task_id:
            task_manager.unregister(task_id)


@streaming
def apk_getinfo(params, stream_handler):
    return apk_analyze(params, stream_handler)


@logs_errors("ApkHandler")
def apk_get_progress(params, stream_handler):
    task_id = params.get("task_id")
    output_dir = params.get("output_dir")
    output_apk = params.get("output_apk")
    progress = 0
    if output_dir and os.path.exists(output_dir):
        progress = 100
    if output_apk and os.path.exists(output_apk):
        progress = 100
    return {"task_id": task_id, "progress": progress}


def apk_cancel_task(params, stream_handler):
    task_id = str(params.get("task_id", ""))
    logger.info(f"CANCEL received for task_id={task_id}")
    if not task_id:
        return {"type": "error", "payload": {"message": "Missing task_id"}}
    cancelled = TaskManager().cancel(task_id)
    logger.info(f"CANCEL result for task_id={task_id}: cancelled={cancelled}")
    if cancelled:
        return {"cancelled": True, "task_id": task_id}
    return {"cancelled": False, "task_id": task_id, "message": "Task not found or already completed"}


API_MAP = {
    "apk.analyze": apk_analyze,
    "apk.analyze_apk": apk_analyze,
    "apk.getInfo": apk_getinfo,
    "apk.decompile": apk_decompile,
    "apk.recompile": apk_recompile,
    "apk.sign": apk_sign,
    "apk.get_progress": apk_get_progress,
    "apk.getProgress": apk_get_progress,
    "apk.cancel_task": apk_cancel_task,
    "apk.cancelTask": apk_cancel_task,
}
