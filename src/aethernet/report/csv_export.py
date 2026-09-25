"""Exportador CSV: un archivo para redes y otro para dispositivos."""

from __future__ import annotations

import csv
from pathlib import Path

from .base import ReportData


def export_csv(data: ReportData, destination: Path) -> list[Path]:
    """Escribe ``<destino>_redes.csv`` y ``<destino>_dispositivos.csv``."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    stem = destination.with_suffix("")
    wifi_path = Path(f"{stem}_redes.csv")
    lan_path = Path(f"{stem}_dispositivos.csv")

    with wifi_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["ssid", "bssid", "vendor", "canal", "banda", "seguridad", "señal_dbm", "calidad", "oculta", "wps", "etiquetas"]
        )
        if data.wifi:
            for ap in sorted(data.wifi.aps, key=lambda a: a.signal_dbm, reverse=True):
                writer.writerow(
                    [
                        ap.ssid,
                        data._mac(ap.bssid),
                        ap.vendor or "",
                        ap.channel,
                        ap.band.value,
                        ap.security,
                        ap.signal_dbm,
                        ap.quality,
                        int(ap.hidden),
                        int(ap.wps),
                        "|".join(ap.tags),
                    ]
                )

    with lan_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["mac", "ip", "hostname", "vendor", "alias", "confiable", "online", "gateway"])
        for device in data.lan_devices:
            writer.writerow(
                [
                    data._mac(device.mac),
                    device.ip,
                    device.hostname or "",
                    device.vendor or "",
                    device.alias or "",
                    int(device.trusted),
                    int(device.online),
                    int(device.is_gateway),
                ]
            )
    return [wifi_path, lan_path]
