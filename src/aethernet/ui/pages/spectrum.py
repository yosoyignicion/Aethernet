"""Espectro: distribución por canal, heatmap 24h y diagnóstico de canal."""

from __future__ import annotations

import time
from typing import Any

from nicegui import ui

from ...config import save_settings
from ...core.forecast import WEEKDAYS, coverage, predict_channel, weekly_grid
from ...core.spectrum import (
    channel_table,
    evaluate_channel,
    occupancy,
    polar_points,
    recommend_channel,
    recommend_from_stats,
)
from ...core.spectrum import heatmap as build_heatmap
from ...models import Band
from ...utils import humanize_age
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
                ui.label("RF_SPECTRUM_ANALYZER").classes("ae-mono text-sm text-[#D8F5E3]")
                band_toggle = ui.toggle(
                    {Band.GHZ_24: "2.4 GHz [CH 1-13]", Band.GHZ_5: "5 GHz [U-NII]"},
                    value=Band.GHZ_24,
                ).props("no-caps dense")
            with ui.row().classes("items-center gap-4 ae-mono text-[11px] text-[#86B89B]"):
                ui.html('SWEEP: <span style="color:#86B89B">n/d</span>')
                ui.html('RBW: <span style="color:#86B89B">n/d</span> · requiere monitor mode')

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
                        ui.label(recommendation["reason"]).classes("text-[12px] text-[#86B89B]")
                        ui.element("div").classes("ae-divider")
                        kv_row("RELACIÓN S/R (SNR)", "n/d", COLORS["text-muted"])
                        kv_row("RUIDO DE FONDO", "n/d", COLORS["text-muted"])
                        overlapping = [ap for ap in scan.aps if ap.channel == recommendation["channel"]]
                        kv_row("REDES EN CANAL RECOMENDADO", str(len(overlapping)), COLORS["cyan"])
                        ui.label(
                            "SNR y ruido de fondo requieren monitor mode; con el hardware actual solo "
                            "medimos ocupación por canal."
                        ).classes("text-[11px] text-[#3F6B52] italic")

                    with ui.element("div").classes("ae-panel flex flex-col gap-2"):
                        target_channel = recommendation["channel"]
                        interfering = sorted(
                            [ap for ap in scan.aps if ap.channel == target_channel],
                            key=lambda a: a.signal_dbm,
                            reverse=True,
                        )[:6]
                        panel_header("cell_tower", "CO-INTERFERENCIA", f"{len(interfering)} DETECTADAS EN CH {target_channel}", COLORS["amber"])
                        ui.label(
                            "Redes vecinas: aparecer aquí es informativo (malla, multi-banda o "
                            "repetidores del entorno), no una amenaza. Solo importan si imitan TU SSID."
                        ).classes("text-[11px] text-[#86B89B] italic")
                        if not interfering:
                            empty_state("Canal limpio.", "check_circle")
                        for ap in interfering:
                            with ui.row().classes("items-center justify-between w-full py-1 border-b border-[#1B3324]"):
                                with ui.column().classes("gap-0 min-w-0"):
                                    ui.label(ap.display_ssid).classes("ae-mono text-[12px] text-[#D8F5E3] truncate max-w-[150px]")
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

        def on_band(event: Any) -> None:
            selected["band"] = event.value
            body.refresh()

        band_toggle.on_value_change(on_band)
        body()

        # -- Asesor de canal 2.4 GHz en vivo (histórico, estable) ----------#
        advisor = {"hours": 6}

        @ui.refreshable
        def render_advisor() -> None:
            stats = context.repo.channel_stats(advisor["hours"])
            scan_now = context.last_scan()
            if stats:
                rec = recommend_from_stats(stats, Band.GHZ_24)
            elif scan_now is not None:
                instant = recommend_channel(scan_now, Band.GHZ_24)
                rec = {
                    "channel": instant["channel"],
                    "availability": instant["free_pct"],
                    "ranking": [instant["channel"]],
                    "scores": {},
                    "reason": instant["reason"],
                }
            else:
                with ui.element("div").classes("ae-panel w-full"):
                    empty_state("Sin datos de espectro todavía.", "insights")
                return

            key = "channel_advisor_24"
            previous = context.repo.kv_get(key, {}) or {}
            now = time.time()
            if previous.get("channel") != rec["channel"]:
                previous = {"channel": rec["channel"], "since": now}
                context.repo.kv_set(key, previous)
            since = float(previous.get("since", now))

            with ui.element("div").classes("ae-panel flex flex-col gap-4 w-full"):
                with ui.row().classes("items-center justify-between w-full flex-wrap gap-3"):
                    panel_header(
                        "insights",
                        "ASESOR DE CANAL 2.4 GHz (EN VIVO)",
                        "HISTÓRICO ESTABLE · AETHERNET NO TOCA TU ROUTER",
                        COLORS["mint"],
                    )
                    with ui.row().classes("items-center gap-2"):
                        label_caps("VENTANA:")
                        for hours, text in ((1, "1 H"), (6, "6 H"), (24, "24 H")):
                            active = advisor["hours"] == hours
                            chip = ui.html(text).classes(
                                "ae-chip" + (" active" if active else "")
                            ).style("cursor:pointer")
                            chip.on("click", lambda _=None, h=hours: _set_window(h))

                with ui.row().classes("items-center gap-4 flex-wrap"):
                    with ui.column().classes("gap-0"):
                        label_caps("CANAL RECOMENDADO AHORA")
                        ui.label(f"CANAL {rec['channel']}").classes("ae-metric text-3xl").style(
                            f"color:{COLORS['mint']}"
                        )
                    with ui.column().classes("gap-0"):
                        label_caps("DISPONIBILIDAD")
                        ui.label(f"{rec['availability']}%").classes("ae-metric text-2xl").style(
                            f"color:{COLORS['amber'] if rec['availability'] < 60 else COLORS['cyan']}"
                        )
                    with ui.column().classes("gap-0"):
                        label_caps("ESTABILIDAD")
                        ui.label(f"estable desde {humanize_age(now - since)}").classes(
                            "ae-mono text-[12px] text-[#86B89B]"
                        )
                    ui.element("div").classes("flex-1")
                    copy_btn = ui.button("COPIAR CANAL", icon="content_copy").props(
                        "unelevated no-caps"
                    ).style(f"background:{COLORS['mint']};color:#030603")

                # ranking visual de los tres canales no solapados
                ranking = rec.get("ranking") or [rec["channel"]]
                scores: dict[str, Any] = rec.get("scores") or {}
                if scores:
                    for channel in ranking:
                        score = float(scores.get(str(channel), 0.0))
                        availability = 100 if score <= 0 else max(0, min(100, round(100 - score * 25)))
                        with ui.row().classes("items-center gap-3 w-full"):
                            ui.label(f"CH {channel:02d}").classes("ae-mono text-[12px] w-14").style(
                                f"color:{COLORS['mint'] if channel == rec['channel'] else COLORS['text-dim']}"
                            )
                            bar = ui.linear_progress(value=availability / 100, show_value=False).classes("flex-1")
                            bar.props("rounded")
                            ui.label(f"{availability}%").classes("ae-mono text-[11px] w-12 text-right")

                ui.label(
                    "Recomendación calculada sobre tus observaciones reales (no un escaneo suelto) para "
                    "evitar cambios de canal que desestabilicen tu red. Aplícalo tú en el panel del router."
                ).classes("text-[11px] text-[#86B89B] italic")

                def _copy() -> None:
                    ui.clipboard.write(str(rec["channel"]))
                    ui.notify(f"Canal {rec['channel']} copiado", position="top", timeout=2500)

                copy_btn.on("click", _copy)

        def _set_window(hours: int) -> None:
            advisor["hours"] = hours
            render_advisor.refresh()

        render_advisor()
        ui.timer(15.0, render_advisor.refresh)

        # -- Previsión por hora/día (histórico) ---------------------------#
        forecast_day = {"weekday": time.localtime().tm_wday}

        @ui.refreshable
        def render_forecast() -> None:
            band = Band.GHZ_24.value
            buckets = context.repo.channel_advisory_buckets(band)
            cov = coverage(buckets)
            today = time.localtime().tm_wday
            now_hour = time.localtime().tm_hour
            prediction = predict_channel(buckets, forecast_day["weekday"], now_hour)
            grid = weekly_grid(buckets, forecast_day["weekday"])
            with ui.element("div").classes("ae-panel flex flex-col gap-3 w-full"):
                with ui.row().classes("items-center justify-between w-full flex-wrap gap-3"):
                    panel_header(
                        "schedule",
                        "PREVISIÓN POR HORA (HISTÓRICO)",
                        f"{cov['slots']}/168 FRANJAS VISTAS · {cov['observations']} OBSERVACIONES",
                        COLORS["cyan"],
                    )
                    with ui.row().classes("items-center gap-1"):
                        for index, name in enumerate(WEEKDAYS):
                            active = forecast_day["weekday"] == index
                            chip = ui.html(name).classes(
                                "ae-chip" + (" active" if active else "")
                            ).style("cursor:pointer")
                            chip.on("click", lambda _=None, w=index: _set_day(w))

                if prediction is not None and forecast_day["weekday"] == today:
                    with ui.row().classes("items-center gap-5 flex-wrap"):
                        for caption, value, color in (
                            ("AHORA (PREVISTO)", f"CANAL {prediction.channel}", COLORS["mint"]),
                            ("CONFIANZA", f"{prediction.confidence:.0%}", COLORS["cyan"]),
                            ("MUESTRAS", str(prediction.samples), COLORS["amber"]),
                        ):
                            with ui.column().classes("gap-0"):
                                label_caps(caption)
                                ui.label(value).classes("ae-metric text-2xl").style(f"color:{color}")
                else:
                    ui.label(
                        "Selecciona el día de hoy o acumula más días para ver la previsión."
                    ).classes("text-[11px] text-[#86B89B]")

                if cov["slots"] == 0:
                    empty_state("Aún no hay historial. Deja Aethernet (o el daemon) escaneando unos días.", "schedule")
                else:
                    ui.echart(charts.forecast_bars(grid["hours"])).classes("w-full").style("height:230px")
                    with ui.row().classes("items-center gap-3"):
                        for channel, color in ((1, COLORS["mint"]), (6, COLORS["cyan"]), (11, COLORS["amber"])):
                            with ui.row().classes("items-center gap-1"):
                                ui.element("div").style(
                                    f"width:10px;height:4px;border-radius:2px;background:{color}"
                                )
                                label_caps(f"CH{channel}")

                ui.label(
                    "Cada escaneo guarda el mejor canal del momento por hora y día. Con 1-2 semanas "
                    "obtienes el patrón para adelantarte a la saturación según el reloj del PC."
                ).classes("text-[11px] text-[#86B89B] italic")

        def _set_day(weekday: int) -> None:
            forecast_day["weekday"] = weekday
            render_forecast.refresh()

        render_forecast()
        ui.timer(60.0, render_forecast.refresh)

        # -- Gestor de canal: selección manual con veredicto de mejora -----#
        @ui.refreshable
        def render_manager() -> None:
            stats = context.repo.channel_stats(hours=context.settings.forecast_window_hours)
            table = channel_table(stats, Band.GHZ_24)
            best = min(table, key=lambda r: r["rank"])
            current = int(context.settings.my_channel or 0)

            if 1 <= current <= 13:
                evaluation = evaluate_channel(best["channel"], stats, Band.GHZ_24, current=current)
                vs = evaluation.get("vs_current", {})
                if current == best["channel"]:
                    verdict = f"Tu canal CH{current:02d} ya es el mejor observado."
                    verdict_color = COLORS["mint"]
                elif vs.get("better"):
                    current_interference = next(
                        (r["interference"] for r in table if r["channel"] == current), 0.0
                    )
                    pct = int(round(vs["interference_delta"] / current_interference * 100)) if current_interference > 0 else 0
                    verdict = (
                        f"CH{current:02d} → CH{best['channel']:02d}: menos interferencia (~{pct}%) "
                        f"y +{vs['availability_delta']}% disponibilidad."
                    )
                    verdict_color = COLORS["amber"]
                else:
                    verdict = "Ahora mismo no hay mejora clara; mantén tu canal y revisa más tarde."
                    verdict_color = COLORS["text-dim"]
            else:
                verdict = "Define tu canal actual para ver cuánto mejorarías."
                verdict_color = COLORS["text-dim"]

            with ui.element("div").classes("ae-panel flex flex-col gap-4 w-full"):
                with ui.row().classes("items-center justify-between w-full flex-wrap gap-3"):
                    panel_header(
                        "tune",
                        "GESTOR DE CANAL 2.4 GHz",
                        "SELECCIÓN MANUAL EN VIVO · AETHERNET NO TOCA TU ROUTER",
                        COLORS["amber"],
                    )
                    copy_btn = ui.button("COPIAR INSTRUCCIONES", icon="content_copy").props(
                        "unelevated no-caps"
                    ).style(f"background:{COLORS['amber']};color:#030603")

                with ui.row().classes("items-end gap-6 flex-wrap"):
                    with ui.column().classes("gap-1"):
                        label_caps("TU CANAL ACTUAL")
                        select = ui.select(
                            {0: "— sin definir —", **{c: f"CH {c:02d}" for c in range(1, 14)}},
                            value=current,
                        ).props("dense outlined").classes("w-40")
                        select.on_value_change(_set_channel)
                    with ui.column().classes("gap-1"):
                        label_caps("RECOMENDADO AHORA")
                        ui.label(f"CH {best['channel']:02d}").classes("ae-metric text-2xl").style(
                            f"color:{COLORS['mint']}"
                        )
                    with ui.column().classes("gap-1"):
                        label_caps("VEREDICTO")
                        ui.label(verdict).classes("ae-mono text-[12px] max-w-[520px]").style(
                            f"color:{verdict_color}"
                        )

                with ui.row().classes("items-center gap-3 w-full"):
                    ui.label("CH").classes("ae-mono text-[10px] w-14 text-[#3F6B52]")
                    ui.label("#").classes("ae-mono text-[10px] w-8 text-[#3F6B52]")
                    ui.label("REDES").classes("ae-mono text-[10px] w-16 text-[#3F6B52]")
                    ui.label("DISPONIBILIDAD").classes("ae-mono text-[10px] flex-1 text-[#3F6B52]")
                for row in sorted(table, key=lambda r: r["rank"]):
                    is_best = row["channel"] == best["channel"]
                    is_mine = row["channel"] == current
                    color = COLORS["mint"] if is_best else (COLORS["amber"] if is_mine else COLORS["text-dim"])
                    with ui.row().classes("items-center gap-3 w-full py-1 border-b border-[#1B3324]"):
                        ui.label(f"CH {row['channel']:02d}").classes("ae-mono text-[12px] w-14").style(
                            f"color:{color}"
                        )
                        ui.label(f"#{row['rank']}").classes("ae-mono text-[11px] w-8 text-[#3F6B52]")
                        ui.label(f"{row['networks']}").classes("ae-mono text-[11px] w-16 text-[#86B89B]")
                        bar = ui.linear_progress(value=row["availability"] / 100, show_value=False).classes(
                            "flex-1"
                        )
                        bar.props("rounded")
                        ui.label(f"{row['availability']}%").classes("ae-mono text-[11px] w-12 text-right")
                        if is_best:
                            ui.html('<span class="ae-chip active">RECOMENDADO</span>')
                        if is_mine:
                            ui.html('<span class="ae-chip">TU CANAL</span>')

                ui.label(
                    "Elige el canal tú mismo en el panel del router; Aethernet mide y te dice qué ganarías. "
                    "La tabla se calcula sobre tus observaciones reales."
                ).classes("text-[11px] text-[#86B89B] italic")

                def _copy() -> None:
                    current_label = f"CH{current:02d}" if current else "sin definir"
                    text = (
                        f"Aethernet · Canal recomendado 2.4 GHz: CH{best['channel']:02d}. "
                        f"Actual: {current_label}. {verdict}"
                    )
                    ui.clipboard.write(text)
                    ui.notify("Instrucciones copiadas", position="top", timeout=2500)

                copy_btn.on("click", _copy)

        def _set_channel(event: Any) -> None:
            context.settings.my_channel = int(event.value or 0)
            save_settings(context.settings, context.paths)
            render_manager.refresh()

        render_manager()
        ui.timer(20.0, render_manager.refresh)
