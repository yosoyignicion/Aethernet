"""Informe de canal 2.4 GHz: situación, comparativa y previsión por hora."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..config import Settings
from ..core.forecast import WEEKDAYS, coverage, weekly_grid
from ..core.spectrum import advise_channel_change, channel_table
from ..models import Band


def render_channel_markdown(
    repo: Any, settings: Settings, *, band: Band = Band.GHZ_24, hours: int = 6
) -> str:
    stats = repo.channel_stats(hours=hours)
    table = channel_table(stats, band)
    best = min(table, key=lambda r: r["rank"]) if table else None
    current = int(settings.my_channel or 0)
    advice = (
        advise_channel_change(table, current, settings.channel_watch_min_improvement)
        if current
        else None
    )
    buckets = repo.channel_advisory_buckets(band.value)
    cov = coverage(buckets)
    grid = weekly_grid(buckets, time.localtime().tm_wday)

    lines: list[str] = []
    lines.append(f"# Informe de canal {band.value} — {_stamp()}")
    lines.append("")
    lines.append("## Situación")
    lines.append("")
    if current:
        lines.append(f"- **Tu canal actual:** CH{current:02d}")
    else:
        lines.append("- **Tu canal actual:** sin definir (configúralo en Ajustes/Espectro)")
    if best:
        lines.append(f"- **Mejor observado:** CH{best['channel']:02d} ({best['availability']}% disponible)")
    if advice:
        lines.append(
            f"- **Recomendación:** cambiar a CH{advice['recommended']:02d} → menos interferencia "
            f"~{advice['improvement_pct']}% ({advice['current_availability']}% → "
            f"{advice['recommended_availability']}% disponibilidad)."
        )
    elif current and best and current == best["channel"]:
        lines.append("- **Recomendación:** tu canal actual ya es el mejor observado.")
    else:
        lines.append("- **Recomendación:** sin mejora clara en la ventana observada.")
    lines.append("")

    lines.append(f"## Comparativa por canal (últimas {hours} h)")
    lines.append("")
    lines.append("| Canal | Ranking | Redes | Interferencia | Disponibilidad |")
    lines.append("| ---: | ---: | ---: | ---: | ---: |")
    for row in sorted(table, key=lambda r: r["rank"]):
        mark = " ← tu canal" if row["channel"] == current else ""
        star = " ⭐" if best and row["channel"] == best["channel"] else ""
        lines.append(
            f"| CH{row['channel']:02d} | #{row['rank']} | {row['networks']} | "
            f"{row['interference']} | {row['availability']}%{mark}{star} |"
        )
    lines.append("")

    lines.append("## Previsión por hora (hoy · " + WEEKDAYS[time.localtime().tm_wday] + ")")
    lines.append("")
    lines.append(f"Cobertura histórica: {cov['slots']}/{cov['slots_total']} franjas · {cov['observations']} observaciones.")
    lines.append("")
    lines.append("| Hora | Canal previsto | Disponibilidad | Muestras |")
    lines.append("| ---: | ---: | ---: | ---: |")
    for entry in grid["hours"]:
        channel = entry["channel"]
        label = f"CH{channel:02d}" if channel else "—"
        lines.append(f"| {entry['hour']:02d}:00 | {label} | {entry['availability']}% | {entry['samples']} |")
    lines.append("")
    lines.append(
        "> Aethernet mide y recomienda; **no cambia tu router**. Aplica el canal en el panel de "
        "administración. La previsión necesita varios días de historial para ser fiable."
    )
    lines.append("")
    return "\n".join(lines)


def export_channel_markdown(repo: Any, settings: Settings, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_channel_markdown(repo, settings), encoding="utf-8")
    return destination


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime())
