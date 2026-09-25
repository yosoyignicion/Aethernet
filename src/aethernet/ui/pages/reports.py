"""Informes: configuración de exportación y vista previa en tiempo real."""

from __future__ import annotations

import socket
import time

from nicegui import ui

from ...report.base import build_report_data
from ...report.markdown import render_markdown
from .. import charts
from ..components import label_caps, panel_header, toast
from ..shell import shell
from ..state import get_context, severity_label
from ..theme import COLORS, SEVERITY_COLORS, icon

_PRESETS = {"24H": 24, "07D": 7 * 24, "30D": 30 * 24, "90D": 90 * 24}
_FORMATS = (
    ("markdown", "MARKDOWN (.MD)", "code", "M"),
    ("pdf", "DOCUMENTO PDF (.PDF)", "picture_as_pdf", "P"),
    ("json", "DATASET JSON (.JSON)", "data_object", "J"),
    ("csv", "TABLA CSV (.CSV)", "table_chart", "C"),
)


@ui.page("/informes")
def reports_page() -> None:
    context = get_context()
    with shell("/informes", "Informes"):
        state = {"preset": "07D", "modules": {"congestion", "inventory", "incidents", "untrusted"}}

        with ui.element("div").classes("ae-panel flex flex-wrap items-center justify-between gap-3"):
            with ui.row().classes("items-center gap-3"):
                ui.html(icon("description", size=22, color=COLORS["cyan"]))
                with ui.column().classes("gap-0"):
                    ui.label("Informes y Auditoría RF").classes("ae-headline text-lg text-[#dfe2eb]")
                    label_caps("SYS.AUDIT // COMPLIANCE & EXPORT")
            with ui.row().classes("items-center gap-2"):
                label_caps(f"NODO LOCAL: {socket.gethostname().upper()}")

        with ui.element("div").classes("grid grid-cols-1 xl:grid-cols-12 gap-5 w-full"):
            # -- configuración ------------------------------------------#
            with ui.element("div").classes("xl:col-span-5 flex flex-col gap-5"):
                with ui.element("div").classes("ae-panel flex flex-col gap-2"):
                    label_caps("01. RANGO DE OBSERVACIÓN")
                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        for code, text in (("24H", "Últimas 24 Horas"), ("07D", "7 Días"), ("30D", "30 Días"), ("90D", "Ciclo Orbital")):
                            active = state["preset"] == code
                            chip = ui.html(text).classes("ae-chip" + (" active" if active else "")).style("cursor:pointer")
                            chip.on("click", lambda _=None, c=code: set_preset(c))
                with ui.element("div").classes("ae-panel flex flex-col gap-2"):
                    label_caps("02. MÓDULOS DE TELEMETRÍA")
                    for key, text in (
                        ("congestion", "Matriz de congestión espectral"),
                        ("inventory", "Inventario exhaustivo BSSID"),
                        ("incidents", "Bitácora de incidentes críticos"),
                        ("untrusted", "Auditoría de dispositivos no confiables"),
                    ):
                        switch = ui.checkbox(text, value=key in state["modules"]).props("dense")
                        switch.on_value_change(lambda e, k=key: toggle_module(k, e.value))
                with ui.element("div").classes("ae-panel flex flex-col gap-3"):
                    label_caps("03. EJECUCIÓN DE EXPORTACIÓN")
                    with ui.element("div").classes("grid grid-cols-2 gap-3"):
                        for fmt, label, icon_name, key in _FORMATS:
                            card = ui.element("div").classes("ae-card flex flex-col items-center gap-2 py-5 cursor-pointer")
                            with card:
                                ui.html(icon(icon_name, size=26, color=COLORS["mint"]))
                                ui.label(label).classes("ae-label")
                                label_caps(f"atajo {key}")
                            card.on("click", lambda _=None, f=fmt: do_export(f))

            # -- vista previa -------------------------------------------#
            with ui.element("div").classes("xl:col-span-7 ae-panel flex flex-col gap-3"):
                with ui.row().classes("items-center justify-between w-full"):
                    label_caps("DOCUMENTO RENDERIZADO EN TIEMPO REAL")
                    copy_btn = ui.button("Copiar MD crudo", icon="content_copy").props("flat dense no-caps").style(
                        f"color:{COLORS['cyan']}"
                    )
                preview = ui.element("div").classes("w-full overflow-auto ae-sub p-4").style("max-height:620px")
                with preview:
                    markdown_box = ui.markdown("").classes("text-[#dfe2eb] max-w-none")

            summary_row = ui.row().classes("xl:col-span-12 grid grid-cols-1 md:grid-cols-3 gap-4 w-full")
            with summary_row:
                summary_cards = ui.element("div").classes("contents")
            with ui.element("div").classes("xl:col-span-7 ae-panel flex flex-col gap-3"):
                panel_header("bar_chart", "Distribución de Ocupación por Canal", "REDES DETECTADAS POR CANAL (2.4 GHZ)", COLORS["mint"])
                occupancy_chart = ui.echart(charts.occupancy_report_bars([0], ["—"])).classes("w-full").style("height:220px")
            with ui.element("div").classes("xl:col-span-5 ae-panel flex flex-col gap-3"):
                panel_header("warning", "Bitácora de Incidentes", "EVENTOS EN LA VENTANA", COLORS["coral"])
                incidents = ui.element("div").classes("flex flex-col gap-2 w-full")

        # -- lógica -----------------------------------------------------#
        def set_preset(code: str) -> None:
            state["preset"] = code
            render()

        def toggle_module(key: str, enabled: bool) -> None:
            if enabled:
                state["modules"].add(key)
            else:
                state["modules"].discard(key)
            render()

        def do_export(fmt: str) -> None:
            try:
                paths = context.export_report(fmt)
                toast(f"Exportado: {paths[0].name}", icon_name="download")
            except Exception as exc:  # noqa: BLE001
                toast(f"No se pudo exportar: {exc}", icon_name="error", color=COLORS["coral"])

        async def copy_raw() -> None:
            data = build_report_data(context.repo, context.settings)
            await ui.run_javascript(
                f"navigator.clipboard.writeText({render_markdown(data)!r})", timeout=2.0
            )
            toast("Portapapeles actualizado", icon_name="content_copy")

        copy_btn.on("click", copy_raw)

        def render() -> None:
            hours = _PRESETS[state["preset"]]
            data = build_report_data(context.repo, context.settings, event_limit=200)
            markdown_box.set_content(render_markdown(data))

            summary_cards.clear()
            with summary_cards:
                _summary_card("ESTADO DE RED", data.health.grade.upper() if data.health else "—", f"{data.health.total}/100" if data.health else "sin datos", COLORS["mint"])
                _summary_card("REDES VISIBLES", str(data.wifi.count if data.wifi else 0), f"{hours} h de ventana", COLORS["cyan"])
                _summary_card("INCIDENTES", str(len(data.events)), "eventos en bitácora", COLORS["amber"])

            occupancy = (data.spectrum or {}).get("occupancy", [])[:14]
            values = [row["networks"] for row in occupancy]
            labels = [f"{row['channel']:02d}" for row in occupancy]
            peak = values.index(max(values)) if values and max(values) > 0 else None
            charts.update(occupancy_chart, charts.occupancy_report_bars(values or [0], labels or ["—"], peak))

            incidents.clear()
            with incidents:
                if not data.events:
                    ui.label("Sin incidentes registrados.").classes("text-[11px] text-[#94A3B8]")
                for event in data.events[:8]:
                    color = SEVERITY_COLORS[event.severity]
                    with ui.row().classes("items-center justify-between w-full ae-sub px-3 py-2"):
                        with ui.column().classes("gap-0 min-w-0"):
                            ui.label(event.title).classes("text-[12px] text-[#dfe2eb] truncate max-w-[240px]")
                            label_caps(time.strftime("%m-%d %H:%M", time.localtime(event.created_at)))
                        ui.html(f'<span class="ae-chip" style="color:{color};border-color:{color}">{severity_label(event.severity)}</span>')

        render()
        ui.timer(10.0, render)


def _summary_card(label: str, value: str, hint: str, color: str) -> None:
    with ui.element("div").classes("ae-card flex flex-col gap-2"):
        label_caps(label)
        ui.label(value).classes("ae-metric text-2xl").style(f"color:{color}")
        ui.label(hint).classes("text-[11px] text-[#94A3B8]")
