from __future__ import annotations

from aethernet.config import Settings
from aethernet.models import LanScan
from aethernet.service.control import ControlChannel
from aethernet.service.daemon import MonitorService
from helpers import ap, device, scan

MINE = "AA:AA:AA:AA:AA:AA"
EVIL = "BB:BB:BB:BB:BB:BB"


def _service(repo, tmp_paths, *, wifi_scan, lan_scan=None):
    settings = Settings(
        notifications=False,
        sound=False,
        my_ssids=["MiRed"],
        my_bssids=[MINE],
        lan_scan_enabled=lan_scan is not None,
    )

    def scanner(interface=None, active=False):
        return wifi_scan

    def lan_scanner(interface=None, active=False, **kwargs):
        return lan_scan or LanScan(timestamp=wifi_scan.timestamp)

    return MonitorService(repo, settings, tmp_paths, scanner=scanner, lan_scanner=lan_scanner)


def test_scan_once_runs_rules_and_creates_events(repo, tmp_paths):
    wifi = scan(ap("MiRed", MINE, dbm=-45), ap("MiRed", EVIL, dbm=-50), ts=1000.0)
    service = _service(repo, tmp_paths, wifi_scan=wifi)
    result = service.scan_once()
    assert result.error is None
    assert result.scan is not None
    assert any(f.rule_id == "evil_twin" for f in result.findings)
    assert result.health is not None
    assert result.alerts is not None and result.alerts.created_count >= 1
    assert repo.unread_count() >= 1
    assert repo.wifi_scan_count() == 1
    assert service.status()["scan_count"] == 1


def test_scan_once_with_lan(repo, tmp_paths):
    wifi = scan(ap("MiRed", MINE, dbm=-45), ts=1000.0)
    lan = LanScan(timestamp=1000.0, devices=(device("00:11:22:33:44:55", "192.168.1.20"),))
    service = _service(repo, tmp_paths, wifi_scan=wifi, lan_scan=lan)
    result = service.scan_once()
    assert result.lan_scan is not None
    assert repo.latest_lan_scan().count == 1


def test_pause_resume_state(repo, tmp_paths):
    service = _service(repo, tmp_paths, wifi_scan=scan(ts=1.0))
    assert not service.paused
    assert service.toggle_pause() is True
    assert service.paused
    assert service.toggle_pause() is False


def test_control_channel_roundtrip(tmp_paths):
    channel = ControlChannel(tmp_paths.control_file)
    channel.send("scan")
    assert channel.poll() == "scan"
    assert channel.poll() is None


def test_monitor_uses_monitor_events(repo, tmp_paths):
    from aethernet.core.analysis import MonitorEvent

    service = _service(repo, tmp_paths, wifi_scan=scan(ap("MiRed", MINE), ts=1000.0))
    result = service.scan_once(
        monitor_events=[MonitorEvent(kind="deauth", timestamp=999.0, bssid=MINE, count=50)]
    )
    assert any(f.rule_id == "deauth_flood" for f in result.findings)
