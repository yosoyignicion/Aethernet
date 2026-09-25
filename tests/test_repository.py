from __future__ import annotations

import time

from aethernet.models import Event, LanScan, Severity, Snapshot
from helpers import ap, device, scan


def _store_scan(repo, ts, *aps, my_bssids=None):
    s = scan(*aps, ts=ts)
    return repo.save_wifi_scan(s, my_bssids=my_bssids), s


def test_wifi_scan_roundtrip(repo):
    scan_id, original = _store_scan(repo, time.time(), ap("A", "AA:BB:CC:00:00:01", dbm=-42))
    assert repo.wifi_scan_count() == 1
    latest = repo.latest_wifi_scan()
    assert latest is not None
    assert latest.count == 1
    assert latest.aps[0].bssid == "AA:BB:CC:00:00:01"
    assert latest.aps[0].signal_dbm == -42
    assert repo.all_bssids() == {"AA:BB:CC:00:00:01"}
    assert repo.get_wifi_scan(scan_id).count == 1


def test_signal_history_and_channel_stats(repo):
    now = time.time()
    _store_scan(repo, now - 200, ap("A", "AA:BB:CC:00:00:01", dbm=-40, channel=6))
    _store_scan(repo, now - 100, ap("A", "AA:BB:CC:00:00:01", dbm=-55, channel=6))
    series = repo.signal_series("AA:BB:CC:00:00:01", hours=24)
    assert [s for _, s in series] == [-40, -55]
    stats = repo.channel_stats(hours=24)
    assert stats[0]["channel"] == 6
    assert stats[0]["samples"] == 2


def test_ap_first_seen_is_preserved(repo):
    now = time.time()
    _store_scan(repo, now - 400, ap("A", "AA:BB:CC:00:00:01", dbm=-40))
    _store_scan(repo, now - 100, ap("A", "AA:BB:CC:00:00:01", dbm=-45))
    known = repo.known_aps()[0]
    assert known.first_seen == now - 400
    assert known.last_seen == now - 100


def test_device_inventory_and_trust(repo):
    repo.save_lan_scan(LanScan(timestamp=1.0, devices=(device("00:11:22:33:44:55", "192.168.1.2"),)))
    repo.save_lan_scan(LanScan(timestamp=2.0, devices=(device("00:11:22:33:44:55", "192.168.1.2"),)))
    devices = repo.devices()
    assert len(devices) == 1
    assert not devices[0].trusted
    repo.set_device_trusted("00:11:22:33:44:55", True, "TV salón")
    updated = repo.devices()[0]
    assert updated.trusted
    assert updated.alias == "TV salón"
    assert "00:11:22:33:44:55" in repo.trusted_macs()


def test_ghost_devices(repo):
    repo.save_lan_scan(LanScan(timestamp=time.time() - 100 * 3600, devices=(device("00:11:22:33:44:55", "192.168.1.9"),)))
    ghosts = repo.ghost_devices(min_age_hours=24)
    assert len(ghosts) == 1


def test_events_dedup_and_read(repo):
    event = Event(severity=Severity.WARNING, title="X", fingerprint="fp1")
    event_id, created = repo.add_event(event, dedup_window_sec=3600)
    assert created
    same_id, created_again = repo.add_event(
        Event(severity=Severity.WARNING, title="X", fingerprint="fp1"), dedup_window_sec=3600
    )
    assert not created_again
    assert same_id == event_id
    assert repo.list_events()[0].dedup_count == 2
    assert repo.unread_count() == 1
    assert repo.mark_event_read(event_id) == 1
    assert repo.unread_count() == 0


def test_events_filter_by_severity(repo):
    repo.add_event(Event(severity=Severity.INFO, title="i"))
    repo.add_event(Event(severity=Severity.CRITICAL, title="c"))
    assert len(repo.list_events(min_severity=Severity.ALERT)) == 1


def test_snapshots_crud(repo):
    snap_id = repo.save_snapshot(Snapshot(kind="wifi", created_at=1.0, label="antes", digest="d", payload={"a": 1}))
    assert repo.get_snapshot(snap_id).label == "antes"
    assert len(repo.list_snapshots("wifi")) == 1
    assert repo.delete_snapshot(snap_id)


def test_kv_and_counts(repo):
    repo.kv_set("k", {"n": 1})
    assert repo.kv_get("k") == {"n": 1}
    _store_scan(repo, time.time(), ap("A", "AA:BB:CC:00:00:01"))
    counts = repo.counts()
    assert counts["visible_networks"] == 1
    assert counts["wifi_scans"] == 1


def test_purge_old(repo):
    _store_scan(repo, time.time() - 100 * 86400, ap("Old", "AA:BB:CC:00:00:09"))
    removed = repo.purge_old(days=90)
    assert removed["wifi_scans"] == 1
    assert repo.wifi_scan_count() == 0


def test_monitor_session_and_events(repo):
    session_id = repo.start_monitor_session("aemon0", [1, 6, 11], 100.0)
    repo.add_monitor_event(
        session_id=session_id, kind="deauth", ts=101.0, bssid="AA:BB:CC:00:00:01", source_mac="00:11:22:33:44:55", count=20
    )
    repo.add_monitor_event(session_id=session_id, kind="probe", ts=102.0, ssid="MiRed", count=1)
    events = repo.list_monitor_events(limit=10)
    assert len(events) == 2
    assert repo.monitor_stats()["deauth"] == 20
    assert repo.monitor_stats()["probe"] == 1
    repo.close_monitor_session(session_id, 42)
    assert repo.monitor_sessions()[0]["status"] == "stopped"
    assert repo.monitor_sessions()[0]["packet_count"] == 42


def test_event_evidence_roundtrip(repo):
    repo.add_event(Event(severity=Severity.WARNING, title="t", evidence={"bssid": "AA", "n": 3}))
    stored = repo.list_events()[0]
    assert stored.evidence == {"bssid": "AA", "n": 3}


def test_channel_advisory_history(repo):
    for hour in (0, 0, 13):
        repo.record_channel_advisory(
            ts=1000.0 + hour, hour=hour, weekday=5, band="2.4 GHz",
            best_channel=1, availability=100, interference=0.0, samples=4, ranking=[1, 6, 11],
        )
    assert repo.channel_advisory_count() == 3
    buckets = repo.channel_advisory_buckets()
    slot = [b for b in buckets if b["hour"] == 0]
    assert slot and slot[0]["n"] == 2
    assert repo.channel_advisory_recent(limit=2)
