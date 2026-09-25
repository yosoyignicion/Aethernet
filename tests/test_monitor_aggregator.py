from __future__ import annotations

from aethernet.core.monitor.aggregator import MonitorAggregator
from aethernet.core.monitor.frames import (
    KIND_BEACON,
    KIND_DEAUTH,
    KIND_EAPOL,
    KIND_PROBE,
    DecodedFrame,
)


def _deauth(bssid="AA:BB:CC:00:00:01", source="00:11:22:33:44:55") -> DecodedFrame:
    return DecodedFrame(kind=KIND_DEAUTH, bssid=bssid, source_mac=source)


def _probe(ssid="MiRed", source="00:11:22:33:44:55", rssi=-55) -> DecodedFrame:
    return DecodedFrame(kind=KIND_PROBE, ssid=ssid, source_mac=source, rssi=rssi)


def test_deauth_threshold_emits_at_multiple():
    agg = MonitorAggregator(window_s=10, deauth_threshold=3)
    events = []
    for i in range(5):
        events += agg.add(_deauth(source=f"00:00:00:00:00:{i:02x}"), ts=100.0)
    # 5 deauth desde fuentes distintas no cruzan el umbral por clave
    assert events == []
    events = []
    for i in range(3):
        events += agg.add(_deauth(), ts=100.0 + i)
    assert len(events) == 1
    assert events[0].kind == KIND_DEAUTH
    assert events[0].count == 3


def test_deauth_window_prunes():
    agg = MonitorAggregator(window_s=1, deauth_threshold=3)
    for _ in range(2):
        agg.add(_deauth(), ts=100.0)
    # fuera de ventana: se descartan los antiguos
    events = agg.add(_deauth(), ts=200.0)
    assert events == []


def test_probe_emits_on_first_and_aggregates():
    agg = MonitorAggregator(window_s=10, probe_min_rssi=-80)
    first = agg.add(_probe(), ts=1.0)
    assert len(first) == 1 and first[0].kind == KIND_PROBE and first[0].count == 1
    assert agg.add(_probe(), ts=2.0) == []
    emitted = []
    for step in range(8):  # llega a 10 acumulados
        emitted += agg.add(_probe(), ts=3.0 + step)
    assert emitted and emitted[0].count == 10


def test_probe_below_rssi_floor_ignored():
    agg = MonitorAggregator(probe_min_rssi=-80)
    assert agg.add(_probe(rssi=-95), ts=1.0) == []


def test_beacon_once_per_window():
    agg = MonitorAggregator(window_s=10)
    frame = DecodedFrame(kind=KIND_BEACON, bssid="AA:BB:CC:00:00:02", ssid="X", channel=6)
    assert len(agg.add(frame, ts=1.0)) == 1
    assert agg.add(frame, ts=2.0) == []
    assert len(agg.add(frame, ts=20.0)) == 1


def test_eapol_emits():
    agg = MonitorAggregator()
    frame = DecodedFrame(kind=KIND_EAPOL, bssid="AA:BB:CC:00:00:03", source_mac="00:11:22:33:44:55")
    events = agg.add(frame, ts=1.0)
    assert events and events[0].kind == KIND_EAPOL


def test_flush_emits_pending_probes():
    agg = MonitorAggregator(window_s=5)
    agg.add(_probe(), ts=1.0)
    flushed = agg.flush(ts=100.0)
    assert flushed and flushed[0].kind == KIND_PROBE
