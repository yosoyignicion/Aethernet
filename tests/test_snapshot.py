from __future__ import annotations

from aethernet.core.snapshot import (
    diff_payloads,
    diff_scans,
    lan_snapshot,
    scan_from_payload,
    wifi_snapshot,
)
from helpers import ap, scan


def test_diff_detects_new_and_removed():
    old = scan(ap("A", "AA:BB:CC:00:00:01"), ap("B", "AA:BB:CC:00:00:02"), ts=1)
    new = scan(ap("A", "AA:BB:CC:00:00:01"), ap("C", "AA:BB:CC:00:00:03"), ts=2)
    diff = diff_scans(old, new)
    assert [a["ssid"] for a in diff.new_aps] == ["C"]
    assert [a["ssid"] for a in diff.removed_aps] == ["B"]
    assert diff.has_changes


def test_diff_detects_channel_signal_security():
    old = scan(ap("A", "AA:BB:CC:00:00:01", channel=6, dbm=-40, security="wpa2"), ts=1)
    new = scan(ap("A", "AA:BB:CC:00:00:01", channel=11, dbm=-70, security="wpa3"), ts=2)
    diff = diff_scans(old, new)
    assert diff.channel_changes[0]["from"] == 6
    assert diff.channel_changes[0]["to"] == 11
    assert diff.signal_changes[0]["delta"] == -30
    assert diff.security_changes[0]["to"] == "wpa3"


def test_diff_no_changes_render():
    s = scan(ap("A", "AA:BB:CC:00:00:01"))
    diff = diff_scans(s, s)
    assert not diff.has_changes
    assert "Sin cambios" in diff.render()


def test_snapshot_roundtrip_payload():
    original = scan(ap("A", "AA:BB:CC:00:00:01"), ts=42)
    snap = wifi_snapshot(original, label="x")
    assert snap.kind == "wifi"
    restored = scan_from_payload(snap.payload)
    assert restored.count == 1
    assert restored.aps[0].bssid == "AA:BB:CC:00:00:01"
    assert snap.digest == wifi_snapshot(original).digest


def test_lan_snapshot_kind():
    from aethernet.models import LanScan

    snap = lan_snapshot(LanScan(timestamp=1.0))
    assert snap.kind == "lan"


def test_diff_payloads():
    old = wifi_snapshot(scan(ap("A", "AA:BB:CC:00:00:01"), ts=1)).payload
    new = wifi_snapshot(scan(ap("B", "AA:BB:CC:00:00:02"), ts=2)).payload
    diff = diff_payloads(old, new)
    assert diff.new_aps and diff.removed_aps
