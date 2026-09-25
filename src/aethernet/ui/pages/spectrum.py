"""Espectro: distribución por canal, heatmap 24h y diagnóstico de canal."""

from __future__ import annotations

from nicegui import ui

from ...core.spectrum import heatmap as build_heatmap
from ...core.spectrum import occupancy, polar_points, recommend_channel
from ...models import Band
from .. import charts
from ..components import empty_state, kv_row, label_caps, panel_header, status_dot
from ..shell import shell
from ..state import fmt_dbm, get_context
from ..theme import COLORS


@ui.page("/espectro")
def spectrum_page() -> None:
    context = get_context()
    with shell("/espectro", "Espectro"):
        selected = {"band": Band.GHZ_24}

        with ui.element("div").classes("ae-panel flex flex-wrap items-center justify-between gap-3"):
            with ui.row().classes("items-center gap-3"):
                label_caps("MÓDULO:")
                ui.label("RF_SPECTRUM_ANALYZER").classes("ae-mono text-sm text-[#dfe2eb]")
                band_toggle = ui.toggle(
                    {Band.GHZ_24: "2.4 GHz [CH 1-13]", Band.GHZ_5: "5 GHz [U-NII]"},
                    value=Band.GHZ_24,
                ).props("no-caps dense")
            with ui.row().classes("items-center gap-4 ae-mono text-[11px] text-[#94A3B8]"):
                ui.html('SWEEP: <span style="color:#94A3B8">n/d</span>')
                ui.html('RBW: <span style="color:#94A3B8">n/d</span> · requiere monitor mode')

        @ui.refreshable
        def body() -> None:
            scan = context.last_scan()
            if scan is None:
                empty_state("Sin escaneos. Pulsa 'Forzar escaneo' en el Dashboard.", "signal_cellular_alt")
                return
            band = selected["band"]
            occupancy_rows = occupancy(scan, band)
            recommendation = recommend_channel(scan, band)

            with ui.element("div").classes("grid grid-cols-1 lg:grid-cols-12 gap-5 w-full"):
                with ui.element("div").classes("lg:col-span-8 flex flex-col gap-5"):
                    with ui.element("div").classes("ae-panel flex flex-col gap-3"):
                        panel_header("bar_chart", "DISTRIBUCIÓN DE POTENCIA POR CANAL", f"BANCO DE CANALES // {band.value}", COLORS["mint"])
                        with ui.row().classes("items-center gap-4"):
                            for text, color in (("Bajo ruido", COLORS["cyan"]), ("Pico", COLORS["amber"]), ("Recomendado", COLORS["mint"])):
                                with ui.row().classes("items-center gap-1"):
                                    ui.element("div").style(f"width:10px;height:4px;border-radius:2px;background:{color}")
                                    label_caps(text)
                        ui.echart(
                            charts.channel_bars(occupancy_rows, recommendation["channel"])
                        ).classes("w-full").style("height:280px")

                    with ui.element("div").classes("ae-panel flex flex-col gap-3"):
                        panel_header("grid_on", "MAPA DE CALOR ESPECTRAL 24 HORAS", "OCUPACIÓN POR CANAL Y HORA // OBSERVACIONES REALES", COLORS["cyan"])
                        grid = build_heatmap(context.repo.hourly_channel_matrix(168))
                        if not grid["channels"]:
                            empty_state("Aún no hay suficiente histórico para el heatmap.", "grid_on")
                        else:
                            ui.echart(charts.heatmap(grid)).classes("w-full").style("height:320px")

                with ui.element("div").classes("lg:col-span-4 flex flex-col gap-5"):
                    with ui.element("div").classes("ae-panel flex flex-col gap-3"):
                        with ui.row().classes("items-center justify-between w-full"):
                            label_caps("DIAGNÓSTICO AUTOMÁTICO")
                            status_dot(COLORS["mint"])
                        label_caps("RECOMENDACIÓN DE CANAL")
                        with ui.row().classes("items-baseline gap-2"):
                            ui.label(f"CANAL {recommendation['channel']}").classes("ae-metric text-2xl").style(
                                f"color:{COLORS['mint']}"
                            )
                            ui.label(f"{recommendation['free_pct']}% LIBRE").classes("ae-mono text-sm").style(
                                f"color:{COLORS['amber']}"
                            )
                        ui.label(recommendation["reason"]).classes("text-[12px] text-[#94A3B8]")
                        ui.element("div").classes("ae-divider")
                        kv_row("RELACIÓN S/R (SNR)", "n/d", COLORS["text-muted"])
                        kv_row("RUIDO DE FONDO", "n/d", COLORS["text-muted"])
                        overlapping = [ap for ap in scan.aps if ap.channel == recommendation["channel"]]
                        kv_row("REDES EN CANAL RECOMENDADO", str(len(overlapping)), COLORS["cyan"])
                        ui.label(
                            "SNR y ruido de fondo requieren monitor mode; con el hardware actual solo "
                            "medimos ocupación por canal."
                        ).classes("text-[11px] text-[#475569] italic")

                    with ui.element("div").classes("ae-panel flex flex-col gap-2"):
                        target_channel = recommendation["channel"]
                        interfering = sorted(
                            [ap for ap in scan.aps if ap.channel == target_channel],
                            key=lambda a: a.signal_dbm,
                            reverse=True,
                        )[:6]
                        panel_header("cell_tower", "CO-INTERFERENCIA", f"{len(interfering)} DETECTADAS EN CH {target_channel}", COLORS["amber"])
                        if not interfering:
                            empty_state("Canal limpio.", "check_circle")
                        for ap in interfering:
                            with ui.row().classes("items-center justify-between w-full py-1 border-b border-[#232A36]"):
                                with ui.column().classes("gap-0 min-w-0"):
                                    ui.label(ap.display_ssid).classes("ae-mono text-[12px] text-[#dfe2eb] truncate max-w-[150px]")
                                    label_caps(ap.bssid)
                                ui.label(fmt_dbm(ap.signal_dbm)).classes("ae-mono text-[12px]").style(
                                    f"color:{COLORS['amber'] if ap.signal_dbm > -70 else COLORS['text-dim']}"
                                )

                    with ui.element("div").classes("ae-panel flex flex-col gap-3"):
                        panel_header("radar", "RADAR DE ENTORNO", "SEÑAL × CANAL", COLORS["mint"])
                        points = polar_points(scan)
                        if points:
                            with ui.element("div").classes("relative w-full items-center justify-center"):
                                ui.echart(charts.polar(points)).classes("w-full").style("height:280px")
                                ui.element("div").classes("ae-sweep")
                        else:
                            empty_state("Sin redes para el radar.", "radar")

        def on_band(event) -> None:
            selected["band"] = event.value
            body.refresh()

        band_toggle.on_value_change(on_band)
        body()
