from __future__ import annotations

import json

import pytest

from aethernet.config import Settings
from aethernet.models import Event, LanScan, Severity
from aethernet.report import build_report_data, export
from helpers import ap, device, scan


@pytest.fixture
def seeded(repo):
    repo.save_wifi_scan(
        scan(
            ap("MiRed", "AA:BB:CC:00:00:01", dbm=-45, security="wpa3"),
            ap("Vecino", "AA:BB:CC:00:00:02", channel=11, security="open"),
            ts=1.0,
        ),
        my_bssids={"AA:BB:CC:00:00:01"},
    )
    repo.save_wifi_scan(scan(ap("MiRed", "AA:BB:CC:00:00:01", dbm=-55), ts=2.0))
    repo.save_lan_scan(LanScan(timestamp=2.0, devices=(device("00:11:22:33:44:55", "192.168.1.20"),)))
    repo.add_event(Event(severity=Severity.WARNING, title="Red abierta nueva", body="detalle"))
    return repo


def test_report_data_shape(seeded):
    data = build_report_data(seeded, Settings())
    payload = data.to_dict()
    assert payload["wifi"]["count"] >= 1
    assert payload["lan"]["count"] == 1
    assert payload["events"]
    assert payload["health"] is not None
    assert payload["recommendations"]


def test_export_markdown(seeded, tmp_path):
    data = build_report_data(seeded, Settings())
    path = export(data, "markdown", tmp_path / "informe.md")[0]
    text = path.read_text(encoding="utf-8")
    assert "# " in text
    assert "Resumen ejecutivo" in text
    assert "Inventario WiFi" in text
    assert "MiRed" in text


def test_export_json(seeded, tmp_path):
    data = build_report_data(seeded, Settings())
    path = export(data, "json", tmp_path / "informe.json")[0]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["wifi"]["count"] >= 1
    assert payload["lan"]["count"] == 1


def test_export_csv(seeded, tmp_path):
    data = build_report_data(seeded, Settings())
    paths = export(data, "csv", tmp_path / "informe.csv")
    assert len(paths) == 2
    nets = next(p for p in paths if "redes" in p.name).read_text(encoding="utf-8")
    devices = next(p for p in paths if "dispositivos" in p.name).read_text(encoding="utf-8")
    assert "ssid" in nets and "MiRed" in nets
    assert "mac" in devices and "00:11:22:33:44:55" in devices


def test_export_redacts_macs(seeded, tmp_path):
    data = build_report_data(seeded, Settings(redact_macs_in_reports=True))
    path = export(data, "json", tmp_path / "redact.json")[0]
    payload = json.loads(path.read_text(encoding="utf-8"))
    bssids = [ap["bssid"] for ap in payload["wifi"]["aps"]]
    assert bssids and all(b.endswith("XX:XX:XX") for b in bssids)


def test_export_pdf(seeded, tmp_path):
    pytest.importorskip("reportlab")
    data = build_report_data(seeded, Settings())
    path = export(data, "pdf", tmp_path / "informe.pdf")[0]
    assert path.exists()
    assert path.read_bytes()[:4] == b"%PDF"
