"""
Contract tests for AAB handler API methods.
"""
import json
import os
import tempfile
import time
import zipfile

from app.handlers.aab_handler import (
    API_MAP,
    _parse_bundle_manifest,
    _scan_aab_native_libs,
)


class TestAabSign:
    def test_missing_aab_path_returns_error(self, api_handler):
        request = {"id": 21, "method": "aab.sign", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 21
        result = data["result"]
        assert result["type"] == "error"

    def test_missing_keystore_returns_error(self, api_handler):
        request = {
            "id": 22,
            "method": "aab.sign",
            "params": {"aab_path": "/nonexistent/test.aab", "keystore": {}},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 22
        assert data["finished"] is True
        result = data["result"]
        assert result["type"] == "error"


class TestConvertAabToApks:
    def test_missing_aab_path_returns_error(self, api_handler):
        request = {"id": 23, "method": "device.convert_aab_to_apks", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestInstallAab:
    def test_missing_params_returns_error(self, api_handler):
        request = {"id": 24, "method": "device.install_aab", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        # Streaming handler returns stream_id immediately
        assert "stream_id" in data.get("result", {})
        assert data["finished"] is False

        # Wait for async stream thread to finish and capture error event
        for _ in range(50):
            if len(api_handler._captured) >= 2:
                break
            time.sleep(0.01)
        assert len(api_handler._captured) >= 2
        error_event = api_handler._captured[0]
        assert error_event["result"]["type"] == "error"

    def test_missing_device_id_returns_error(self, api_handler):
        request = {
            "id": 25,
            "method": "device.install_aab",
            "params": {"aab_path": "/nonexistent/test.aab"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        # Streaming handler returns stream_id immediately
        assert "stream_id" in data.get("result", {})
        assert data["finished"] is False

        # Wait for async stream thread to finish and capture error event
        for _ in range(50):
            if len(api_handler._captured) >= 2:
                break
            time.sleep(0.01)
        assert len(api_handler._captured) >= 2
        error_event = api_handler._captured[0]
        assert error_event["result"]["type"] == "error"
        assert "device" in error_event["result"]["payload"]["message"].lower()


class TestResponseShape:
    METHODS = ["aab.analyze", "aab.sign", "device.convert_aab_to_apks", "device.install_aab"]

    def test_all_methods_produce_valid_response_shape(self, api_handler):
        for method in self.METHODS:
            request = {"id": 200, "method": method, "params": {}}
            resp = api_handler.handle_request(request)
            data = json.loads(resp) if isinstance(resp, str) else resp
            assert "id" in data, f"{method}: missing id"
            assert "result" in data, f"{method}: missing result"
            assert "finished" in data, f"{method}: missing finished"


class TestAabAnalyzeHelpers:
    MANIFEST_XML = (
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
        'android:versionCode="42" android:versionName="1.2.3" '
        'package="com.example.aabtest">\n'
        '  <uses-sdk android:minSdkVersion="24" android:targetSdkVersion="36"/>\n'
        '  <uses-permission android:name="android.permission.INTERNET"/>\n'
        '  <uses-permission android:name="android.permission.CAMERA"/>\n'
        '  <application android:label="Test Bundle App" '
        'android:theme="@0x7f0c0005"/>\n'
        '</manifest>'
    )

    def test_parse_bundle_manifest(self):
        info = _parse_bundle_manifest(self.MANIFEST_XML)
        assert info['package_name'] == 'com.example.aabtest'
        assert info['version_code'] == '42'
        assert info['version_name'] == '1.2.3'
        assert info['min_sdk_version'] == '24'
        assert info['target_sdk_version'] == '36'
        assert info['permissions'] == [
            'android.permission.INTERNET',
            'android.permission.CAMERA',
        ]
        assert info['application_label'] == 'Test Bundle App'

    def test_parse_bundle_manifest_empty(self):
        assert _parse_bundle_manifest('') == {}

    def test_resource_ref_label_skipped(self):
        info = _parse_bundle_manifest(
            '<manifest package="com.x"><application android:label="@0x7f010001"/></manifest>'
        )
        assert 'application_label' not in info
        assert info['package_name'] == 'com.x'

    def test_scan_aab_native_libs(self):
        fd, path = tempfile.mkstemp(suffix='.aab')
        os.close(fd)
        try:
            with zipfile.ZipFile(path, 'w') as zf:
                zf.writestr('base/lib/arm64-v8a/liba.so', b'x')
                zf.writestr('base/lib/armeabi-v7a/liba.so', b'x')
                zf.writestr('feature/lib/arm64-v8a/libb.so', b'x')
                zf.writestr('base/lib/arm64-v8a/notes.txt', b'x')
            so_map = _scan_aab_native_libs(path)
            assert so_map['arm64-v8a'] == ['liba.so', 'libb.so']
            assert so_map['armeabi-v7a'] == ['liba.so']
        finally:
            os.unlink(path)

    def test_api_map_registers_analyze(self):
        assert 'aab.analyze' in API_MAP
