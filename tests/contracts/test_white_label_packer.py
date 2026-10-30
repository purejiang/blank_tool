#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract/unit tests for the white-label-packer builtin plugin.

The integration test at the bottom builds a synthetic APK + AAB with the
bundled runtime tools and exercises the real ``PluginContext``; it is skipped
when ``runtime/`` is absent (it is gitignored, so CI without the runtime just
skips). Unit tests below never spawn tools.
"""

import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

import pytest

# conftest already puts backend/ on sys.path
ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = ROOT / "plugins-dist" / "white-label-packer"
PLUGIN_MAIN = PLUGIN_DIR / "main.py"
RUNTIME = ROOT / "runtime"


def _load_plugin():
    spec = importlib.util.spec_from_file_location("wl_main_contract", PLUGIN_MAIN)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wl_main_contract"] = mod
    spec.loader.exec_module(mod)
    return mod


WL = _load_plugin()

TEST_TMP = ROOT / ".tmp" / "wl-tests"
os.makedirs(TEST_TMP, exist_ok=True)


@pytest.fixture
def workdir():
    """Workspace-local tmp dir (pytest's tmp_path is unusable under the
    DSH sandbox on this machine; see AGENTS.md/TROUBLESHOOTING)."""
    d = TEST_TMP / ("case-" + uuid.uuid4().hex)
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:dist="http://schemas.android.com/apk/distribution"
    package="com.example.base"
    android:versionCode="7"
    android:versionName="1.2.3"
    android:sharedUserId="com.example.shared">
    <uses-sdk android:minSdkVersion="21" android:targetSdkVersion="33"/>
    <dist:module dist:instant="false"/>
    <permission android:name="com.example.base.permission.C2D" android:protectionLevel="signature"/>
    <uses-permission android:name="com.example.base.permission.C2D"/>
    <application android:label="@string/app_name" android:icon="@drawable/icon"
        android:allowBackup="true">
        <activity android:name=".MainActivity" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN"/>
                <category android:name="android.intent.category.LAUNCHER"/>
            </intent-filter>
        </activity>
        <provider android:name="com.example.base.FP"
            android:authorities="com.example.base.fileprovider"
            android:exported="false"/>
    </application>
</manifest>
"""


class _Tool:
    def __init__(self, path):
        self.tool_path = path
        self.is_valid = bool(path)

    def get_java_path(self):
        return str(RUNTIME / "jre" / "bin" / "java.exe")


class _Ctx:
    """Minimal PluginContext stand-in for action-level unit tests."""

    def __init__(self, tools=None):
        self.tools = tools or {}
        self.finished = None
        self.cancelled_payload = None

    def get_tool(self, name):
        return self.tools.get(name)

    def log(self, msg):
        pass

    def error(self, msg):
        pass

    def is_cancelled(self):
        return False

    def work_dir(self, task_id="", sub=""):
        import tempfile
        base = tempfile.mkdtemp(prefix="wl-ctx-")
        p = os.path.join(base, sub) if sub else base
        os.makedirs(p, exist_ok=True)
        return p

    def finish(self, payload):
        self.finished = payload
        return payload

    def cancelled(self, payload):
        self.cancelled_payload = payload


def _spec(**over):
    spec = {
        "resource_pkg": "com.example.base",
        "new_pkg": "com.example.white",
        "app_name": "白包 App",
        "metadata": [{"name": "wl_channel", "value": "{channel}"}],
        "mapping": {"channel": "other"},
        "rename_authorities": True,
        "rename_permissions": True,
        "remove_shared_uid": True,
    }
    spec.update(over)
    return spec


# ---------------------------------------------------------------------------
# Manifest patching
# ---------------------------------------------------------------------------

def test_patch_manifest_identity_and_flags():
    import xml.etree.ElementTree as ET

    out = WL._patch_manifest(MANIFEST, _spec())
    root = ET.fromstring(out)
    A = "{http://schemas.android.com/apk/res/android}"
    assert root.get("package") == "com.example.base"       # resource package kept
    assert root.get(A + "sharedUserId") is None
    app = root.find("application")
    assert app.get(A + "label") == "白包 App"
    # relative class name expanded against the old package
    act = app.find("activity")
    assert act.get(A + "name") == "com.example.base.MainActivity"
    # custom permission + its use renamed
    perm = root.find("permission")
    assert perm.get(A + "name") == "com.example.white.permission.C2D"
    use = root.find("uses-permission")
    assert use.get(A + "name") == "com.example.white.permission.C2D"
    # provider authority renamed
    prov = app.find("provider")
    assert prov.get(A + "authorities") == "com.example.white.fileprovider"
    # meta-data inserted with placeholder substituted
    metas = [m for m in app.findall("meta-data") if m.get(A + "name") == "wl_channel"]
    assert len(metas) == 1
    assert metas[0].get(A + "value") == "other"
    # dist namespace element preserved
    assert "dist:module" in out or "module" in out


