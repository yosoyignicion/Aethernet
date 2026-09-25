"""Dashboard: 'El Salpicadero'. Salud, contadores y histórico de congestión."""

from __future__ import annotations

from nicegui import ui

from ...core.spectrum import advise_channel_change, channel_table
from ...models import Band
from .. import charts
from ..components import label_caps, panel_header, status_dot, toast
from ..shell import shell
from ..state import get_context
from ..theme import COLORS, GRADE_COLORS, icon


@ui.page("/")
def dashboard() -> None:
    context = get_context()
    with shell("/", "Dashboard"):
        # -- barra de operaciones rápidas -------------------------------#
        with ui.element("div").classes("ae-panel flex flex-wrap items-center justify-between gap-3"):
            with ui.row().classes("items-center gap-3"):
                ui.html(icon("radar", size=22, color=COLORS["cyan"]))
                with ui.column().classes("gap-0"):
                    ui.label("CENTRO DE DIAGNÓSTICO RF").classes("ae-headline text-base text-[#D8F5E3]")
                    label_caps("MATRIZ OPERATIVA // RED LOCAL")
            with ui.row().classes("items-center gap-2"):
                scan_btn = ui.button("FORZAR ESCANEO", icon="sync").props("unelevated no-caps").style(
                    f"background:{COLORS['surface-2']};color:{COLORS['text']}"
                )
                export_btn = ui.button("EXPORTAR TELEMETRÍA", icon="file_download").props("unelevated no-caps").style(
                    f"background:{COLORS['surface-2']};color:{COLORS['text']}"
                )

        # -- gauge + tarjetas métricas ----------------------------------#
        with ui.element("div").classes("grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch w-full"):
            with ui.element("div").classes("lg:col-span-5 ae-panel flex flex-col justify-between"):
                with ui.row().classes("items-center justify-between w-full"):
                    with ui.row().classes("items-center gap-2"):
                        status_dot(COLORS["amber"], pulse=True)
                        label_caps("GAUGE // RF HEALTH")
                    label_caps("SENSOR 2.4/5G")
                gauge_container = ui.element("div").classes("relative w-full items-center justify-center").style("height:260px")
                with gauge_container:
                    gauge_chart = ui.echart(charts.gauge(0, "sin datos")).classes("w-full h-full")
                    with ui.column().classes("absolute inset-0 items-center justify-center gap-0 pointer-events-none"):
                        score_label = ui.label("—").classes("ae-metric text-4xl text-[#D8F5E3]")
                        grade_label = ui.label("SIN DATOS").classes("ae-label").style(f"color:{COLORS['amber']}")
                        label_caps("SALUD DE RED")
                with ui.row().classes("items-center justify-between ae-sub px-3 py-2 w-full"):
                    with ui.column().classes("gap-0"):
                        label_caps("ESTADO DEL ADAPTADOR")
                        adapter_label = ui.label("—").classes("ae-mono text-[12px]")
                    headline_label = ui.label("Sin escaneos todavía.").classes("text-[11px] text-[#86B89B] max-w-[60%] text-right")

            with ui.element("div").classes("lg:col-span-7 grid grid-cols-1 sm:grid-cols-2 gap-4"):
                cards = ui.element("div").classes("contents")
                metric_refs: dict[str, ui.label] = {}
                with cards:
                    for key, label, unit, icon_name, accent, hint, badge in (
                        ("visible_networks", "REDES VISIBLES", "BSSID", "wifi_find", COLORS["cyan"], "en el último ciclo", "ACTIVO"),
                        ("lan_devices", "DISPOSITIVOS LAN", "NODOS", "lan", COLORS["mint"], "inventario de subred", "UP"),
                        ("untrusted_devices", "NO CONFIABLES", "ALERTAS", "gpp_maybe", COLORS["amber"], "BSSID sin fichar", "REVISAR"),
                        ("unread_events", "ALERTAS SIN LEER", "EVENTOS", "notification_important", COLORS["coral"], "bandeja sin leer", "NIVEL"),
                    ):
                        with ui.element("div").classes(
                            "ae-card ae-hover-glow flex flex-col justify-between gap-3 min-h-[132px]"
                        ):
                            with ui.row().classes("items-center justify-between w-full"):
                                with ui.row().classes("items-center gap-2"):
                                    status_dot(accent, pulse=accent == COLORS["coral"])
                                    label_caps(label)
                                ui.html(icon(icon_name, size=20, color=accent))
                            with ui.row().classes("items-baseline gap-2"):
                                value_label = ui.label("0").classes("ae-metric text-4xl").style(f"color:{accent}")
                                label_caps(unit)
                            with ui.row().classes("items-center justify-between w-full ae-sub px-2 py-1"):
                                ui.label(hint).classes("text-[11px] text-[#86B89B] truncate")
                                label_caps(badge, accent)
                            metric_refs[key] = value_label

        # -- tarjeta de canal (semáforo accionable) ---------------------#
        with ui.element("div").classes("ae-panel flex flex-wrap items-center justify-between gap-4 w-full"):
            with ui.row().classes("items-center gap-3"):
                canal_dot = ui.html(
                    f'<span style="display:inline-block;width:10px;height:10px;border-radius:9999px;'
                    f'background:{COLORS["text-muted"]}"></span>'
                )
                with ui.column().classes("gap-0"):
                    label_caps("CANAL 2.4 GHz")
                    canal_label = ui.label("—").classes("ae-headline text-base text-[#D8F5E3]")
            canal_reco = ui.label("").classes("ae-mono text-[12px] text-[#86B89B]")
            canal_btn = ui.button("GESTOR DE CANAL", icon="tune").props("unelevated no-caps").style(
                f"background:{COLORS['surface-2']};color:{COLORS['text']}"
            )
            canal_btn.on("click", lambda: ui.navigate.to("/espectro"))

        # -- histórico de congestión ------------------------------------#
        with ui.element("div").classes("ae-panel flex flex-col gap-4 w-full"):
            panel_header("show_chart", "HISTÓRICO DE CONGESTIÓN 24H", "RESOLUCIÓN TEMPORAL 15 MIN // OBSERVACIONES REALES", COLORS["mint"])
            congestion_chart = ui.echart(charts.congestion_area(context.repo.hourly_congestion(24))).classes("w-full").style("height:260px")

    # -- lógica ---------------------------------------------------------#
    def refresh() -> None:
        health = context.health()
        scan = context.last_scan()
        if health and scan:
            charts.update(gauge_chart, charts.gauge(health.total, health.grade))
            score_label.set_text(str(health.total))
            score_label.style(f"color:{GRADE_COLORS.get(health.grade, COLORS['text'])}")
            grade_label.set_text(health.grade.upper())
            headline_label.set_text(health.headline)
            band = "2.4/5 GHz" if context.adapter.supports_5ghz else "2.4 GHz"
            adapter_label.set_text(f"{context.adapter.interface or '—'} · {band}")
        else:
            score_label.set_text("—")
            adapter_label.set_text("—")
        counts = context.counts()
        for key, label in metric_refs.items():
            label.set_text(str(counts.get(key, 0)))
        unread_label = metric_refs["unread_events"]
        if counts.get("unread_events", 0) > 0:
            unread_label.classes(add="ae-glitch")
        else:
            unread_label.classes(remove="ae-glitch")
        charts.update(congestion_chart, charts.congestion_area(context.repo.hourly_congestion(24)))

        # canal actual vs recomendado
        current_channel = int(context.settings.my_channel or 0)
        stats = context.repo.channel_stats(hours=context.settings.forecast_window_hours)
        table = channel_table(stats, Band.GHZ_24)
        best = min(table, key=lambda r: r["rank"]) if table else None
        if current_channel:
            advice = advise_channel_change(
                table, current_channel, context.settings.channel_watch_min_improvement
            )
            if advice:
                color = COLORS["amber"]
                canal_label.set_text(f"CH{current_channel:02d} · saturado")
                canal_reco.set_text(
                    f"Mejor: CH{advice['recommended']:02d} (menos interferencia ~{advice['improvement_pct']}%)"
                )
            else:
                color = COLORS["mint"]
                canal_label.set_text(f"CH{current_channel:02d} · óptimo")
                canal_reco.set_text("Tu canal actual es el mejor observado.")
        else:
            color = COLORS["text-muted"]
            canal_label.set_text("sin definir")
            canal_reco.set_text(
                f"Mejor ahora: CH{best['channel']:02d}" if best else "Define tu canal en el gestor."
            )
        canal_dot.set_content(
            f'<span style="display:inline-block;width:10px;height:10px;border-radius:9999px;'
            f'background:{color}"></span>'
        )

    def _after_scan(_result: object) -> None:
        ui.timer(0.1, refresh, once=True)

    def do_scan() -> None:
        started = context.scan_async(on_done=_after_scan)
        toast("Escaneo RF iniciado" if started else "Ya hay un escaneo en curso", icon_name="sync")

    async def do_export() -> None:
        try:
            paths = context.export_report("md")
            toast(f"Informe generado: {paths[0].name}", icon_name="download")
        except Exception as exc:  # noqa: BLE001
            toast(f"No se pudo exportar: {exc}", icon_name="error", color=COLORS["coral"])

    scan_btn.on("click", do_scan)
    export_btn.on("click", do_export)
    refresh()
    ui.timer(3.0, refresh)
