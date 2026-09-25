"""Exportador Markdown: legible en el móvil o subible a un repo."""

from __future__ import annotations

import time
from pathlib import Path

from ..models import Severity
from ..utils import humanize_age
from .base import ReportData

_SEVERITY_LABEL = {
    Severity.INFO: "INFO",
    Severity.WARNING: "AVISO",
    Severity.ALERT: "ALERTA",
    Severity.CRITICAL: "CRÍTICO",
}


def export_markdown(data: ReportData, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_markdown(data), encoding="utf-8")
    return destination


def render_markdown(data: ReportData) -> str:
    lines: list[str] = []
    lines.append(f"# {data.title}")
    lines.append("")
    generated = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data.generated_at))
    lines.append(f"_Generado el {generated}._")
    lines.append("")

    lines.extend(_executive_summary(data))
    lines.extend(_health_section(data))
    lines.extend(_recommendations(data))
    lines.extend(_spectrum_section(data))
    lines.extend(_wifi_section(data))
    lines.extend(_lan_section(data))
    lines.extend(_events_section(data))
    lines.extend(_limits_section(data))

    lines.append("---")
    lines.append("")
    lines.append(
        "> Aethernet es honesto por diseño: informa de lo que observa con este "
        "hardware, no promete seguridad absoluta. Todo es local; ninguna dato salió de tu equipo."
    )
    lines.append("")
    return "\n".join(lines)


def _executive_summary(data: ReportData) -> list[str]:
    lines = ["## Resumen ejecutivo", ""]
    if data.health:
        lines.append(
            f"**Salud de la red: {data.health.total}/100 ({data.health.grade}).** "
            f"{data.health.headline}"
        )
    else:
        lines.append("Todavía no hay escaneos guardados.")
    lines.append("")
    wifi_count = data.wifi.count if data.wifi else 0
    untrusted = sum(1 for d in data.lan_devices if not d.trusted and not d.is_gateway)
    critical = sum(1 for e in data.events if e.severity is Severity.CRITICAL)
    lines.append("| Métrica | Valor |")
    lines.append("| --- | --- |")
    lines.append(f"| Redes visibles | {wifi_count} |")
    lines.append(f"| Dispositivos LAN | {len(data.lan_devices)} |")
    lines.append(f"| Dispositivos no confiables | {untrusted} |")
    lines.append(f"| Eventos en el informe | {len(data.events)} |")
    lines.append(f"| Eventos críticos | {critical} |")
    lines.append("")
    return lines


def _health_section(data: ReportData) -> list[str]:
    if not data.health or not data.health.factors:
        return []
    lines = ["## Salud por factor", "", "| Factor | Puntuación | Peso | Nota |", "| --- | ---: | ---: | --- |"]
    for factor in data.health.factors:
        lines.append(
            f"| {factor.label} | {factor.score} | {factor.weight:.0%} | {factor.note} |"
        )
    lines.append("")
    return lines


def _recommendations(data: ReportData) -> list[str]:
    if not data.recommendations:
        return []
    lines = ["## Recomendaciones", ""]
    lines.extend(f"- {rec}" for rec in data.recommendations)
    lines.append("")
    return lines


def _spectrum_section(data: ReportData) -> list[str]:
    if not data.spectrum:
        return []
    rec = data.spectrum.get("recommendation") or {}
    lines = ["## Espectro", ""]
    if rec:
        lines.append(f"**Recomendación de canal:** {rec.get('reason', '')}")
        lines.append("")
    occupancy = data.spectrum.get("occupancy") or []
    busy = [row for row in occupancy if row.get("networks")]
    if busy:
        lines += ["| Canal | Redes | Señal media (dBm) |", "| ---: | ---: | ---: |"]
        for row in busy:
            lines.append(f"| {row['channel']} | {row['networks']} | {row.get('avg_dbm') or '-'} |")
        lines.append("")
    return lines


def _wifi_section(data: ReportData) -> list[str]:
    if not data.wifi or not data.wifi.aps:
        return []
    lines = ["## Inventario WiFi", "", "| SSID | BSSID | Fabricante | Canal | Banda | Seguridad | dBm | Etiquetas |",
             "| --- | --- | --- | ---: | --- | --- | ---: | --- |"]
    for ap in sorted(data.wifi.aps, key=lambda a: a.signal_dbm, reverse=True):
        tags = ", ".join(ap.tags) if ap.tags else ("oculta" if ap.hidden else "")
        lines.append(
            f"| {ap.display_ssid} | {data._mac(ap.bssid)} | {ap.vendor or '-'} | {ap.channel} | "
            f"{ap.band.value} | {ap.security} | {ap.signal_dbm} | {tags} |"
        )
    lines.append("")
    return lines


def _lan_section(data: ReportData) -> list[str]:
    if not data.lan_devices:
        return []
    lines = ["## Inventario LAN", "", "| Nombre | IP | MAC | Fabricante | Confiable | Estado |",
             "| --- | --- | --- | --- | :---: | --- |"]
    for device in data.lan_devices:
        status = "online" if device.online else "ausente"
        if device.is_gateway:
            status += " · router"
        lines.append(
            f"| {device.display_name} | {device.ip} | {data._mac(device.mac)} | {device.vendor or '-'} | "
            f"{'sí' if device.trusted else 'no'} | {status} |"
        )
    lines.append("")
    return lines


def _events_section(data: ReportData) -> list[str]:
    if not data.events:
        return []
    lines = ["## Hallazgos y eventos", ""]
    for event in data.events:
        label = _SEVERITY_LABEL.get(event.severity, event.severity.value)
        lines.append(f"### [{label}] {event.title} · {humanize_age(time.time() - event.created_at)}")
        if event.body:
            lines.append("")
            lines.append(event.body)
        if event.dedup_count > 1:
            lines.append("")
            lines.append(f"_Repetido {event.dedup_count} veces._")
        lines.append("")
    return lines


def _limits_section(data: ReportData) -> list[str]:
    if not data.limits:
        return []
    lines = ["## Límites de tu hardware", ""]
    lines.extend(f"- {limit}" for limit in data.limits)
    lines.append("")
    lines.append("_Lo que no aparece aquí simplemente no puede detectarse con este adaptador._")
    lines.append("")
    return lines