def test_patch_manifest_flags_off_keep_authority_permission_and_shared_uid():
    import xml.etree.ElementTree as ET

    out = WL._patch_manifest(
        MANIFEST,
        _spec(rename_authorities=False, rename_permissions=False,
              remove_shared_uid=False, metadata=[]),
    )
    root = ET.fromstring(out)
    A = "{http://schemas.android.com/apk/res/android}"
    assert root.get(A + "sharedUserId") == "com.example.shared"
    app = root.find("application")
    assert app.find("provider").get(A + "authorities") == "com.example.base.fileprovider"
    assert root.find("permission").get(A + "name") == "com.example.base.permission.C2D"


def test_patch_manifest_adds_permissions():
    import xml.etree.ElementTree as ET

    out = WL._patch_manifest(
        MANIFEST,
        _spec(permissions=["com.android.vending.BILLING",
                           "com.android.vending.BILLING"]),
    )
    root = ET.fromstring(out)
    A = "{http://schemas.android.com/apk/res/android}"
    names = [e.get(A + "name") for e in root.findall("uses-permission")]
    assert names.count("com.android.vending.BILLING") == 1
    assert "com.example.white.permission.C2D" in names
    # 额外权限插在 <application> 之前
    app_index = list(root).index(root.find("application"))
    perm_index = [i for i, e in enumerate(root)
                  if e.tag == "uses-permission"
                  and e.get(A + "name") == "com.android.vending.BILLING"][0]
    assert perm_index < app_index


def test_patch_manifest_removes_split_for_aab_base():
    import xml.etree.ElementTree as ET

    text = MANIFEST.replace(
        'package="com.example.base"', 'package="com.example.base" split="config.arm64"'
    )
    out = WL._patch_manifest(text, _spec(metadata=[]))
    root = ET.fromstring(out)
    assert root.get("split") is None


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def test_parse_badging():
    text = (
        "package: name='com.example.base' versionCode='7' versionName='1.2.3' "
        "platformBuildVersionName='11'\n"
        "minSdkVersion:'21'\n"
        "targetSdkVersion:'33'\n"
        "uses-permission: name='android.permission.INTERNET'\n"
        "application-label:'Base App'\n"
        "application-icon-160:'res/drawable/icon.png'\n"
        "native-code: 'arm64-v8a' 'armeabi-v7a'\n"
        "application-debuggable\n"
    )
    info = WL._parse_badging(text)
    assert info["package"] == "com.example.base"
    assert info["version_code"] == 7
    assert info["version_name"] == "1.2.3"
    assert info["min_sdk"] == "21"
    assert info["target_sdk"] == "33"
    assert info["label"] == "Base App"
    assert info["abis"] == ["arm64-v8a", "armeabi-v7a"]
    assert info["debuggable"] is True
    assert info["icon_files"] == ["res/drawable/icon.png"]


def test_parse_resources():
    text = (
        "Binary APK\n"
        "Package name=com.example.base id=7f\n"
        "  type drawable id=01 entryCount=1\n"
        "    resource 0x7f010000 drawable/icon\n"
        "      () (file) res/drawable/icon.png type=PNG\n"
        "  type string id=02 entryCount=1\n"
        "    resource 0x7f020000 string/app_name\n"
        "      () \"Base App\"\n"
    )
    info = WL._parse_resources(text)
    assert info["package"] == "com.example.base"
    assert info["name_to_id"]["drawable/icon"] == "0x7f010000"
    assert info["id_to_files"]["0x7f010000"] == ["res/drawable/icon.png"]


def test_parse_apktool_yml():
    yml = """version: 2.12.1
apkFileName: base.apk
sdkInfo:
  minSdkVersion: 21
  targetSdkVersion: 33
packageInfo:
  forcedPackageId: 127
versionInfo:
  versionCode: 7
  versionName: 1.2.3
doNotCompress:
- arsc
- png
"""
    meta = WL._parse_apktool_yml(yml)
    assert meta["version_code"] == 7
    assert meta["version_name"] == "1.2.3"
    assert meta["min_sdk"] == "21"
    assert meta["target_sdk"] == "33"
    assert meta["do_not_compress"] == ["arsc", "png"]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def test_safe_asset_rel():
    assert WL._safe_asset_rel("assets/channel.json") == "assets/channel.json"
    assert WL._safe_asset_rel("channel.json") == "assets/channel.json"
    for bad in ("../evil", "/abs/x", "C:/x", "assets/../../x"):
        with pytest.raises(Exception):
            WL._safe_asset_rel(bad)


