"""Shell de la aplicación: cabecera, barra lateral, pie de estado y layout.

Idéntico en todas las páginas; solo cambia el ítem activo.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from nicegui import ui

from ..config import save_settings
from . import theme
from .components import label_caps, status_dot, toast
from .state import fmt_age, get_context
from .theme import COLORS, NAV_ITEMS, icon

_LOGO = f"""
<svg width="34" height="34" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="20" cy="20" r="18" stroke="{COLORS['border']}" stroke-width="1.5"/>
  <circle cx="20" cy="20" r="13" stroke="{COLORS['mint']}" stroke-width="1.5" stroke-dasharray="3 4"/>
  <circle cx="20" cy="20" r="7" stroke="{COLORS['cyan']}" stroke-width="1.5"/>
  <circle cx="20" cy="20" r="2.5" fill="{COLORS['mint']}"/>
  <path d="M20 2v6M38 20h-6M20 38v-6M2 20h6" stroke="{COLORS['mint']}" stroke-width="1.5"/>
</svg>
"""


def _nav(active: str) -> None:
    for index, (icon_name, label, path) in enumerate(NAV_ITEMS, start=1):
        is_active = path == active
        classes = "w-full items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors"
        if is_active:
            classes += " bg-[#152C1D]"
        else:
            classes += " hover:bg-[#0E1E15]"
        row = ui.row().classes(classes)
        with row:
            index_label = f"{index:02d}" if icon_name != "warning" else ""
            ui.html(icon(icon_name, size=20, color=COLORS["mint"] if is_active else COLORS["text-dim"]))
            if label == "Alertas":
                unread = get_context().repo.unread_count()
                ui.label(label).classes(
                    "text-sm flex-1 " + ("text-[#7CFFB2]" if is_active else "text-[#D8F5E3]")
                )
                if unread:
                    ui.html(
                        f'<span class="ae-mono text-[10px] font-bold px-2 py-0.5 rounded-full" '
                        f'style="background:{COLORS["coral"]};color:#0A0E14">{unread}</span>'
                    )
            else:
                ui.label(label).classes(
                    "text-sm flex-1 " + ("text-[#7CFFB2]" if is_active else "text-[#D8F5E3]")
                )
                ui.label(index_label).classes("ae-mono text-[10px] text-[#3F6B52]")
        row.style("border-left:2px solid " + (COLORS["mint"] if is_active else "transparent"))
        row.on("click", lambda _=None, p=path: ui.navigate.to(p))
    ui.element("div").classes("ae-divider my-2")


def _sidebar_footer() -> None:
    context = get_context()
    with ui.column().classes("gap-2 w-full px-3 pb-3"):
        label_caps("RX POWER")
        value = ui.label("—").classes("ae-mono text-lg text-[#D8F5E3]")
        bar = ui.linear_progress(value=0, show_value=False).classes("w-full").props("rounded")

        def update() -> None:
            scan = context.last_scan()
            strongest = max((ap.signal_dbm for ap in scan.aps), default=None) if scan else None
            if strongest is None:
                value.set_text("—")
                bar.value = 0
                return
            value.set_text(f"{strongest} dBm")
            bar.value = max(0.0, min(1.0, (strongest + 100) / 60))

        update()
        ui.timer(2.0, update)


_SYS_STATES = {
    "excelente": ("NOMINAL", COLORS["mint"]),
    "buena": ("NOMINAL", COLORS["mint"]),
    "aceptable": ("AVISO", COLORS["amber"]),
    "degradada": ("DEGRADADO", COLORS["coral"]),
    "crítica": ("CRÍTICO", COLORS["magenta"]),
}


def _header() -> None:
    context = get_context()
    with ui.row().classes("w-full items-center justify-between px-4 h-full"):
        with ui.row().classes("items-center gap-3"):
            ui.html(_LOGO)
            with ui.column().classes("gap-0"):
                ui.label("AETHERNET").classes("ae-headline text-base font-semibold tracking-wide text-[#D8F5E3]")
                label_caps("MONITOR RF // LOCAL")
        with ui.row().classes("items-center gap-3"):
            with ui.row().classes("ae-sub items-center gap-2 px-3 py-1"):
                dot = ui.html(
                    f'<span style="display:inline-block;width:9px;height:9px;border-radius:9999px;'
                    f'background:{COLORS["text-muted"]}"></span>'
                )
                sys_label = ui.label("SYS: —").classes("ae-label")

                def update_sys() -> None:
                    health = context.health()
                    if health is None:
                        sys_label.set_text("SYS: SIN DATOS")
                        return
                    word, color = _SYS_STATES.get(health.grade, ("SIN DATOS", COLORS["text-muted"]))
                    sys_label.set_text(f"SYS: {word}")
                    sys_label.style(f"color:{color}")
                    dot.set_content(
                        f'<span style="display:inline-block;width:9px;height:9px;border-radius:9999px;'
                        f'background:{color}"></span>'
                    )

                update_sys()
                ui.timer(3.0, update_sys)
            search = ui.button(icon="search").props("flat dense round").on(
                "click", lambda: ui.navigate.to("/redes")
            )
            search.tooltip("Buscar redes y BSSID (Ctrl+K)")

            def toggle_compact(_: object = None) -> None:
                context.settings.compact = not context.settings.compact
                save_settings(context.settings, context.paths)
                compact = str(context.settings.compact).lower()
                ui.run_javascript(
                    f"document.documentElement.classList.toggle('ae-compact', {compact})"
                )
                toast(
                    "Modo compacto " + ("activado" if context.settings.compact else "desactivado"),
                    icon_name="density_medium",
                )

            ui.button(icon="density_medium").props("flat dense round").on("click", toggle_compact).tooltip(
                "Modo compacto"
            )
            ui.button(icon="help").props("flat dense round").on(
                "click", lambda: ui.navigate.to("/ajustes")
            ).tooltip("Atajos de teclado")
            ui.html(
                f'<div style="width:30px;height:30px;border-radius:9999px;background:{COLORS["surface-high"]};'
                f'display:flex;align-items:center;justify-content:center">'
                f'{icon("person", size=18, color=COLORS["text-dim"])}</div>'
            )


def _footer() -> None:
    context = get_context()
    with ui.row().classes("w-full items-center justify-between px-4 h-full"):
        with ui.row().classes("items-center gap-3"):
            adapter_label = ui.html("")
            ui.label("·").classes("text-[#3F6B52]")
            db_label = ui.html("")
            ui.label("·").classes("text-[#3F6B52]")
            age_label = ui.label("—").classes("ae-mono text-[11px] text-[#86B89B]")
            ui.label("·").classes("text-[#3F6B52]")
            mon_label = ui.label("MON: —").classes("ae-mono text-[11px]")

        def update() -> None:
            adapter = context.adapter
            adapter_label.set_content(
                f'<span class="ae-mono text-[11px] text-[#86B89B]">ADAPTADOR: '
                f'<span style="color:{COLORS["text"]}">{adapter.interface or "—"}</span></span>'
            )
            db_label.set_content(
                f'<span class="ae-mono text-[11px] text-[#86B89B]">LATENCIA DB: '
                f'<span style="color:{COLORS["mint"]}">local</span></span>'
            )
            scan = context.last_scan()
            age_label.set_text(f"ÚLTIMA ACT: {fmt_age(scan.timestamp) if scan else '—'}")
            if context.monitor_running():
                mon_label.set_text("MON: ACTIVO")
                mon_label.style(f"color:{COLORS['mint']}")
            else:
                mon_label.set_text("MON: —")
                mon_label.style(f"color:{COLORS['text-muted']}")

        update()
        with ui.row().classes("items-center gap-2"):
            status_dot(COLORS["cyan"], pulse=context.scanning)
            state_label = ui.label("").classes("ae-mono text-[11px] text-[#39D0FF]")

        def update_state() -> None:
            state_label.set_text("[ESTADO: ESCANEANDO...]" if context.scanning else "[ESTADO: EN ESPERA]")

        update_state()
        ui.timer(1.0, update)
        ui.timer(0.5, update_state)


@contextmanager
def shell(active: str, title: str) -> Iterator[ui.column]:
    """Monta el shell y devuelve el contenedor de contenido."""
    theme.install()
    ui.page_title(f"{title} · AETHERNET")
    if get_context().settings.compact:
        ui.run_javascript("document.documentElement.classList.add('ae-compact')")

    with ui.header(elevated=False).classes(
        "ae-surface h-16 px-0 border-b border-[#1B3324]"
    ).style(f"background:{COLORS['surface-1']}"):
        _header()

    with ui.left_drawer(value=True, fixed=True, bordered=False).classes(
        "ae-sidebar"
    ).style(
        f"background:{COLORS['surface-1']};width:220px;border-right:1px solid {COLORS['border']};"
        "padding:0;display:flex;flex-direction:column;justify-content:space-between"
    ):
        with ui.column().classes("gap-1 w-full p-2 pt-3"):
            label_caps("Módulos de Rastreo")
            _nav(active)
        _sidebar_footer()

    with ui.footer(elevated=False).classes("h-10 px-0 border-t border-[#1B3324]").style(
        f"background:{COLORS['surface-1']}"
    ):
        _footer()

    with ui.column().classes("w-full gap-4 p-4 md:p-6 ae-fade-up") as content:
        yield content
