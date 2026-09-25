"""Exportador PDF con ReportLab (y gráficos con matplotlib si están).

Ambas dependencias son opcionales: si faltan, se lanza un error claro con la
instrucción de instalación en lugar de fallar de forma críptica.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from .base import ReportData, ReportDependencyError

_ACCENT = "#00B8A0"
_DARK = "#0A0E14"


def export_pdf(data: ReportData, destination: Path) -> Path:
    _import_reportlab()
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        str(destination),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=data.title,
        author="Aethernet",
    )
    story: list[Any] = []
    story.append(Paragraph(data.title, styles["Title"]))
    story.append(
        Paragraph(
            "Generado el " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data.generated_at)),
            styles["Italic"],
        )
    )
    story.append(Spacer(1, 8))

    if data.health:
        story.append(Paragraph(f"Salud: {data.health.total}/100 ({data.health.grade})", styles["Heading2"]))
        story.append(Paragraph(data.health.headline, styles["BodyText"]))
        story.extend(
            _table(
                [["Factor", "Puntuación", "Nota"]] + [[f.label, str(f.score), f.note] for f in data.health.factors],
                Table,
                TableStyle,
                colors,
            )
        )
        story.append(Spacer(1, 8))

    chart = _channel_chart(data)
    if chart is not None:
        story.append(Paragraph("Ocupación por canal", styles["Heading2"]))
        story.append(Image(str(chart), width=160 * mm, height=80 * mm))
        story.append(Spacer(1, 8))

    if data.recommendations:
        story.append(Paragraph("Recomendaciones", styles["Heading2"]))
        for rec in data.recommendations:
            story.append(Paragraph(f"• {rec}", styles["BodyText"]))
        story.append(Spacer(1, 8))

    if data.wifi and data.wifi.aps:
        story.append(Paragraph("Inventario WiFi", styles["Heading2"]))
        rows = [["SSID", "BSSID", "Canal", "Seguridad", "dBm"]]
        for ap in sorted(data.wifi.aps, key=lambda a: a.signal_dbm, reverse=True)[:40]:
            rows.append([ap.display_ssid[:24], data._mac(ap.bssid), str(ap.channel), ap.security, str(ap.signal_dbm)])
        story.extend(_table(rows, Table, TableStyle, colors))
        story.append(Spacer(1, 8))

    if data.events:
        story.append(Paragraph("Hallazgos recientes", styles["Heading2"]))
        for event in data.events[:25]:
            story.append(
                Paragraph(
                    f"<b>[{event.severity.value.upper()}]</b> {event.title}",
                    styles["BodyText"],
                )
            )
        story.append(Spacer(1, 8))

    if data.limits:
        story.append(Paragraph("Límites de tu hardware", styles["Heading2"]))
        for limit in data.limits:
            story.append(Paragraph(f"• {limit}", styles["BodyText"]))

    doc.build(story)
    _cleanup_chart(chart)
    return destination


def _import_reportlab() -> Any:
    try:
        import reportlab  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ReportDependencyError(
            "Para informes PDF instala las dependencias: pip install 'aethernet[reports]'"
        ) from exc
    return reportlab


def _table(rows: list[list[str]], Table: Any, TableStyle: Any, colors: Any) -> list[Any]:
    table = Table(rows, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_DARK)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F8")]),
            ]
        )
    )
    return [table]


def _channel_chart(data: ReportData) -> Path | None:
    """Genera un PNG temporal con la ocupación por canal; ``None`` si no hay matplotlib."""
    if not data.spectrum:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    occupancy = data.spectrum.get("occupancy") or []
    channels = [row["channel"] for row in occupancy]
    networks = [row["networks"] for row in occupancy]
    if not any(networks):
        return None

    figure, axis = plt.subplots(figsize=(8, 3.5), dpi=110)
    axis.bar([str(c) for c in channels], networks, color=_ACCENT)
    axis.set_xlabel("Canal")
    axis.set_ylabel("Redes")
    axis.set_title("Redes por canal")
    axis.grid(axis="y", color="#E0E0E0")
    figure.tight_layout()

    path = Path(tempfile.mkdtemp(prefix="aethernet-chart-")) / "chart.png"
    figure.savefig(path, transparent=False)
    plt.close(figure)
    return path


def _cleanup_chart(path: Path | None) -> None:
    import contextlib

    if path and path.exists():
        with contextlib.suppress(OSError):
            path.unlink()
