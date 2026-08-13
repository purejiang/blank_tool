#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APK Audit Tool — batch audit and compare APK files.

Usage:
    python apk_audit.py <apk_paths> <output_dir>

    apk_paths:  comma-separated APK file paths, or a directory containing .apk files
    output_dir: directory for report output (HTML + Markdown)

The script finds Java and apktool.jar automatically, decompiles each APK
to a temporary directory, extracts key information, cleans up, then
generates HTML and Markdown comparison reports and prints a JSON summary
to stdout.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from html import escape
from pathlib import Path

# AndroidManifest.xml namespace
ANDROID_NS = "http://schemas.android.com/apk/res/android"


# ── Binary discovery ──────────────────────────────────────────────────

def find_java():
    """Locate the Java runtime binary."""
    java_bin = os.environ.get("BT_JAVA_BIN", "")
    if java_bin and os.path.isfile(java_bin):
        return java_bin
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home:
        exe = "java.exe" if sys.platform == "win32" else "java"
        candidate = os.path.join(java_home, "bin", exe)
        if os.path.isfile(candidate):
            return candidate
    try:
        r = subprocess.run(["java", "-version"], capture_output=True)
        if r.returncode == 0:
            return "java"
    except FileNotFoundError:
        pass
    return None


def find_apktool_jar():
    """Locate apktool.jar by scanning common locations."""
    candidates = []
    runtime_dir = os.environ.get("BT_RUNTIME_DIR", "")
    if runtime_dir:
        candidates.append(os.path.join(runtime_dir, "apktool", "apktool.jar"))
    # Walk up from CWD looking for runtime/apktool/apktool.jar
    cwd = os.getcwd()
    for _ in range(5):
        candidates.append(os.path.join(cwd, "runtime", "apktool", "apktool.jar"))
        parent = os.path.dirname(cwd)
        if parent == cwd:
            break
        cwd = parent
    candidates.append("apktool.jar")
    for c in candidates:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    return None


# ── File parsers ──────────────────────────────────────────────────────

def parse_properties(filepath):
    """Parse a .properties file into a dict."""
    props = {}
    if not os.path.isfile(filepath):
        return props
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                props[key.strip()] = value.strip()
    return props


def parse_manifest(manifest_path):
    """Parse decompiled AndroidManifest.xml (plain XML)."""
    info = {}
    if not os.path.isfile(manifest_path):
        return info
    try:
        tree = ET.parse(manifest_path)
        root = tree.getroot()
    except ET.ParseError as exc:
        return {"parse_error": str(exc)}

    def attr(name):
        return root.get(f"{{{ANDROID_NS}}}{name}", "") or root.get(name, "")

    info["package"] = root.get("package", "")
    info["version_code"] = attr("versionCode")
    info["version_name"] = attr("versionName")
    info["compile_sdk"] = attr("compileSdkVersion")
    info["min_sdk"] = attr("minSdkVersion")
    info["target_sdk"] = attr("targetSdkVersion")

    # Meta-data entries
    for md in root.findall(".//meta-data"):
        name = md.get(f"{{{ANDROID_NS}}}name", "") or md.get("name", "")
        value = md.get(f"{{{ANDROID_NS}}}value", "") or md.get("value", "")
        if not name:
            continue
        lower = name.lower()
        if "google_client_id" in lower or "google_clientid" in lower:
            info["google_client_id"] = value
        if "channel_adver" in lower:
            info["channel_adver_meta"] = value

    # Permissions
    permissions = []
    for perm in root.findall(".//uses-permission"):
        name = perm.get(f"{{{ANDROID_NS}}}name", "") or perm.get("name", "")
        if name:
            permissions.append(name)
    info["permissions"] = sorted(permissions)

    # Component counts
    info["activities_count"] = len(root.findall(".//activity"))
    info["services_count"] = len(root.findall(".//service"))
    info["receivers_count"] = len(root.findall(".//receiver"))
    info["providers_count"] = len(root.findall(".//provider"))

    return info


