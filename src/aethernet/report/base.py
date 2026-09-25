"""Construcción del paquete de datos de un informe y utilidades comunes."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings
from ..core.adapter import hardware_suggestions, honest_limits
from ..core.health import score_health
from ..core.spectrum import spectrum_snapshot
from ..models import AdapterInfo, Event, HealthScore, LanDevice, Severity, WifiScan, to_json


class ReportDependencyError(RuntimeError):
    """Falta una dependencia opcional para generar este formato."""


def redact_mac(mac: str) -> str:
    """Conserva el OUI y oculta el resto: AA:BB:CC:XX:XX:XX."""
    parts = mac.split(":")
    if len(parts) != 6:
        return mac
    return ":".join(parts[:3] + ["XX", "XX", "XX"])


@dataclass(slots=True)
class ReportData:
    title: str
    generated_at: float
    settings: dict[str, Any] = field(default_factory=dict)
    wifi: WifiScan | None = None
    health: HealthScore | None = None
    events: list[Event] = field(default_factory=list)
    lan_devices: list[LanDevice] = field(default_factory=list)
    spectrum: dict[str, Any] | None = None
    adapter: AdapterInfo | None = None
    recommendations: list[str] = field(default_factory=list)
    limits: list[str] = field(default_factory=list)
    redact_macs: bool = False

    def _mac(self, mac: str) -> str:
        return redact_mac(mac) if self.redact_macs else mac

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "generated_at": self.generated_at,
            "generated_at_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.generated_at)),
            "settings": self.settings,
            "health": self.health.to_dict() if self.health else None,
            "wifi": _wifi_dict(self.wifi, self.redact_macs),
            "spectrum": self.spectrum,
            "lan": {
                "count": len(self.lan_devices),
                "devices": [_device_dict(d, self.redact_macs) for d in self.lan_devices],
            },
            "events": [e.to_dict() for e in self.events],
            "adapter": self.adapter.to_dict() if self.adapter else None,
            "limits": self.limits,
            "recommendations": self.recommendations,
        }

    def to_json(self) -> str:
        return to_json(self.to_dict())


def _wifi_dict(scan: WifiScan | None, redact: bool) -> dict[str, Any] | None:
    if scan is None:
        return None
    data = scan.to_dict()
    if redact:
        for ap in data.get("aps", []):
            ap["bssid"] = redact_mac(ap["bssid"])
    data["count"] = scan.count
    return data


def _device_dict(device: LanDevice, redact: bool) -> dict[str, Any]:
    data = device.to_dict()
    if redact:
        data["mac"] = redact_mac(data["mac"])
    return data


def build_report_data(
    repo,
    settings: Settings,
    *,
    title: str | None = None,
    event_limit: int = 50,
    min_severity: Severity | None = None,
) -> ReportData:
    """Reúne todos los datos persistidos en un único objeto serializable."""
    now = time.time()
    scan = repo.latest_wifi_scan()
    lan = repo.latest_lan_scan()
    history: dict[str, list[int]] = {}
    if scan is not None:
        for ap in scan.aps:
            points = repo.signal_series(ap.bssid, hours=48)
            history[ap.bssid] = [s for _, s in points]
    health = (
        score_health(
            scan,
            my_ssids=tuple(settings.my_ssids),
            my_bssids=tuple(settings.my_bssids),
            signal_history=history,
            now=now,
        )
        if scan is not None
        else None
    )
    events = repo.list_events(limit=event_limit, min_severity=min_severity)
    spectrum = spectrum_snapshot(scan) if scan is not None else None
    adapter = scan.adapter if scan is not None else None

    recommendations = build_recommendations(health, events, spectrum, adapter)
    limits = honest_limits(adapter)

    settings_snapshot = {
        "my_ssids": list(settings.my_ssids),
        "scan_mode": settings.scan_mode,
        "scan_interval_min": settings.scan_interval_min,
        "scanline_effect": settings.scanline_effect,
    }
    return ReportData(
        title=title or f"{settings.report_template_title} — {time.strftime('%Y-%m-%d', time.localtime(now))}",
        generated_at=now,
        settings=settings_snapshot,
        wifi=scan,
        health=health,
        events=events,
        lan_devices=list(lan.devices) if lan else repo.devices(),
        spectrum=spectrum,
        adapter=adapter,
        recommendations=recommendations,
        limits=limits,
        redact_macs=settings.redact_macs_in_reports,
    )


def build_recommendations(
    health: HealthScore | None,
    events: list[Event],
    spectrum: dict[str, Any] | None,
    adapter: AdapterInfo | None,
) -> list[str]:
    recs: list[str] = []
    if health is not None:
        for factor in health.factors:
            if factor.score < 70:
                recs.append(f"{factor.label}: {factor.note}")
    if spectrum:
        recommendation = spectrum.get("recommendation")
        if recommendation and recommendation.get("free_pct", 0) >= 60:
            recs.append(recommendation["reason"])
    for event in events:
        if event.severity.at_least(Severity.ALERT) and event.body:
            first_line = event.body.splitlines()[0]
            recs.append(f"{event.title}: {first_line}")
    recs.extend(hardware_suggestions(adapter))
    # deduplicar conservando orden
    seen: set[str] = set()
    unique: list[str] = []
    for rec in recs:
        if rec not in seen:
            seen.add(rec)
            unique.append(rec)
    return unique[:10]


def output_path(directory: Path, base: str, extension: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return directory / f"{base}-{stamp}.{extension}"
