"""Alertas: línea temporal de incidentes, filtros y bandeja de evidencia."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from nicegui import ui

from ...models import Event, Severity
from ..components import empty_state, kv_row, label_caps, panel_header, status_dot, toast
from ..shell import shell
from ..state import fmt_age, get_context, severity_label
from ..theme import COLORS, SEVERITY_COLORS


@ui.page("/alertas")
def alerts_page() -> None:
    context = get_context()
    with shell("/alertas", "Alertas"):
        state: dict[str, Any] = {"severity": None, "selected": None}

        with ui.element("div").classes("ae-panel flex flex-wrap items-center justify-between gap-3 w-full"):
            with ui.column().classes("gap-0"):
                ui.label("Centro de Alertas de Espectro").classes("ae-headline text-lg text-[#D8F5E3]")
                with ui.row().classes("items-center gap-2"):
                    label_caps("MATRIZ DE INCIDENCIAS RF")
                    status_dot(COLORS["coral"], pulse=True)
                    label_caps("SENSOR", COLORS["text-muted"])
            counters = ui.row().classes("items-center gap-2")
            with ui.row().classes("items-center gap-2"):
                mute_btn = ui.button("SILENCIAR TIPO", icon="volume_off").props("unelevated no-caps").style(
                    f"background:{COLORS['surface-2']};color:{COLORS['amber']}"
                )
                export_btn = ui.button("EXPORTAR BITÁCORA", icon="file_download").props("unelevated no-caps").style(
                    f"background:{COLORS['surface-2']};color:{COLORS['text']}"
                )

        filters_row = ui.row().classes("items-center gap-2 flex-wrap")
        with ui.element("div").classes("grid grid-cols-1 xl:grid-cols-12 gap-5 w-full"):
            timeline = ui.element("div").classes("xl:col-span-7 ae-panel flex flex-col gap-3")
            inspector = ui.element("div").classes("xl:col-span-5 ae-panel flex flex-col gap-3")

        def build_filters() -> None:
            filters_row.clear()
            with filters_row:
                label_caps("SEVERIDAD:")
                options = [(None, "TODAS"), (Severity.CRITICAL, "CRÍTICA"), (Severity.ALERT, "ALERTA"),
                           (Severity.WARNING, "ADVERTENCIA"), (Severity.INFO, "INFORMATIVA")]
                for value, text in options:
                    active = state["severity"] == value
                    chip = ui.html(text).classes("ae-chip" + (" active" if active else "")).style("cursor:pointer")
                    chip.on("click", lambda _=None, v=value: pick_severity(v))

        def pick_severity(value: Any) -> None:
            state["severity"] = value
            build_filters()
            render_timeline.refresh()

        @ui.refreshable
        def render_counters() -> None:
            counters.clear()
            counts = context.repo.event_counts_by_severity()
            with counters:
                for severity in (Severity.CRITICAL, Severity.ALERT, Severity.WARNING, Severity.INFO):
                    color = SEVERITY_COLORS[severity]
                    with ui.element("div").classes("ae-sub px-3 py-1 flex flex-col items-center min-w-[74px]"):
                        ui.label(str(counts.get(severity.value, 0))).classes("ae-metric text-lg").style(f"color:{color}")
                        label_caps(severity_label(severity))

        @ui.refreshable
        def render_timeline() -> None:
            timeline.clear()
            with timeline:
                panel_header("warning", "FLUJO TEMPORAL DE TELEMETRÍA ANÓMALA", "EVENTOS PERSISTIDOS EN SQLITE", COLORS["coral"])
                events = context.repo.list_events(limit=60, min_severity=state["severity"])
                if not events:
                    empty_state("Sin eventos para este filtro.", "notifications_off")
                    return
                for event in events:
                    _event_card(context, event, state, render_inspector.refresh)

        @ui.refreshable
        def render_inspector(event: Event | None) -> None:
            inspector.clear()
            with inspector:
                if event is None:
                    status = context.monitor_status()
                    panel_header(
                        "sensors",
                        "MONITOR PASIVO",
                        "SELECCIONA UN EVENTO PARA VER SU EVIDENCIA",
                        COLORS["cyan"],
                    )
                    with ui.row().classes("items-center gap-2"):
                        ui.html(
                            f'<span class="ae-chip{" active" if status["running"] else ""}">'
                            f'{"CAPTURANDO" if status["running"] else "DETENIDO"}</span>'
                        )
                        if not status["capable"]:
                            ui.html('<span class="ae-chip">HARDWARE/PERMISOS NO DISPONIBLES</span>')
                    kv_row("INTERFAZ", status["interface"] or "—")
                    kv_row("CANAL ACTUAL", str(status["current_channel"]))
                    kv_row("PAQUETES", str(status["packet_count"]))
                    kv_row("EVENTOS", str(status["event_count"]))
                    if not status["capable"]:
                        ui.label(status["reason"]).classes("text-[11px]").style(f"color:{COLORS['amber']}")
                    ui.element("div").classes("ae-divider")
                    label_caps("ÚLTIMOS EVENTOS DE MONITOR")
                    rows = context.repo.list_monitor_events(limit=8)
                    if not rows:
                        ui.label("Sin eventos de monitor registrados.").classes("text-[11px] text-[#3F6B52]")
                    for row in rows:
                        with ui.row().classes("items-center justify-between w-full"):
                            ui.label(
                                f"[{row['kind']}] {row['ssid'] or row['bssid'] or row['source_mac']}"
                            ).classes("ae-mono text-[11px] text-[#D8F5E3] truncate max-w-[65%]")
                            label_caps(f"×{row['count']} · {fmt_age(row['ts'])}")
                    return
                panel_header("pageview", "INSPECTOR DE EVIDENCIA", f"ACTIVO: 0x{event.fingerprint[:4].upper() or '----'}", COLORS["cyan"])
                with ui.row().classes("items-center gap-2"):
                    ui.html(f'<span class="ae-chip active">{severity_label(event.severity)}</span>')
                    ui.html(f'<span class="ae-chip">{event.kind}</span>')
                    if event.dedup_count > 1:
                        ui.html(f'<span class="ae-chip">×{event.dedup_count}</span>')
                kv_row("TÍTULO", event.title)
                kv_row("REGISTRADO", fmt_age(event.created_at))
                kv_row("FINGERPRINT", event.fingerprint or "—")
                kv_row("ESTADO", "LEÍDO" if event.read else "SIN LEER", COLORS["text-dim"] if event.read else COLORS["amber"])
                ui.element("div").classes("ae-divider")
                label_caps("DESCRIPCIÓN")
                ui.label(event.body or "Sin detalle adicional.").classes(
                    "ae-mono text-[11px] text-[#86B89B] whitespace-pre-wrap"
                )
                if event.evidence:
                    ui.element("div").classes("ae-divider")
                    label_caps("EVIDENCIA (RAW)")
                    ui.label(json.dumps(event.evidence, ensure_ascii=False, indent=2)).classes(
                        "ae-mono text-[10px] text-[#86B89B] whitespace-pre-wrap max-h-40 overflow-auto"
                    )
                with ui.row().classes("items-center gap-2 w-full"):
                    read_btn = ui.button("Marcar leído", icon="done_all").props("unelevated no-caps dense").style(
                        f"background:{COLORS['surface-2']};color:{COLORS['mint']};flex:1"
                    )
                    mute_btn = ui.button("Silenciar tipo", icon="volume_off").props("unelevated no-caps dense").style(
                        f"background:{COLORS['surface-2']};color:{COLORS['amber']};flex:1"
                    )

                    def mark_read(_: Any = None) -> None:
                        if event.event_id is not None:
                            context.repo.mark_event_read(event.event_id)
                        toast("Evento marcado como leído", icon_name="done_all")
                        render_timeline.refresh()
                        render_counters.refresh()
                        render_inspector.refresh(None)

                    def mute(_: Any = None) -> None:
                        context.repo.mute_fingerprint(event.fingerprint, True)
                        toast("Tipo de evento silenciado", icon_name="volume_off")
                        render_timeline.refresh()

                    read_btn.on("click", mark_read)
                    mute_btn.on("click", mute)

        def do_mute_type() -> None:
            if state["selected"] is None:
                toast("Selecciona un evento primero", icon_name="info")
                return
            context.repo.mute_fingerprint(state["selected"].fingerprint, True)
            toast("Tipo seleccionado silenciado", icon_name="volume_off")
            render_timeline.refresh()

        def do_export() -> None:
            try:
                paths = context.export_report("json")
                toast(f"Bitácora exportada: {paths[0].name}", icon_name="download")
            except Exception as exc:  # noqa: BLE001
                toast(f"Error: {exc}", icon_name="error", color=COLORS["coral"])

        mute_btn.on("click", do_mute_type)
        export_btn.on("click", do_export)

        build_filters()
        render_counters()
        render_timeline()
        render_inspector(None)
        ui.timer(4.0, render_counters.refresh)
        ui.timer(6.0, render_timeline.refresh)


def _event_card(
    context: Any, event: Event, state: dict[str, Any], refresh_inspector: Callable[..., Any]
) -> None:
    color = SEVERITY_COLORS[event.severity]
    with ui.element("div").classes("ae-sub p-3 flex flex-col gap-2 cursor-pointer").style(
        f"border-left:2px solid {color}"
    ) as card:
        with ui.row().classes("items-center justify-between w-full"):
            with ui.row().classes("items-center gap-2"):
                ui.html(f'<span class="ae-chip" style="color:{color};border-color:{color}">{severity_label(event.severity)}</span>')
                ui.html(f'<span class="ae-chip">{event.kind}</span>')
                if event.dedup_count > 1:
                    ui.html(f'<span class="ae-chip">×{event.dedup_count}</span>')
            label_caps(fmt_age(event.created_at))
        ui.label(event.title).classes("text-[13px] text-[#D8F5E3]")
        if event.body:
            ui.label(event.body.splitlines()[0]).classes("text-[11px] text-[#86B89B] truncate")
        with ui.row().classes("items-center gap-2"):
            if not event.read:
                ui.html(f'<span class="ae-icon" style="font-size:14px;color:{COLORS["amber"]}">fiber_manual_record</span>')

        def select(_: Any = None) -> None:
            state["selected"] = event
            refresh_inspector(event)

        card.on("click", select)
