"""Ajustes: hardware, captura, alertas, display, persistencia y atajos."""

from __future__ import annotations

import tarfile
import time
from typing import Any

from nicegui import ui

from ...config import save_settings
from ...core.adapter import hardware_suggestions, honest_limits
from ...core.didactic import all_topics
from ..components import kv_row, label_caps, panel_header, toast
from ..shell import shell
from ..state import get_context
from ..theme import COLORS

_PALETTES = {
    "dark": {"--ae-void": "#0A0E14", "--ae-surface-1": "#0A1510", "--ae-mint": "#00E5A0", "--ae-primary": "#7CFFB2"},
    "terminal": {"--ae-void": "#001A0E", "--ae-surface-1": "#032314", "--ae-mint": "#00FF9C", "--ae-primary": "#47ffb8"},
    "amber": {"--ae-void": "#160D04", "--ae-surface-1": "#22140A", "--ae-mint": "#FFBE36", "--ae-primary": "#ffe1b1"},
}
_SHORTCUTS = (
    ("Paleta de comandos", "Ctrl + K"),
    ("Buscar redes y BSSID", "/"),
    ("Forzar ciclo de escaneo RF", "R"),
    ("Exportar informe", "Ctrl + E"),
    ("Copiar canal activo", "C"),
    ("Navegar entre módulos 01-07", "1 .. 7"),
)


