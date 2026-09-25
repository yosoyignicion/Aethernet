from __future__ import annotations

import json

from aethernet.integration.importer import (
    import_wifi_analyzer,
    parse_wifi_analyzer,
    security_from_capabilities,
)

SAMPLE = {
    "networks": [
        {
            "SSID": "MiWiFi_5G",
            "BSSID": "aa:bb:cc:11:22:33",
            "frequency": 5180,
            "level": -55,
            "capabilities": "[WPA2-PSK-CCMP][ESS]",
        },
        {"SSID": "Abierta", "BSSID": "aa:bb:cc:77:88:99", "frequency": 2462, "level": -80, "capabilities": "[ESS]"},
        {"SSID": "Wpa3", "BSSID": "aa:bb:cc:aa:bb:cc", "frequency": 5745, "level": -65, "capabilities": "[WPA3-SAE][ESS]"},
    ]
}


def test_security_from_capabilities():
    assert security_from_capabilities("[WPA2-PSK-CCMP][ESS]") == "wpa2"
    assert security_from_capabilities("[WPA3-SAE]") == "wpa3"
    assert security_from_capabilities("[ESS]") == "open"
    assert security_from_capabilities("[WPA-PSK-TKIP]") == "wpa"
    assert security_from_capabilities("[WEP]") == "wep"
    assert security_from_capabilities(None) == "open"


def test_parse_wifi_analyzer():
    aps = {ap.bssid: ap for ap in parse_wifi_analyzer(SAMPLE, timestamp=10.0)}
    assert len(aps) == 3
    assert aps["AA:BB:CC:11:22:33"].channel == 36
    assert aps["AA:BB:CC:11:22:33"].security == "wpa2"
    assert aps["AA:BB:CC:AA:BB:CC"].security == "wpa3"
    assert "imported" in aps["AA:BB:CC:77:88:99"].tags


def test_import_wifi_analyzer_file(tmp_path):
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(SAMPLE), encoding="utf-8")
    scan = import_wifi_analyzer(path)
    assert scan.count == 3
    assert scan.source == "import"


def test_parse_handles_unknown_shape():
    assert parse_wifi_analyzer({"foo": "bar"}) == []
    assert parse_wifi_analyzer([{"bssid": "aa:bb:cc:00:00:01", "ssid": "x", "level": -50}])