def test_safe_asset_rel_normalizes():
    assert WL._safe_asset_rel("assets\\sub\\x.json") == "assets/sub/x.json"
    assert WL._safe_asset_rel("") == ""


def test_substitute():
    mapping = {"channel": "other", "package": "com.x", "app_name": "X"}
    assert WL._substitute("{channel}:{package}:{unknown}", mapping) == "other:com.x:{unknown}"


def test_validate_package():
    WL._validate_package("com.example.white", "com.example.base")
    for bad in ("", "com", "1com.x", "com..x", "com.x-y"):
        with pytest.raises(Exception):
            WL._validate_package(bad, "com.example.base")
    with pytest.raises(Exception):
        WL._validate_package("com.example.base", "com.example.base")


def test_channel_config_supports_custom_channels():
    ch = WL._channel_config({
        "id": "other", "package_name": "com.x.o", "app_name": "X",
        "format": "aab", "keystore": {},
    })
    assert ch["id"] == "other"
    assert ch["label"] == "其他包"
    assert ch["format"] == "aab"           # 不再强制 APK

    custom = WL._channel_config({
        "id": "partner", "label": "合作方", "package_name": "com.x.p",
        "app_name": "P", "format": "both", "keystore": {},
        "permissions": ["com.android.vending.BILLING",
                        "com.android.vending.BILLING"],
    })
    assert custom["id"] == "partner"
    assert custom["label"] == "合作方"
    assert custom["format"] == "both"
    assert custom["permissions"] == ["com.android.vending.BILLING"]

    with pytest.raises(Exception):
        WL._channel_config({"id": "other", "permissions": ["bad perm"]})

    for bad in ("", "../x", "腾讯", "A B", "a" * 40):
        with pytest.raises(Exception):
            WL._channel_config({"id": bad})


def test_profile_excludes_passwords():
    prof = WL._profile_from_channel({
        "id": "partner", "label": "合作方", "enabled": True,
        "package_name": "com.x", "app_name": "X",
        "keystore": {"path": "k.jks", "alias": "a", "storepass": "s", "keypass": "k"},
    })
    assert prof["label"] == "合作方"
    assert prof["keystore"] == {"path": "k.jks", "alias": "a"}
    assert "storepass" not in json.dumps(prof)
    assert "keypass" not in json.dumps(prof)


# ---------------------------------------------------------------------------
# Zip assembly / AAB splice
# ---------------------------------------------------------------------------

def _zip(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)


