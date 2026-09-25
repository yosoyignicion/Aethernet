"""Comparador de snapshots: qué cambió entre dos escaneos."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from ..models import AccessPoint, LanScan, Snapshot, WifiScan


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def wifi_snapshot(scan: WifiScan, label: str = "") -> Snapshot:
    payload = scan.to_dict()
    return Snapshot(
        kind="wifi",
        created_at=scan.timestamp,
        label=label or time.strftime("%Y-%m-%d %H:%M", time.localtime(scan.timestamp)),
        digest=_digest(payload),
        payload=payload,
    )


def lan_snapshot(scan: LanScan, label: str = "") -> Snapshot:
    payload = scan.to_dict()
    return Snapshot(
        kind="lan",
        created_at=scan.timestamp,
        label=label or time.strftime("%Y-%m-%d %H:%M", time.localtime(scan.timestamp)),
        digest=_digest(payload),
        payload=payload,
    )


def scan_from_payload(payload: dict[str, Any]) -> WifiScan:
    aps = tuple(AccessPoint.from_dict(a) for a in payload.get("aps", []))
    return WifiScan(
        timestamp=payload.get("timestamp", 0.0),
        interface=payload.get("interface", ""),
        aps=aps,
        source=payload.get("source", "snapshot"),
    )


@dataclass(slots=True)
class SnapshotDiff:
    old_label: str = ""
    new_label: str = ""
    new_aps: list[dict[str, Any]] = field(default_factory=list)
    removed_aps: list[dict[str, Any]] = field(default_factory=list)
    channel_changes: list[dict[str, Any]] = field(default_factory=list)
    signal_changes: list[dict[str, Any]] = field(default_factory=list)
    security_changes: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.new_aps
            or self.removed_aps
            or self.channel_changes
            or self.signal_changes
            or self.security_changes
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "old_label": self.old_label,
            "new_label": self.new_label,
            "has_changes": self.has_changes,
            "new_aps": self.new_aps,
            "removed_aps": self.removed_aps,
            "channel_changes": self.channel_changes,
            "signal_changes": self.signal_changes,
            "security_changes": self.security_changes,
        }

    def render(self) -> str:
        """Resumen en texto apto para CLI/informes."""
        lines: list[str] = []
        if self.new_aps:
            lines.append(f"Redes nuevas ({len(self.new_aps)}):")
            lines += [f"  + {ap['ssid'] or '<oculta>'} ({ap['bssid']}) ch{ap['channel']}" for ap in self.new_aps]
        if self.removed_aps:
            lines.append(f"Redes desaparecidas ({len(self.removed_aps)}):")
            lines += [f"  - {ap['ssid'] or '<oculta>'} ({ap['bssid']})" for ap in self.removed_aps]
        if self.channel_changes:
            lines.append(f"Cambios de canal ({len(self.channel_changes)}):")
            lines += [
                f"  ~ {c['ssid'] or c['bssid']}: {c['from']} → {c['to']}" for c in self.channel_changes
            ]
        if self.security_changes:
            lines.append(f"Cambios de seguridad ({len(self.security_changes)}):")
            lines += [
                f"  ~ {c['ssid'] or c['bssid']}: {c['from']} → {c['to']}" for c in self.security_changes
            ]
        if self.signal_changes:
            lines.append(f"Cambios de señal relevantes ({len(self.signal_changes)}):")
            lines += [
                f"  ~ {c['ssid'] or c['bssid']}: {c['from']} → {c['to']} dBm ({c['delta']:+d})"
                for c in self.signal_changes
            ]
        return "\n".join(lines) if lines else "Sin cambios entre los dos escaneos."


def diff_scans(
    old: WifiScan,
    new: WifiScan,
    *,
    signal_threshold: int = 10,
    old_label: str = "",
    new_label: str = "",
) -> SnapshotDiff:
    old_map = old.by_bssid()
    new_map = new.by_bssid()
    diff = SnapshotDiff(old_label=old_label, new_label=new_label)

    for bssid, ap in new_map.items():
        if bssid not in old_map:
            diff.new_aps.append(_ap_brief(ap))
    for bssid, ap in old_map.items():
        if bssid not in new_map:
            diff.removed_aps.append(_ap_brief(ap))
    for bssid, ap in new_map.items():
        previous = old_map.get(bssid)
        if previous is None:
            continue
        if previous.channel and ap.channel and previous.channel != ap.channel:
            diff.channel_changes.append(
                {"bssid": bssid, "ssid": ap.ssid, "from": previous.channel, "to": ap.channel}
            )
        delta = ap.signal_dbm - previous.signal_dbm
        if abs(delta) >= signal_threshold:
            diff.signal_changes.append(
                {
                    "bssid": bssid,
                    "ssid": ap.ssid,
                    "from": previous.signal_dbm,
                    "to": ap.signal_dbm,
                    "delta": delta,
                }
            )
        if previous.security != ap.security:
            diff.security_changes.append(
                {"bssid": bssid, "ssid": ap.ssid, "from": previous.security, "to": ap.security}
            )
    return diff


def diff_payloads(old_payload: dict[str, Any], new_payload: dict[str, Any], **kwargs: Any) -> SnapshotDiff:
    return diff_scans(scan_from_payload(old_payload), scan_from_payload(new_payload), **kwargs)


def _ap_brief(ap: AccessPoint) -> dict[str, Any]:
    return {
        "ssid": ap.ssid,
        "bssid": ap.bssid,
        "channel": ap.channel,
        "signal_dbm": ap.signal_dbm,
        "security": ap.security,
        "vendor": ap.vendor,
    }
