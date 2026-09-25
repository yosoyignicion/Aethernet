from __future__ import annotations

import pytest

pytest.importorskip("scapy")

from scapy.layers.dot11 import Dot11, Dot11Deauth  # noqa: E402

from aethernet.core.monitor.capture import MonitorCapture  # noqa: E402

BSSID = "aa:bb:cc:00:00:01"
SRC = "00:11:22:33:44:55"


def _deauth_packet():
    return Dot11(type=0, subtype=12, addr1="ff:ff:ff:ff:ff:ff", addr2=SRC, addr3=BSSID) / Dot11Deauth(reason=7)


def test_capture_pipeline_persists_and_emits(repo):
    seen = []
    capture = MonitorCapture(
        repo,
        "wlan0",
        [1],
        deauth_threshold=3,
        on_event=seen.append,
    )
    capture._session_id = repo.start_monitor_session("aemon0", [1], 0.0)

    packet = _deauth_packet()
    for _ in range(3):
        capture._on_packet(packet)

    assert capture.status().packet_count == 3
    assert len(seen) == 1
    assert seen[0].kind == "deauth"
    rows = repo.list_monitor_events()
    assert len(rows) == 1
    assert rows[0]["kind"] == "deauth"
    assert repo.monitor_stats()["deauth"] == 3
    assert capture.recent_evidence(1)
    assert "deauth" in capture.recent_evidence(1)[0]["hexdump"]


def test_capture_drain_returns_pending(repo):
    capture = MonitorCapture(repo, "wlan0", [1], deauth_threshold=1)
    capture._session_id = repo.start_monitor_session("aemon0", [1], 0.0)
    capture._on_packet(_deauth_packet())
    drained = capture.drain()
    assert len(drained) == 1
    assert capture.drain() == []