def _names(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def test_assemble_apk(workdir):
    link = workdir / "link.apk"
    src = workdir / "src.apk"
    out = workdir / "out.apk"
    _zip(link, {
        "AndroidManifest.xml": b"NEW_MANIFEST",
        "resources.arsc": b"NEW_ARSC",
        "res/new.png": b"NEW_RES",
    })
    _zip(src, {
        "AndroidManifest.xml": b"OLD_MANIFEST",
        "resources.arsc": b"OLD_ARSC",
        "res/old.png": b"OLD_RES",
        "classes.dex": b"DEX",
        "assets/keep.txt": b"KEEP",
        "META-INF/MANIFEST.MF": b"SIG",
        "META-INF/services/x": b"SVC",
        "lib/arm64-v8a/libx.so": b"SO",
    })
    WL._assemble_apk(str(link), str(src), str(out),
                     {"assets/channel.json": b"CH"})
    names = _names(str(out))
    assert names["AndroidManifest.xml"] == b"NEW_MANIFEST"
    assert names["resources.arsc"] == b"NEW_ARSC"
    assert names["res/new.png"] == b"NEW_RES"
    assert "res/old.png" not in names
    assert names["classes.dex"] == b"DEX"
    assert names["assets/keep.txt"] == b"KEEP"
    assert names["assets/channel.json"] == b"CH"
    assert names["META-INF/services/x"] == b"SVC"
    assert "META-INF/MANIFEST.MF" not in names
    assert names["lib/arm64-v8a/libx.so"] == b"SO"


def test_build_module_zip(workdir):
    proto = workdir / "proto.apk"
    src = workdir / "src.apk"
    out = workdir / "module.zip"
    _zip(proto, {
        "AndroidManifest.xml": b"MANIFEST_PROTO",
        "resources.pb": b"RES_PB",
        "res/a.png": b"RES",
    })
    _zip(src, {
        "AndroidManifest.xml": b"OLD",
        "resources.arsc": b"ARSC",
        "res/old.png": b"OLD",
        "classes.dex": b"DEX",
        "classes2.dex": b"DEX2",
        "lib/arm64-v8a/libx.so": b"SO",
        "assets/a.txt": b"A",
        "kotlin/METADATA": b"META",
        "META-INF/MANIFEST.MF": b"SIG",
    })
    WL._build_module_zip(str(proto), str(src), str(out),
                         {"assets/channel.json": b"CH"})
    names = _names(str(out))
    assert names["manifest/AndroidManifest.xml"] == b"MANIFEST_PROTO"
    assert names["resources.pb"] == b"RES_PB"
    assert names["res/a.png"] == b"RES"
    assert names["dex/classes.dex"] == b"DEX"
    assert names["dex/classes2.dex"] == b"DEX2"
    assert names["lib/arm64-v8a/libx.so"] == b"SO"
    assert names["assets/a.txt"] == b"A"
    assert names["assets/channel.json"] == b"CH"
    assert names["root/kotlin/METADATA"] == b"META"
    assert "root/META-INF/MANIFEST.MF" not in names


def test_aab_guard_ignores_bundle_metadata(monkeypatch, workdir):
    aab = workdir / "real.aab"
    _zip(aab, {
        "BUNDLE-METADATA/com.android.tools.build.obfuscation/proguard.map": b"x",
        "BundleConfig.pb": b"cfg",
        "base/manifest/AndroidManifest.xml": b"manifest",
        "base/resources.pb": b"res",
        "base/dex/classes.dex": b"dex",
        "META-INF/MANIFEST.MF": b"sig",
    })
    dumped = (
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
        'package="com.test" android:versionCode="1" android:versionName="1.0"/>'
    )
    monkeypatch.setattr(WL, "_bundletool_dump_manifest", lambda *a: (0, dumped))
    source = {"package": "com.test", "version_code": 1, "version_name": "1.0"}
    info = WL._aab_guard(_Ctx(), {}, str(aab), source, str(workdir))
    assert info["modules"] == ["base"]          # BUNDLE-METADATA 不是模块
    assert info["same_build"] is True
    assert info["splice_available"] is True


def test_splice_aab_replaces_and_preserves(workdir):
    source = workdir / "source.aab"
    out = workdir / "out.aab"
    _zip(source, {
        "BundleConfig.pb": b"CFG",
        "base/manifest/AndroidManifest.xml": b"OLD_MANIFEST",
        "base/resources.pb": b"RES_PB",
        "base/res/icon.png": b"OLD_ICON",
        "base/dex/classes.dex": b"DEX",
        "base/assets/keep.txt": b"KEEP",
        "META-INF/MANIFEST.MF": b"SIG",
        "META-INF/BASE.SF": b"SIG",
        "META-INF/BASE.RSA": b"SIG",
    })
    WL._splice_aab(
        _Ctx(), {}, str(source), b"NEW_MANIFEST",
        {"res/icon.png": b"NEW_ICON"},
        {"assets/channel.json": b"CH"},
        str(out), str(workdir),
    )
    names = _names(str(out))
    assert names["base/manifest/AndroidManifest.xml"] == b"NEW_MANIFEST"
    assert names["base/res/icon.png"] == b"NEW_ICON"
    assert names["base/assets/channel.json"] == b"CH"
    assert names["base/resources.pb"] == b"RES_PB"
    assert names["base/dex/classes.dex"] == b"DEX"
    assert names["BundleConfig.pb"] == b"CFG"
    assert "META-INF/MANIFEST.MF" not in names
    assert "META-INF/BASE.SF" not in names
    assert "META-INF/BASE.RSA" not in names


# ---------------------------------------------------------------------------
# Actions / discovery / UI contract
# ---------------------------------------------------------------------------

def test_presets_shape(monkeypatch, workdir):
    monkeypatch.setenv("BT_OUTPUT_DIR", str(workdir / "out"))
    ctx = _Ctx({
        "apktool": _Tool("x"), "aapt": _Tool("x"), "zipalign": _Tool("x"),
        "apksigner": _Tool("x"), "bundletool": _Tool("x"),
        "jarsigner": _Tool("x"),
    })
    payload = WL.run(ctx, action="presets")
    assert payload["action"] == "presets"
    assert [c["id"] for c in payload["channels"]] == ["other", "samsung", "google"]
    assert payload["channels"][0]["label"] == "其他包"
    assert payload["defaults"]["google_mode"] == "auto"
    assert payload["defaults"]["strict_aab_check"] is True
    assert "tools" in payload and "saved_profiles" in payload
    assert "bundled" in payload


def test_bundled_assets_discovery(monkeypatch, workdir):
    plugin = workdir / "plugin"
    assets = plugin / "assets"
    assets.mkdir(parents=True)
    (assets / "base.apk").write_bytes(b"fake-apk")
    monkeypatch.setattr(WL, "PLUGIN_DIR", str(plugin))
    monkeypatch.setattr(WL, "BUNDLED_ASSETS", str(assets))
    bundled = WL._bundled_paths()
    assert bundled["apk"] == str(assets / "base.apk")
    assert bundled["aab"] == ""
    (assets / "base.aab").write_bytes(b"fake-aab")
    bundled = WL._bundled_paths()
    assert bundled["aab"] == str(assets / "base.aab")


def test_profiles_roundtrip(monkeypatch, workdir):
    monkeypatch.setenv("BT_OUTPUT_DIR", str(workdir / "out"))
    WL._save_profiles({
        "schema": 1,
        "channels": {"partner": {"label": "合作方", "package_name": "com.x.partner"}},
    })
    loaded = WL._load_profiles()
    assert loaded["channels"]["partner"]["label"] == "合作方"
    assert loaded["channels"]["partner"]["package_name"] == "com.x.partner"


def test_presets_migrates_legacy_tencent(monkeypatch, workdir):
    monkeypatch.setenv("BT_OUTPUT_DIR", str(workdir / "out"))
    WL._save_profiles({
        "schema": 1,
        "channels": {"tencent": {"package_name": "com.x.tencent"}},
    })
    ctx = _Ctx({
        "apktool": _Tool("x"), "aapt": _Tool("x"), "zipalign": _Tool("x"),
        "apksigner": _Tool("x"), "bundletool": _Tool("x"),
        "jarsigner": _Tool("x"),
    })
    saved = WL.run(ctx, action="presets")["saved_profiles"]
    assert "other" in saved["channels"]
    assert saved["channels"]["other"]["package_name"] == "com.x.tencent"


def test_ui_static_contract():
    html = (PLUGIN_DIR / "ui" / "index.html").read_text(encoding="utf-8")
    allowed = {
        "run", "cancel", "log", "getMeta", "getDevices", "pickFile",
        "pickDirectory", "openPath", "toast", "confirm",
        "onLog", "onResult", "onError", "onMeta", "onDevices",
        "onFile", "onDir", "onConfirm",
    }
    calls = set(re.findall(r"\bbridge\.(\w+)", html))
    assert calls, "UI must call pluginBridge via the bridge alias"
    assert calls <= allowed, f"non-whitelisted bridge calls: {calls - allowed}"
    assert not re.search(r"https?://", html), "UI must be offline (no external URLs)"
    assert "html,body" in html.replace(" ", "")
    assert "pluginBridge" in html
    assert "开始打包" in html and "取消" in html
    assert "其他包" in html and "btnAddChannel" in html
    assert 'data-field="label"' in html
    assert 'data-field="permissions"' in html and "com.android.vending.BILLING" in html
    assert "apkBundled" in html and "aabBundled" in html and "btnClearAab" in html


def test_plugin_package_importable(monkeypatch, workdir):
    """The plugin must work as a distributable zip, not as a builtin."""
    import app.plugins.manager as m
    from app.handlers.plugin_package_handler import import_plugin

    assert not (ROOT / "backend" / "app" / "plugins" / "builtin"
                / "white-label-packer").exists()

    # build a zip with the same layout the plugin page imports
    zip_path = workdir / "white-label-packer.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(PLUGIN_DIR.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            zf.write(p, p.relative_to(PLUGIN_DIR).as_posix())

    user = workdir / "user"
    user.mkdir()
    monkeypatch.setenv("BT_PLUGINS_DIR", str(user))
    m.PluginManager._instance = None
    try:
        plugins = import_plugin({"zip_path": str(zip_path)}, None)
        info = [p for p in plugins if p["name"] == "white-label-packer"][0]
        assert info["builtin"] is False
        assert info["ui_path"].endswith("index.html")
        assert os.path.isfile(info["ui_path"])
        assert "白包" in info["display_name"]
        assert os.path.isdir(user / "white-label-packer")
    finally:
        m.PluginManager._instance = None


# ---------------------------------------------------------------------------
# Integration: synthetic APK + AAB through the real runtime tools/context
# ---------------------------------------------------------------------------

def _runtime_ready() -> bool:
    names = [
        RUNTIME / "apktool" / "apktool.jar",
        RUNTIME / "aapt" / ("aapt2.exe" if os.name == "nt" else "aapt2"),
        RUNTIME / "android" / ("zipalign.exe" if os.name == "nt" else "zipalign"),
        RUNTIME / "android" / "apksigner.jar",
        RUNTIME / "android" / "android.jar",
        RUNTIME / "android" / "smali-2.5.2.jar",
        RUNTIME / "bundletool" / "bundletool.jar",
        RUNTIME / "jre" / "bin" / ("java.exe" if os.name == "nt" else "java"),
        RUNTIME / "jre" / "bin" / ("jarsigner.exe" if os.name == "nt" else "jarsigner"),
        RUNTIME / "jre" / "bin" / ("keytool.exe" if os.name == "nt" else "keytool"),
    ]
    return all(p.is_file() for p in names)


def _run_to_log(cmd, log_path, cwd=None):
    with open(log_path, "w", encoding="utf-8", errors="replace") as f:
        proc = subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT)
    assert proc.returncode == 0, (
        f"command failed ({proc.returncode}): {cmd}\n" +
        open(log_path, encoding="utf-8", errors="replace").read()[-3000:]
    )
    return proc.returncode


