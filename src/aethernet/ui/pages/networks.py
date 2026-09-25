"""Redes: inventario BSSID con búsqueda, filtros e inspector lateral."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from ...core.oui import vendor_for
from ...models import AccessPoint
from .. import charts
from ..components import empty_state, kv_row, label_caps, panel_header
from ..shell import shell
from ..state import fmt_age, get_context, security_label
from ..theme import COLORS, icon

_COLUMNS: list[dict[str, Any]] = [
    {"name": "signal", "label": "SEÑAL", "field": "signal", "sortable": True, "align": "left"},
    {"name": "ssid", "label": "SSID", "field": "ssid", "sortable": True, "align": "left"},
    {"name": "bssid", "label": "BSSID (MAC)", "field": "bssid", "align": "left"},
    {"name": "channel", "label": "CANAL / FREC", "field": "channel", "sortable": True, "align": "left"},
    {"name": "security", "label": "SEGURIDAD", "field": "security", "sortable": True, "align": "left"},
    {"name": "vendor", "label": "FABRICANTE (OUI)", "field": "vendor", "align": "left"},
    {"name": "seen", "label": "ÚLTIMA ACT", "field": "seen", "sortable": True, "align": "left"},
]


def _signal_text(dbm: int) -> str:
    return f"{dbm} dBm"


@ui.page("/redes")
def networks_page() -> None:
    context = get_context()
    with shell("/redes", "Redes"):
        state: dict[str, Any] = {"chips": set(), "density": "standard"}

        with ui.element("div").classes("ae-panel flex flex-col gap-4"):
            with ui.row().classes("items-center justify-between w-full flex-wrap gap-3"):
                with ui.row().classes("items-center gap-2 ae-mono text-[11px] text-[#86B89B]"):
                    ui.html(icon("wifi", size=18, color=COLORS["cyan"]))
                    ui.label("// RF TABLE DISCOVERY").classes("ae-mono text-[11px]")
                    ui.label("| PROMISCUOUS MODE [ETH_P_ALL]").classes("ae-mono text-[11px] text-[#3F6B52]")
                search = ui.input(placeholder="Buscar SSID, BSSID o fabricante...").props(
                    'type=search clearable dense outlined'
                ).classes("min-w-[280px]")
                with search.add_slot("prepend"):
                    ui.html(icon("search", size=16, color=COLORS["text-dim"]))
            filters_row = ui.row().classes("items-center gap-2 flex-wrap")

        metrics_row = ui.row().classes("grid grid-cols-2 md:grid-cols-6 gap-3 w-full")

        @ui.refreshable
        def render_inspector(ap: AccessPoint | None) -> None:
            with ui.element("div").classes("ae-panel flex flex-col gap-3").style("min-height:400px"):
                if ap is None:
                    empty_state("Selecciona una red para inspeccionarla.", "touch_app")
                    return
                panel_header("troubleshoot", "// INSPECTOR DE RED ACTIVA", None, COLORS["cyan"])
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label(ap.display_ssid).classes("ae-headline text-lg text-[#D8F5E3] truncate")
                    ui.html(f'<span class="ae-chip active">{_signal_text(ap.signal_dbm)}</span>')
                series = context.repo.signal_series(ap.bssid, hours=24)
                label_caps("HISTÓRICO RSSI (24 H)")
                if series:
                    ui.echart(charts.sparkline(series)).classes("w-full").style("height:80px")
                else:
                    ui.label("Sin histórico todavía.").classes("text-[11px] text-[#3F6B52]")
                ui.element("div").classes("ae-divider")
                label_caps("PARÁMETROS DE CAPA 1 Y 2")
                kv_row("FABRICANTE (OUI)", ap.vendor or vendor_for(ap.bssid) or "Desconocido", COLORS["cyan"])
                kv_row("CANAL / FRECUENCIA", f"CH {ap.channel} / {ap.frequency_mhz or '—'} MHz")
                kv_row("SEGURIDAD", security_label(ap.security), COLORS["mint"] if ap.is_secure else COLORS["coral"])
                kv_row("BSSID HARDWARE", ap.bssid)
                kv_row("TASA MÁXIMA", f"{ap.max_rate:.0f} Mbps" if ap.max_rate else "n/d")
                kv_row("WPS", "ACTIVO" if ap.wps else "no detectado", COLORS["amber"] if ap.wps else None)
                kv_row("PRIMERA VEZ", fmt_age(ap.first_seen))
                kv_row("ÚLTIMA VEZ", fmt_age(ap.last_seen))
                if ap.tags:
                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        for tag in ap.tags:
                            ui.html(f'<span class="ae-chip active">{tag}</span>')

        with ui.element("div").classes("grid grid-cols-1 xl:grid-cols-12 gap-5 w-full"):
            with ui.element("div").classes("xl:col-span-8"):
                table = ui.table(columns=_COLUMNS, rows=[], row_key="bssid", selection="single", pagination=12).classes(
                    "w-full ae-panel"
                ).props("flat dense dark")
            with ui.element("div").classes("xl:col-span-4"):
                render_inspector(None)

        def apply_filters() -> None:
            scan = context.last_scan()
            if scan is None:
                table.rows = []
                return
            aps = list(scan.aps)
            chips = state["chips"]
            if "5" in chips:
                aps = [a for a in aps if a.band.value.startswith("5")]
            if "24" in chips:
                aps = [a for a in aps if a.band.value.startswith("2.4")]
            if "secure" in chips:
                aps = [a for a in aps if a.is_secure]
            if "open" in chips:
                aps = [a for a in aps if a.is_open]
            if "hidden" in chips:
                aps = [a for a in aps if a.hidden]
            table.rows = [
                {
                    "bssid": a.bssid,
                    "ssid": a.display_ssid,
                    "signal": _signal_text(a.signal_dbm),
                    "channel": f"CH {a.channel:02d}",
                    "security": security_label(a.security),
                    "vendor": a.vendor or "—",
                    "seen": fmt_age(a.last_seen),
                }
                for a in aps
            ]

        def build_chips() -> None:
            filters_row.clear()
            scan = context.last_scan()
            aps = list(scan.aps) if scan else []
            counts = {
                "all": len(aps),
                "5": sum(1 for a in aps if a.band.value.startswith("5")),
                "24": sum(1 for a in aps if a.band.value.startswith("2.4")),
                "secure": sum(1 for a in aps if a.is_secure),
                "open": sum(1 for a in aps if a.is_open),
                "hidden": sum(1 for a in aps if a.hidden),
            }
            definitions = (
                ("all", f"TODAS ({counts['all']})"),
                ("5", f"5 GHZ ({counts['5']})"),
                ("24", f"2.4 GHZ ({counts['24']})"),
                ("secure", f"CIFRADAS ({counts['secure']})"),
                ("open", f"ABIERTAS ({counts['open']})"),
                ("hidden", f"OCULTAS ({counts['hidden']})"),
            )
            with filters_row:
                for key, text in definitions:
                    active = key in state["chips"]
                    chip = ui.html(text).classes("ae-chip" + (" active" if active else "")).style("cursor:pointer")
                    chip.on("click", lambda _=None, k=key: toggle_chip(k))

        def toggle_chip(key: str) -> None:
            if key == "all":
                state["chips"].clear()
            elif key in state["chips"]:
                state["chips"].discard(key)
            else:
                state["chips"].add(key)
            build_chips()
            apply_filters()

        def on_select(event: Any) -> None:
            selection = event.args or []
            if not selection:
                render_inspector.refresh(None)
                return
            bssid = selection[0].get("bssid")
            scan = context.last_scan()
            ap = next((a for a in scan.aps if a.bssid == bssid), None) if scan else None
            render_inspector.refresh(ap)

        def refresh() -> None:
            scan = context.last_scan()
            metrics_row.clear()
            if scan is None:
                apply_filters()
                return
            channels: dict[int, int] = {}
            for ap in scan.aps:
                channels[ap.channel] = channels.get(ap.channel, 0) + 1
            busiest = max(channels.items(), key=lambda kv: kv[1]) if channels else (0, 0)
            avg = round(sum(a.signal_dbm for a in scan.aps) / len(scan.aps), 1) if scan.aps else 0
            metrics = (
                ("BSSIDS ACTIVOS", str(scan.count), COLORS["cyan"]),
                ("CH CONGESTIÓN MÁX", f"CH {busiest[0]:02d} ({busiest[1]})", COLORS["amber"]),
                ("SEÑAL PROMEDIO", f"{avg} dBm", COLORS["mint"]),
                ("ABIERTAS", str(sum(1 for a in scan.aps if a.is_open)), COLORS["coral"]),
                ("OCULTAS", str(sum(1 for a in scan.aps if a.hidden)), COLORS["text-dim"]),
                ("WPS", str(sum(1 for a in scan.aps if a.wps)), COLORS["amber"]),
            )
            with metrics_row:
                for lbl, value, color in metrics:
                    with ui.element("div").classes("ae-sub p-3 flex flex-col gap-1"):
                        label_caps(lbl)
                        ui.label(value).classes("ae-metric text-lg").style(f"color:{color}")
            build_chips()
            apply_filters()

        table.on("selection", on_select)
        search.bind_value(table, "filter")
        refresh()
        ui.timer(4.0, refresh)
