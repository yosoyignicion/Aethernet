from __future__ import annotations

from aethernet.models import (
    Band,
    Severity,
    WifiScan,
    canonical_security,
    normalize_bssid,
    security_rank,
)
from helpers import ap


def test_security_canonicalization():
    assert canonical_security("") == "open"
    assert canonical_security("WPA1 WPA2") == "wpa2"
    assert canonical_security("WPA2") == "wpa2"
    assert canonical_security("wpa3") == "wpa3"
    assert canonical_security("WEP") == "wep"


def test_security_rank_orders_strength():
    assert security_rank("wpa3") >= security_rank("wpa2") > security_rank("wpa") > security_rank("wep") > security_rank("open")


def test_normalize_bssid():
    assert normalize_bssid("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert normalize_bssid(" aabbccddeeff ") == "AA:BB:CC:DD:EE:FF"
    assert normalize_bssid("") == ""


def test_band_detection():
    assert Band.from_frequency(2412) is Band.GHZ_24
    assert Band.from_frequency(5180) is Band.GHZ_5
    assert Band.from_frequency(5955) is Band.GHZ_6
    assert Band.from_frequency(0) is Band.UNKNOWN
    assert Band.from_channel(13) is Band.GHZ_24
    assert Band.from_channel(36) is Band.GHZ_5


def test_severity_ordering():
    assert Severity.CRITICAL.at_least(Severity.WARNING)
    assert not Severity.INFO.at_least(Severity.ALERT)
    assert Severity.CRITICAL.rank > Severity.INFO.rank


def test_access_point_flags():
    hidden = ap("", "AA:BB:CC:00:00:01", security="open", hidden=True)
    assert hidden.is_open
    assert not hidden.is_secure
    assert hidden.display_ssid == "<oculta>"
    strong = ap("Red", "AA:BB:CC:00:00:02", dbm=-40, security="wpa3")
    assert strong.is_secure
    assert strong.band is Band.GHZ_24


def test_scan_lookup_and_digest():
    a = ap("A", "AA:BB:CC:00:00:01")
    b = ap("B", "AA:BB:CC:00:00:02")
    s = WifiScan(timestamp=10.0, aps=(a, b))
    assert s.count == 2
    assert s.by_bssid()["AA:BB:CC:00:00:01"].ssid == "A"
    assert s.by_ssid()["B"][0].bssid == "AA:BB:CC:00:00:02"
    assert s.id == WifiScan(timestamp=10.0, aps=(b, a)).id