def _build_synthetic_apk(workdir):
    from app.utils.png_image import encode_png_rgba

    java = RUNTIME / "jre" / "bin" / ("java.exe" if os.name == "nt" else "java")
    keytool = RUNTIME / "jre" / "bin" / ("keytool.exe" if os.name == "nt" else "keytool")
    aapt2 = RUNTIME / "aapt" / ("aapt2.exe" if os.name == "nt" else "aapt2")
    androd_jar = RUNTIME / "android" / "android.jar"
    smali = RUNTIME / "android" / "smali-2.5.2.jar"
    apksigner = RUNTIME / "android" / "apksigner.jar"
    logs = workdir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    base = workdir / "base"
    (base / "res" / "values").mkdir(parents=True, exist_ok=True)
    (base / "res" / "drawable").mkdir(parents=True, exist_ok=True)

    (base / "res" / "values" / "strings.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<resources><string name=\"app_name\">Base App</string>"
        "<string name=\"hello\">Hello</string></resources>\n",
        encoding="utf-8",
    )
    px = bytearray(48 * 48 * 4)
    for i in range(0, len(px), 4):
        px[i:i + 4] = bytes((20, 80, 200, 255))
    (base / "res" / "drawable" / "icon.png").write_bytes(encode_png_rgba(48, 48, px))

    manifest = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.base" android:versionCode="7" android:versionName="1.2.3"
    android:sharedUserId="com.example.shared">
    <uses-sdk android:minSdkVersion="21" android:targetSdkVersion="33"/>
    <permission android:name="com.example.base.permission.C2D" android:protectionLevel="signature"/>
    <uses-permission android:name="com.example.base.permission.C2D"/>
    <application android:label="@string/app_name" android:icon="@drawable/icon"
        android:allowBackup="true">
        <activity android:name=".MainActivity" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN"/>
                <category android:name="android.intent.category.LAUNCHER"/>
            </intent-filter>
        </activity>
        <provider android:name="com.example.base.FP"
            android:authorities="com.example.base.fileprovider" android:exported="false"/>
    </application>