def parse_strings_xml(strings_path):
    """Parse res/values/strings.xml into a name→value dict."""
    strings = {}
    if not os.path.isfile(strings_path):
        return strings
    try:
        tree = ET.parse(strings_path)
        root = tree.getroot()
        for s in root.findall("string"):
            name = s.get("name", "")
            if name:
                strings[name] = s.text or ""
    except ET.ParseError:
        pass
    return strings


def parse_apktool_yml(yml_path):
    """Parse apktool.yml (simplified key: value extraction)."""
    info = {}
    if not os.path.isfile(yml_path):
        return info
    with open(yml_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key in ("apkFileName", "isFrameworkApk", "sdkInfo",
                           "packageInfo", "version", "versionInfo"):
                    info[key] = value
    return info


# ── Single-APK audit ──────────────────────────────────────────────────

def audit_apk(apk_path, temp_base, java_bin, apktool_jar):
    """Decompile and audit a single APK. Returns a findings dict."""
    apk_name = os.path.basename(apk_path)
    apk_size = os.path.getsize(apk_path) if os.path.isfile(apk_path) else 0
    result = {
        "apk_path": os.path.abspath(apk_path),
        "apk_name": apk_name,
        "apk_size": apk_size,
        "status": "ok",
        "errors": [],
    }

    # Decompile
    stem = Path(apk_path).stem
    decompile_dir = os.path.join(temp_base, stem)
    if os.path.exists(decompile_dir):
        shutil.rmtree(decompile_dir, ignore_errors=True)

    cmd = [java_bin, "-jar", apktool_jar, "d", "-f",
           "-o", decompile_dir, apk_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        result["status"] = "error"
        result["errors"].append(
            f"apktool decode failed (exit {proc.returncode}): "
            f"{(proc.stderr or proc.stdout)[:500]}"
        )
        return result

    # channel_adver.properties
    for rel in ("channel_adver.properties", "assets/channel_adver.properties"):
        props_path = os.path.join(decompile_dir, *rel.split("/"))
        props = parse_properties(props_path)
        if props:
            result["channel_adver"] = props.get(
                "channel_adver", props.get("adver", ""))
            result["properties"] = props
            break

    # AndroidManifest.xml
    manifest = parse_manifest(
        os.path.join(decompile_dir, "AndroidManifest.xml"))
    result["manifest"] = manifest

    # strings.xml → app_name
    strings = parse_strings_xml(
        os.path.join(decompile_dir, "res", "values", "strings.xml"))
    result["strings_count"] = len(strings)
    raw_app_name = strings.get("app_name", "")
    result["app_name"] = raw_app_name
    if raw_app_name.startswith("@string/"):
        key = raw_app_name[8:]
        result["app_name_resolved"] = strings.get(key, raw_app_name)
    else:
        result["app_name_resolved"] = raw_app_name

    # apktool.yml
    result["apktool_info"] = parse_apktool_yml(
        os.path.join(decompile_dir, "apktool.yml"))

    # Cleanup
    shutil.rmtree(decompile_dir, ignore_errors=True)
    return result


# ── Comparison fields ─────────────────────────────────────────────────

# (display_label, dot_path_or_None_for_special)
COMPARISON_FIELDS = [
    ("Package",               ("manifest", "package")),
    ("Version Name",           ("manifest", "version_name")),
    ("Version Code",           ("manifest", "version_code")),
    ("App Name (resolved)",    ("app_name_resolved",)),
    ("Channel Adver",          ("channel_adver",)),
    ("Google Client ID",       ("manifest", "google_client_id")),
    ("Min SDK",                ("manifest", "min_sdk")),
    ("Target SDK",             ("manifest", "target_sdk")),
    ("Compile SDK",            ("manifest", "compile_sdk")),
    ("Activities",             ("manifest", "activities_count")),
    ("Services",               ("manifest", "services_count")),
    ("Receivers",              ("manifest", "receivers_count")),
    ("Providers",              ("manifest", "providers_count")),
    ("Permissions Count",      None),
    ("File Size",              None),
    ("Status",                 ("status",)),
]


def get_field(result, label, path):
    """Extract a comparison field value from a result dict."""
    if path is None:
        if label == "Permissions Count":
            perms = result.get("manifest", {}).get("permissions", [])
            return str(len(perms))
        if label == "File Size":
            return f"{result.get('apk_size', 0):,} bytes"
        return "-"
    val = result
    for p in path:
        val = val.get(p, "") if isinstance(val, dict) else ""
    return str(val) if val != "" else "-"


def compute_differences(results):
    """Return list of (label, values) tuples where values differ across APKs."""
    diffs = []
    if len(results) < 2:
        return diffs
    for label, path in COMPARISON_FIELDS:
        values = [get_field(r, label, path) for r in results]
        if len(set(values)) > 1:
            diffs.append((label, values))
    # Permission set differences
    perm_sets = []
    for r in results:
        perms = set(r.get("manifest", {}).get("permissions", []))
        perm_sets.append(perms)
    if len(perm_sets) > 1:
        all_perms = set().union(*perm_sets)
        only_in = {}
        for i, r in enumerate(results):
            extra = perm_sets[i] - set().union(*(perm_sets[:i] + perm_sets[i+1:]))
            if extra:
                only_in[r["apk_name"]] = sorted(extra)
        if only_in:
            diffs.append(("__permissions_diff__", only_in))
    return diffs


# ── Markdown report ───────────────────────────────────────────────────

def generate_markdown(results, output_path):
    """Generate a Markdown comparison report."""
    lines = ["# APK Audit Report\n"]
    lines.append(f"- **Total APKs:** {len(results)}")
    lines.append(f"- **OK:** {sum(1 for r in results if r['status'] == 'ok')}")
    lines.append(f"- **Errors:** {sum(1 for r in results if r['status'] == 'error')}")
    lines.append("")

    # Comparison table
    lines.append("## Comparison\n")
    header = "| Field | " + " | ".join(r["apk_name"] for r in results) + " |"
    sep = "|---|" + "|".join("---" for _ in results) + "|"
    lines.append(header)
    lines.append(sep)
    for label, path in COMPARISON_FIELDS:
        row = [label]
        for r in results:
            row.append(get_field(r, label, path))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # Differences
    diffs = compute_differences(results)
    if diffs:
        lines.append("## Differences\n")
        for entry in diffs:
            if entry[0] == "__permissions_diff__":
                only_in = entry[1]
                lines.append("### Permissions unique to specific APKs\n")
                for name, perms in only_in.items():
                    lines.append(f"**{name}:**")
                    for p in perms:
                        lines.append(f"- {p}")
                    lines.append("")
            else:
                label, values = entry
                lines.append(f"- **{label}**: " +
                             " vs ".join(f"{r['apk_name']}=`{v}`"
                                         for r, v in zip(results, values)))
        lines.append("")

    # Permissions detail
    lines.append("## Permissions Detail\n")
    for r in results:
        perms = r.get("manifest", {}).get("permissions", [])
        lines.append(f"### {r['apk_name']} ({len(perms)} permissions)\n")
        if perms:
            for p in perms:
                lines.append(f"- {p}")
        else:
            lines.append("(none)")
        lines.append("")

    # Errors
    if any(r.get("errors") for r in results):
        lines.append("## Errors\n")
        for r in results:
            if r.get("errors"):
                lines.append(f"### {r['apk_name']}\n")
                for e in r["errors"]:
                    lines.append(f"- {e}")
                lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_path


# ── HTML report ───────────────────────────────────────────────────────

def generate_html(results, output_path):
    """Generate a standalone HTML comparison report."""
    diffs = compute_differences(results)
    diff_labels = set(d[0] for d in diffs if d[0] != "__permissions_diff__")

    # Build comparison table rows
    table_rows = []
    for label, path in COMPARISON_FIELDS:
        values = [get_field(r, label, path) for r in results]
        is_diff = label in diff_labels
        cells = []
        for v in values:
            css = " class='diff'" if is_diff else ""
            cells.append(f"<td{css}>{escape(str(v))}</td>")
        table_rows.append(
            f"<tr><td class='label'>{escape(label)}</td>{''.join(cells)}</tr>")

    # Build permission sections
    perm_sections = []
    for r in results:
        perms = r.get("manifest", {}).get("permissions", [])
        items = "".join(f"<li>{escape(p)}</li>" for p in perms) or \
            "<li class='none'>(none)</li>"
        perm_sections.append(
            f"<div class='perm-block'><h4>{escape(r['apk_name'])} "
            f"<span class='badge'>{len(perms)}</span></h4>"
            f"<ul class='perm-list'>{items}</ul></div>")

    # Build error section
    error_blocks = ""
    if any(r.get("errors") for r in results):
        blocks = []
        for r in results:
            if r.get("errors"):
                items = "".join(f"<li>{escape(e)}</li>" for e in r["errors"])
                blocks.append(
                    f"<div><h4>{escape(r['apk_name'])}</h4><ul class='errors'>{items}</ul></div>")
        error_blocks = (
            "<section><h2>Errors</h2>" + "".join(blocks) + "</section>")

    # Differences section
    diff_html = ""
    if diffs:
        parts = []
        for entry in diffs:
            if entry[0] == "__permissions_diff__":
                only_in = entry[1]
                sub = []
                for name, perms in only_in.items():
                    items = "".join(f"<li>{escape(p)}</li>" for p in perms)
                    sub.append(f"<h4>{escape(name)}</h4><ul>{items}</ul>")
                parts.append(
                    "<div><h3>Permissions unique to specific APKs</h3>"
                    + "".join(sub) + "</div>")
            else:
                label, values = entry
                cells = []
                for r, v in zip(results, values):
                    cells.append(f"<td>{escape(str(v))}</td>")
                parts.append(
                    f"<tr><td class='label'>{escape(label)}</td>"
                    + "".join(cells) + "</tr>")
        diff_html = (
            "<section><h2>Differences</h2>"
            "<table class='diff-table'><thead><tr><th>Field</th>"
            + "".join(f"<th>{escape(r['apk_name'])}</th>" for r in results)
            + "</tr></thead><tbody>" + "".join(parts) + "</tbody></table>"
            + "</section>")

    ok_count = sum(1 for r in results if r["status"] == "ok")
    err_count = sum(1 for r in results if r["status"] == "error")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>APK Audit Report</title>
<style>
  :root {{
    --bg: #f8f9fa; --card: #fff; --border: #e0e0e0;
    --text: #1a1a1a; --muted: #6c757d;
    --primary: #4f46e5; --primary-light: #eef2ff;
    --diff-bg: #fef3c7; --diff-text: #92400e;
    --error-bg: #fef2f2; --error-text: #991b1b;
    --ok: #16a34a; --err: #dc2626;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
           Roboto, sans-serif; background: var(--bg); color: var(--text);
           line-height: 1.6; padding: 24px; }}
  header {{ background: linear-gradient(135deg, var(--primary), #7c3aed);
            color: #fff; padding: 32px; border-radius: 12px; margin-bottom: 24px; }}
  header h1 {{ font-size: 28px; margin-bottom: 8px; }}
  header .subtitle {{ opacity: .85; font-size: 15px; }}
  .stats {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
  .stat-card {{ background: var(--card); border: 1px solid var(--border);
                border-radius: 8px; padding: 16px 24px; min-width: 120px;
                text-align: center; }}
  .stat-card .num {{ font-size: 32px; font-weight: 700; }}
  .stat-card .lbl {{ font-size: 13px; color: var(--muted); }}
  .stat-card.ok .num {{ color: var(--ok); }}
  .stat-card.err .num {{ color: var(--err); }}
  section {{ background: var(--card); border: 1px solid var(--border);
             border-radius: 8px; padding: 24px; margin-bottom: 24px;
             overflow-x: auto; }}
  h2 {{ font-size: 20px; margin-bottom: 16px; border-bottom: 2px solid var(--border);
        padding-bottom: 8px; }}
  h3 {{ font-size: 16px; margin: 16px 0 8px; }}
  h4 {{ font-size: 14px; margin: 12px 0 6px; }}
  table {{ border-collapse: collapse; width: 100%; min-width: 600px; }}
  th, td {{ padding: 8px 12px; text-align: left; border: 1px solid var(--border);
            font-size: 13px; word-break: break-all; }}
  th {{ background: var(--primary-light); font-weight: 600; white-space: nowrap; }}
  td.label {{ font-weight: 600; background: #f9fafb; white-space: nowrap; }}
  td.diff {{ background: var(--diff-bg); color: var(--diff-text); }}
  .perm-block {{ margin-bottom: 16px; }}
  .perm-list {{ list-style: none; columns: 2; -webkit-columns: 2;
                column-gap: 24px; }}
  .perm-list li {{ padding: 3px 0; font-size: 12px; font-family: monospace;
                   break-inside: avoid; }}
  .perm-list li.none {{ color: var(--muted); font-style: italic; }}
  .badge {{ display: inline-block; background: var(--primary-light);
             color: var(--primary); padding: 1px 8px; border-radius: 10px;
             font-size: 12px; font-weight: 600; }}
  ul.errors {{ color: var(--error-text); padding-left: 20px; }}
  .diff-table td.label {{ white-space: nowrap; }}
</style>
</head>
<body>
<header>
  <h1>APK Audit Report</h1>
  <div class="subtitle">Batch audit and comparison of {len(results)} APK(s)</div>
</header>
<div class="stats">
  <div class="stat-card"><div class="num">{len(results)}</div><div class="lbl">Total</div></div>
  <div class="stat-card ok"><div class="num">{ok_count}</div><div class="lbl">OK</div></div>
  <div class="stat-card err"><div class="num">{err_count}</div><div class="lbl">Errors</div></div>
</div>
<section>
  <h2>Comparison</h2>
  <table>
    <thead>
      <tr><th>Field</th>{''.join(f'<th>{escape(r["apk_name"])}</th>' for r in results)}</tr>
    </thead>
    <tbody>{''.join(table_rows)}</tbody>
  </table>
</section>
{diff_html}
<section>
  <h2>Permissions Detail</h2>
  {''.join(perm_sections)}
</section>
{error_blocks}
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


# ── Entry point ───────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: apk_audit.py <apk_paths> <output_dir>"}))
        sys.exit(1)

    apk_paths_arg = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else ""

    # Resolve output directory
    if not output_dir:
        output_dir = tempfile.mkdtemp(prefix="apk_audit_")
    os.makedirs(output_dir, exist_ok=True)

    # Parse APK paths: comma-separated or directory
    apk_paths = []
    if os.path.isdir(apk_paths_arg):
        for f in sorted(os.listdir(apk_paths_arg)):
            if f.lower().endswith(".apk"):
                apk_paths.append(os.path.join(apk_paths_arg, f))
    else:
        apk_paths = [p.strip() for p in apk_paths_arg.split(",") if p.strip()]

    if not apk_paths:
        print(json.dumps({"error": "No APK files found"}))
        sys.exit(1)

    # Locate binaries
    java_bin = find_java()
    apktool_jar = find_apktool_jar()
    if not java_bin:
        print(json.dumps({
            "error": "Java not found. Set JAVA_HOME, BT_JAVA_BIN, or ensure java is on PATH."
        }))
        sys.exit(1)
    if not apktool_jar:
        print(json.dumps({
            "error": "apktool.jar not found. Place it at runtime/apktool/apktool.jar "
                     "or set BT_RUNTIME_DIR."
        }))
        sys.exit(1)

    # Audit each APK
    temp_base = tempfile.mkdtemp(prefix="apk_audit_decompile_")
    results = []
    for apk_path in apk_paths:
        if not os.path.isfile(apk_path):
            results.append({
                "apk_path": os.path.abspath(apk_path),
                "apk_name": os.path.basename(apk_path),
                "apk_size": 0,
                "status": "error",
                "errors": [f"file not found: {apk_path}"],
            })
            continue
        results.append(audit_apk(apk_path, temp_base, java_bin, apktool_jar))

    shutil.rmtree(temp_base, ignore_errors=True)

    # Generate reports
    md_path = os.path.join(output_dir, "apk-audit-report.md")
    html_path = os.path.join(output_dir, "apk-audit-report.html")
    generate_markdown(results, md_path)
    generate_html(results, html_path)

    # JSON summary to stdout
    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "markdown_report": os.path.abspath(md_path),
        "html_report": os.path.abspath(html_path),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