@ui.page("/ajustes")
def settings_page() -> None:
    context = get_context()
    with shell("/ajustes", "Ajustes"):
        with ui.element("div").classes("ae-panel flex flex-wrap items-center justify-between gap-3 w-full"):
            with ui.column().classes("gap-0"):
                ui.label("CONFIGURACIÓN Y CALIBRACIÓN DE FIRMWARE").classes("ae-headline text-lg text-[#D8F5E3]")
                label_caps("SISTEMA // PANEL 07")
            with ui.row().classes("items-center gap-2"):
                selftest_badge = ui.html('<span class="ae-chip">SELF-TEST PENDIENTE</span>')
                test_btn = ui.button("DIAGNÓSTICO DEL SISTEMA", icon="sync").props("unelevated no-caps").style(
                    f"background:{COLORS['surface-2']};color:{COLORS['text']}"
                )

        with ui.element("div").classes("grid grid-cols-1 xl:grid-cols-12 gap-5 w-full"):
            with ui.element("div").classes("xl:col-span-7 flex flex-col gap-5"):
                # -- captura RF --------------------------------------#
                with ui.element("div").classes("ae-panel flex flex-col gap-3"):
                    adapter = context.adapter
                    with ui.row().classes("items-center justify-between w-full"):
                        panel_header("settings_input_antenna", "MÓDULO 01 // INTERFAZ DE CAPTURA RF", None, COLORS["cyan"])
                        ui.html(f'<span class="ae-chip active">PHY: {adapter.mode.upper()}</span>')
                    with ui.element("div").classes("ae-sub p-3 flex flex-col gap-2"):
                        ui.label(f"{adapter.driver or 'Adaptador'} · {adapter.interface or '—'}").classes(
                            "ae-headline text-sm text-[#D8F5E3]"
                        )
                        kv_row("CHIPSET", adapter.chipset or "n/d")
                        kv_row("BANDAS", ", ".join(b.value for b in adapter.bands) or "desconocidas")
                        kv_row("MONITOR MODE", "soportado" if adapter.supports_monitor else "no disponible",
                               COLORS["mint"] if adapter.supports_monitor else COLORS["coral"])
                        kv_row("INYECCIÓN", "soportada" if adapter.supports_injection else "no disponible",
                               COLORS["mint"] if adapter.supports_injection else COLORS["coral"])
                    # -- monitor pasivo (no disruptivo) --------------#
                    status = context.monitor_status()
                    with ui.element("div").classes("ae-sub p-3 flex flex-col gap-2"):
                        with ui.row().classes("items-center justify-between w-full"):
                            label_caps("MONITOR PASIVO")
                            ui.html(
                                f'<span class="ae-chip{" active" if status["capable"] else ""}">'
                                f'{"DISPONIBLE" if status["capable"] else "NO DISPONIBLE"}</span>'
                            )
                        ui.label(
                            "Crea una interfaz virtual de monitor. Nunca cambia el tipo de tu interfaz "
                            "gestionada, así que no corta tu WiFi. Solo escucha."
                        ).classes("text-[11px] text-[#86B89B]")
                        if not status["capable"]:
                            ui.label(f"Motivo: {status['reason']}").classes("text-[11px]").style(
                                f"color:{COLORS['amber']}"
                            )
                        consent = ui.switch(
                            "Acepto auditar solo mi propia red",
                            value=context.settings.consent_monitor,
                        ).props("dense")
                        monitor_switch = ui.switch(
                            "Activar captura pasiva (deauth / probes / beacons / EAPOL)",
                            value=context.settings.monitor_enabled and context.monitor_running(),
                        ).props("dense" + ("" if status["capable"] else " disable"))
                        mon_info = ui.label("").classes("ae-mono text-[11px] text-[#86B89B]")

                        def refresh_mon() -> None:
                            if context.monitor_running():
                                st = context.monitor_status()
                                mon_info.set_text(
                                    f"ACTIVO · {st['interface']} · CH {st['current_channel']} · "
                                    f"{st['packet_count']} pkts · {st['event_count']} eventos"
                                )
                            else:
                                mon_info.set_text("detenido")

                        def on_monitor(event: Any) -> None:
                            if event.value and not consent.value:
                                toast("Marca el consentimiento antes de activar", icon_name="gpp_maybe", color=COLORS["amber"])
                                monitor_switch.set_value(False)
                                return
                            def _after_toggle(_result: object) -> None:
                                ui.timer(0.1, refresh_mon, once=True)

                            context.set_monitor_enabled(bool(event.value), on_done=_after_toggle)
                            toast("Monitor activado" if event.value else "Monitor detenido", icon_name="sensors")

                        def on_consent(event: Any) -> None:
                            context.settings.consent_monitor = bool(event.value)
                            persist("Consentimiento guardado")

                        monitor_switch.on_value_change(on_monitor)
                        consent.on_value_change(on_consent)
                        refresh_mon()
                        ui.timer(2.0, refresh_mon)

                    ui.switch("Inyección de frames (no implementado)", value=False).props("dense disable")
                    for limit in honest_limits(adapter):
                        ui.label("· " + limit).classes("text-[11px] text-[#86B89B]")
                    for suggestion in hardware_suggestions(adapter):
                        ui.label("→ " + suggestion).classes("text-[11px] text-[#3F6B52] italic")

                # -- muestreo ----------------------------------------#
                with ui.element("div").classes("ae-panel flex flex-col gap-3"):
                    panel_header("tune", "MÓDULO 02 // FRECUENCIA DE MUESTREO", "HOPPING Y DISCRIMINACIÓN", COLORS["mint"])
                    label_caps("INTERVALO DE ESCANEO CONTINUO")
                    interval_toggle = ui.toggle([1, 5, 12, 15, 30, 60], value=context.settings.scan_interval_min).props("dense no-caps")
                    label_caps("DWELL TIME POR CANAL")
                    dwell_slider = ui.slider(min=50, max=250, step=10, value=context.settings.dwell_ms).props("label")
                    label_caps("DISCRIMINADOR DE RUIDO RSSI (dBm)")
                    rssi_slider = ui.slider(min=-100, max=-60, step=1, value=context.settings.rssi_floor_dbm).props("label")

                # -- disparadores ------------------------------------#
                with ui.element("div").classes("ae-panel flex flex-col gap-2"):
                    panel_header("notifications_active", "MÓDULO 04 // DISPARADORES DE ALERTA", "TRIGGERS", COLORS["amber"])
                    notify_switch = ui.switch("Notificación de escritorio ante eventos", value=context.settings.notifications).props("dense")
                    sound_switch = ui.switch("Alerta sonora en saturación", value=context.settings.sound).props("dense")
                    quiet_switch = ui.switch("Modo silencioso por horas", value=context.settings.quiet_enabled).props("dense")
                    redact_switch = ui.switch("Ocultar MACs en informes", value=context.settings.redact_macs_in_reports).props("dense")

            with ui.element("div").classes("xl:col-span-5 flex flex-col gap-5"):
                # -- display -----------------------------------------#
                with ui.element("div").classes("ae-panel flex flex-col gap-3"):
                    panel_header("palette", "MÓDULO 03 // DISPLAY", "MATRIZ CROMÁTICA", COLORS["cyan"])
                    palette_row = ui.row().classes("items-center gap-3")
                    with palette_row:
                        for key, text, bg in (
                            ("dark", "Oscuro Estándar", "#0A0E14"),
                            ("terminal", "Fósforo Verde", "#001A0E"),
                            ("amber", "Ámbar Cósmico", "#160D04"),
                        ):
                            active = context.settings.theme == key
                            card = ui.element("div").classes("ae-sub p-3 cursor-pointer flex flex-col gap-1").style(
                                f"border-color:{COLORS['mint'] if active else COLORS['border']}"
                            )
                            with card:
                                ui.element("div").style(f"width:100%;height:26px;border-radius:8px;background:{bg};border:1px solid {COLORS['border']}")
                                ui.label(text).classes("ae-label")
                                label_caps("ACTIVO" if active else "STANDBY", COLORS["mint"] if active else None)
                            card.on("click", lambda _=None, k=key: set_palette(k))
                    label_caps("ESCALA DE INTERFAZ")
                    with ui.row().classes("items-center gap-2"):
                        for scale in (100, 110, 125):
                            chip = ui.html(f"{scale}%").classes(
                                "ae-chip" + (" active" if context.settings.ui_scale == scale else "")
                            ).style("cursor:pointer")
                            chip.on("click", lambda _=None, s=scale: set_scale(s))

                # -- persistencia ------------------------------------#
                with ui.element("div").classes("ae-panel flex flex-col gap-3"):
                    panel_header("database", "MÓDULO 05 // PERSISTENCIA SQLITE3", "I/O LOCAL", COLORS["mint"])
                    size = context.paths.db_path.stat().st_size if context.paths.db_path.exists() else 0
                    kv_row("RUTA", str(context.paths.db_path))
                    kv_row("TAMAÑO", f"{size / 1_048_576:.2f} MB")
                    kv_row("REGISTROS", str(sum(context.counts().get(k, 0) for k in ("wifi_scans", "visible_networks"))))
                    label_caps("RETENCIÓN AUTOMÁTICA (DÍAS · 0 = DESACTIVADA)")
                    retention = ui.number(
                        value=context.settings.retention_days, min=0, max=3650, step=30
                    ).props("dense outlined").classes("w-full")
                    with ui.row().classes("items-center gap-2 w-full"):
                        purge_btn = ui.button("PURGAR AHORA", icon="auto_delete").props("unelevated no-caps dense").style(
                            f"background:{COLORS['surface-2']};color:{COLORS['amber']};flex:1"
                        )
                        backup_btn = ui.button("RESPALDO .TAR.GZ", icon="archive").props("unelevated no-caps dense").style(
                            f"background:{COLORS['surface-2']};color:{COLORS['mint']};flex:1"
                        )

                # -- atajos ------------------------------------------#
                with ui.element("div").classes("ae-panel flex flex-col gap-2"):
                    panel_header("keyboard", "MÓDULO 06 // ATAJOS", "ANSI MAPPING", COLORS["cyan"])
                    for text, keys in _SHORTCUTS:
                        with ui.row().classes("items-center justify-between w-full"):
                            ui.label(text).classes("text-[12px] text-[#86B89B]")
                            ui.html(f'<span class="ae-chip">{keys}</span>')
                    with ui.expansion("Glosario didáctico", icon="help").classes("w-full"):
                        for topic in all_topics():
                            ui.label(f"{topic.title}: {topic.summary}").classes("text-[11px] text-[#86B89B]")

        # -- persistencia de ajustes ---------------------------------#
        def persist(message: str = "Ajustes guardados") -> None:
            save_settings(context.settings, context.paths)
            context.reload_settings()
            toast(message, icon_name="save")

        def set_palette(key: str) -> None:
            context.settings.theme = key
            persist(f"Paleta '{key}' aplicada")
            variables = _PALETTES.get(key, {})
            ui.run_javascript(
                ";".join(f"document.documentElement.style.setProperty('{k}','{v}')" for k, v in variables.items())
            )

        def set_scale(scale: int) -> None:
            context.settings.ui_scale = scale
            persist(f"Escala {scale}% (se aplica al recargar)")

        def on_setting(field: str, value: Any) -> None:
            setattr(context.settings, field, value)
            persist()

        def run_selftest() -> None:
            context.refresh_capabilities()
            ok = sum(1 for tool in context.capabilities.tools if tool.available)
            total = len(context.capabilities.tools)
            selftest_badge.set_content(f'<span class="ae-chip active">PASADO: {ok}/{total} OK</span>')
            toast(f"Diagnóstico: {ok}/{total} componentes disponibles", icon_name="check_circle")

        def purge() -> None:
            days = context.settings.retention_days or 90
            removed = context.repo.purge_old(days)
            total = sum(removed.values())
            persist(f"Purgados {total} registros >{days} días")

        def backup() -> None:
            target = context.paths.data_dir / f"aethernet-backup-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"
            with tarfile.open(target, "w:gz") as tar:
                tar.add(context.paths.db_path, arcname="aethernet.db")
            toast(f"Respaldo: {target.name}", icon_name="archive")

        interval_toggle.on_value_change(lambda e: on_setting("scan_interval_min", int(e.value)))
        dwell_slider.on_value_change(lambda e: on_setting("dwell_ms", int(e.value)))
        rssi_slider.on_value_change(lambda e: on_setting("rssi_floor_dbm", int(e.value)))
        notify_switch.on_value_change(lambda e: on_setting("notifications", bool(e.value)))
        sound_switch.on_value_change(lambda e: on_setting("sound", bool(e.value)))
        quiet_switch.on_value_change(lambda e: on_setting("quiet_enabled", bool(e.value)))
        redact_switch.on_value_change(lambda e: on_setting("redact_macs_in_reports", bool(e.value)))
        retention.on_value_change(lambda e: on_setting("retention_days", int(e.value or 0)))
        test_btn.on("click", run_selftest)
        purge_btn.on("click", purge)
        backup_btn.on("click", backup)
        run_selftest()