</manifest>
"""
    (base / "AndroidManifest.xml").write_text(manifest, encoding="utf-8")

    _run_to_log([str(aapt2), "compile", "--dir", str(base / "res"),
                 "-o", str(base / "compiled.zip")], str(logs / "compile.log"))
    unsigned = base / "unsigned.apk"
    _run_to_log(
        [str(aapt2), "link", "-o", str(unsigned), "-I", str(androd_jar),
         "--manifest", str(base / "AndroidManifest.xml"),
         str(base / "compiled.zip"),
         "--min-sdk-version", "21", "--target-sdk-version", "33",
         "--version-code", "7", "--version-name", "1.2.3"],
        str(logs / "link.log"),
    )

    smali_dir = base / "smali" / "com" / "example" / "base"
    smali_dir.mkdir(parents=True, exist_ok=True)
    (smali_dir / "Main.smali").write_text(
        ".class public Lcom/example/base/Main;\n.super Ljava/lang/Object;\n",
        encoding="utf-8",
    )
    dex = base / "classes.dex"
    _run_to_log([str(java), "-jar", str(smali), "assemble", "-o", str(dex),
                 str(base / "smali")], str(logs / "smali.log"))

    with zipfile.ZipFile(unsigned) as zin, \
            zipfile.ZipFile(base / "withdex.apk", "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            zi = zipfile.ZipInfo(info.filename, info.date_time)
            zi.compress_type = info.compress_type
            zout.writestr(zi, zin.read(info.filename))
        zout.write(dex, "classes.dex")

    ks = base / "base.p12"
    _run_to_log(
        [str(keytool), "-genkeypair", "-keystore", str(ks), "-storetype", "PKCS12",
         "-storepass", "basepass", "-keypass", "basepass", "-alias", "base",
         "-keyalg", "RSA", "-keysize", "2048", "-validity", "3650",
         "-dname", "CN=Base,O=Test,C=CN"],
        str(logs / "keytool.log"),
    )
    signed = base / "base.apk"
    _run_to_log(
        [str(java), "-jar", str(apksigner), "sign", "--ks", str(ks),
         "--ks-key-alias", "base", "--ks-pass", "pass:basepass",
         "--out", str(signed), str(base / "withdex.apk")],
        str(logs / "sign.log"),
    )
    return signed, {"path": str(ks), "alias": "base",
                    "storepass": "basepass", "keypass": ""}


@pytest.mark.skipif(not _runtime_ready(), reason="runtime/ tools not present")
def test_integration_apk_and_aab_splice(monkeypatch, workdir):
    """End-to-end: real PluginContext + apktool/aapt2/apksigner/bundletool.

    Slow (~20-40s). Needs runtime/ (gitignored). Under the DSH sandbox this
    test needs full-access (Java spawns child processes with pipes).
    """
    import hashlib

    from app.plugins.context import PluginContext

    tasks = workdir / "tasks"
    out = workdir / "out"
    cache = workdir / "cache"
    tmp = workdir / "tmp"
    logs = workdir / "logs"
    for p in (tasks, out, cache, tmp, logs):
        p.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BT_RUNTIME_DIR", str(RUNTIME))
    monkeypatch.setenv("BT_TASKS_DIR", str(tasks))
    monkeypatch.setenv("BT_OUTPUT_DIR", str(out))
    monkeypatch.setenv("BT_CACHE_DIR", str(cache))
    monkeypatch.setenv("BT_LOG_DIR", str(logs))
    monkeypatch.setenv("TMP", str(tmp))
    monkeypatch.setenv("TEMP", str(tmp))
    monkeypatch.setenv("TMPDIR", str(tmp))

    apk, keystore = _build_synthetic_apk(workdir)
    apk_hash = hashlib.sha256(apk.read_bytes()).hexdigest()
    ctx = PluginContext("white-label-packer", None)

    # 插件自带 assets/base.apk 时，apk_path 省略也能 inspect
    bundled = workdir / "bundled-assets"
    bundled.mkdir()
    (bundled / "base.apk").write_bytes(apk.read_bytes())
    monkeypatch.setattr(WL, "BUNDLED_ASSETS", str(bundled))
    bundled_insp = WL.run(ctx, action="inspect", task_id="bundled-inspect",
                          apk_path="", aab_path="")
    assert bundled_insp["success"] is True
    assert bundled_insp["source"]["package"] == "com.example.base"

    insp = WL.run(ctx, action="inspect", task_id="t0",
                  apk_path=str(apk), aab_path="")
    assert insp["success"] is True
    assert insp["source"]["package"] == "com.example.base"
    assert insp["source"]["icon"]["files"], insp["source"]["icon"]

    icon = workdir / "new-icon.png"
    from app.utils.png_image import encode_png_rgba
    px = bytearray(96 * 96 * 4)
    for i in range(0, len(px), 4):
        px[i:i + 4] = bytes((220, 30, 40, 255))
    icon.write_bytes(encode_png_rgba(96, 96, px))

    def ch(cid, pkg, app_name, fmt, extra=None):
        c = {
            "id": cid, "enabled": True, "package_name": pkg,
            "app_name": app_name, "version_code": None, "version_name": None,
            "icon_path": str(icon), "format": fmt,
            "keystore": keystore,
            "metadata": [{"name": "wl_channel", "value": "{channel}"}],
            "permissions": ["com.android.vending.BILLING"],
            "asset": {"path": "assets/channel.json",
                      "content": '{"channel":"{channel}"}'},
            "rename_authorities": True, "rename_permissions": True,
            "remove_shared_uid": True,
        }
        if extra:
            c.update(extra)
        return c

    result = WL.run(
        ctx, action="pack", task_id="t1", apk_path=str(apk), aab_path="",
        output_dir=str(out), google_mode="reconstruct", strict_aab_check=True,
        save_profiles=False, keep_workdir=True,
        channels=[
            ch("other", "com.example.white.other", "白包其他", "apk"),
            ch("partner", "com.example.white.partner", "白包合作方", "apk"),
            ch("google", "com.example.white.google", "白包谷歌", "aab"),
        ],
    )
    assert result["success"] is True
    by = {i["channel"]: i for i in result["items"]}
    other = by["other"]
    partner = by["partner"]
    google = by["google"]
    assert other["apk_path"] and os.path.isfile(other["apk_path"])
    assert other["verify"]["apksigner"] == "ok"
    assert other["verify"]["zipalign"] == "ok"
    assert other["verify"]["badging"] == "ok"
    assert other["verify"]["resource_ids"] == "ok"
    assert partner["apk_path"] and os.path.isfile(partner["apk_path"])
    assert partner["verify"]["apksigner"] == "ok"
    assert google["aab_path"] and os.path.isfile(google["aab_path"])
    assert google["aab_mode"] == "reconstruct"
    assert google["verify"]["bundletool_validate"] == "ok"
    assert google["verify"]["jarsigner"] == "ok"
    assert google["verify"]["keytool"] == "ok"

    # Build a source AAB with the SAME identity as the APK, then splice.
    from app.utils.env import get_task_dir
    tools = WL._collect_tools(ctx)
    project = Path(get_task_dir("t1")) / "work" / "project"
    assert (project / "AndroidManifest.xml").is_file()
    src = WL._read_source(ctx, tools, str(apk), str(workdir / "src-inspect"))
    ids_path = workdir / "stable-ids.txt"
    ids_path.write_text("\n".join(
        f"{src['resource_package']}:{name}={rid}"
        for rid, name in src["resource_dump"]["id_to_name"].items()
    ) + "\n", encoding="utf-8")
    compiled = workdir / "source-compiled.zip"
    WL._aapt2_compile(ctx, tools, str(project), str(compiled))
    proto = workdir / "source-proto.apk"
    WL._aapt2_link(
        ctx, tools, str(project / "AndroidManifest.xml"), str(compiled),
        str(proto), src["package"],
        {"version_code": src["version_code"], "version_name": src["version_name"],
         "min_sdk": src["min_sdk"], "target_sdk": src["target_sdk"],
         "max_sdk": "", "do_not_compress": []},
        str(ids_path), proto=True,
    )
    module = workdir / "source-module.zip"
    WL._build_module_zip(str(proto), str(apk), str(module), {})
    source_aab = workdir / "source.aab"
    rc, text = WL._run(
        ctx, [tools["java"], "-jar", tools["bundletool"], "build-bundle",
              "--modules=" + str(module), "--output=" + str(source_aab),
              "--overwrite"],
        timeout=1200,
    )
    assert rc == 0, text[-2000:]
    WL._jarsigner_sign(ctx, tools, str(source_aab), keystore)
    source_hash = hashlib.sha256(source_aab.read_bytes()).hexdigest()
    before = WL._entry_hashes(str(source_aab))

    insp_aab = WL.run(ctx, action="inspect", task_id="t0",
                      apk_path=str(apk), aab_path=str(source_aab))
    assert insp_aab["success"] is True
    assert insp_aab["aab"]["same_build"] is True
    assert insp_aab["aab"]["splice_available"] is True

    result2 = WL.run(
        ctx, action="pack", task_id="t2", apk_path=str(apk),
        aab_path=str(source_aab), output_dir=str(out), google_mode="splice",
        strict_aab_check=True, save_profiles=False,
        channels=[ch("google", "com.example.white.spliced", "白包直改", "aab")],
    )
    item = result2["items"][0]
    assert item["aab_mode"] == "splice", item
    assert item["verify"]["jarsigner"] == "ok"
    assert item["verify"]["keytool"] == "ok"
    assert item["verify"]["bundletool_validate"] == "ok"
    assert item["verify"]["bundletool_build_apks"] == "ok"
    assert WL._entry_hashes(item["aab_path"]) == before
    assert hashlib.sha256(source_aab.read_bytes()).hexdigest() == source_hash
    assert hashlib.sha256(apk.read_bytes()).hexdigest() == apk_hash

