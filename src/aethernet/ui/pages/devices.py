"""Dispositivos: gestión de nodos LAN con confianza y alias."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from ...core.devices import classify_device
from ...core.fingerprint import classify_services, probe_ports, service_names
from ...logging_setup import get_logger
from ...models import LanDevice
from ..components import empty_state, label_caps, toast
from ..shell import shell
from ..state import fmt_age, get_context
from ..theme import COLORS, icon

log = get_logger(__name__)


@ui.page("/dispositivos")
def devices_page() -> None:
    context = get_context()
    with shell("/dispositivos", "Dispositivos"):
        state: dict[str, Any] = {"query": ""}

        lan = context.repo.latest_lan_scan()
        subnet = lan.subnet if lan else "—"
        with ui.element("div").classes("ae-panel flex flex-wrap items-center justify-between gap-3 w-full"):
            with ui.column().classes("gap-0"):
                header_label = ui.label("0 Dispositivos en LAN local").classes("ae-headline text-lg text-[#D8F5E3]")
                with ui.row().classes("items-center gap-2"):
                    label_caps("MATRIZ // SUBNET_SCANNER")
                    ui.html(f'<span class="ae-chip active">CIDR {subnet}</span>')
                    summary_label = ui.label("").classes("text-[11px] text-[#86B89B]")
            with ui.row().classes("items-center gap-2"):
                search = ui.input(placeholder="Filtrar IP, MAC o Vendor...").props(
                    'type=search clearable dense outlined'
                ).classes("min-w-[240px]")
                arp_btn = ui.button("Escanear ARP", icon="sync").props("unelevated no-caps").style(
                    f"background:{COLORS['surface-2']};color:{COLORS['text']}"
                )

        grid = ui.element("div").classes("grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 w-full")

        with ui.element("div").classes("ae-panel flex flex-col gap-3"):
            with ui.row().classes("items-center gap-2"):
                ui.html(icon("add_link", size=18, color=COLORS["mint"]))
                ui.label("Añadir Regla MAC Estática").classes("ae-headline text-sm text-[#D8F5E3]")
            ui.label(
                "Asigna una regla permanente ARP/DHCP: la MAC quedará como confiable con su alias."
            ).classes("text-[11px] text-[#86B89B]")
            with ui.row().classes("items-end gap-3 flex-wrap"):
                mac_input = ui.input("MAC", placeholder="AA:BB:CC:DD:EE:FF").props("dense outlined").classes("w-[220px]")
                alias_input = ui.input("ALIAS", placeholder="Etiqueta...").props("dense outlined").classes("w-[200px]")
                assign_btn = ui.button("Asignar", icon="add_link").props("unelevated no-caps").style(
                    f"background:{COLORS['mint']};color:#0A0E14"
                )

        @ui.refreshable
        def render_grid() -> None:
            devices = context.repo.devices()
            query = state["query"].strip().lower()
            if query:
                devices = [
                    d
                    for d in devices
                    if query in d.ip.lower() or query in d.mac.lower() or query in (d.vendor or "").lower()
                    or query in (d.alias or "").lower() or query in (d.hostname or "").lower()
                ]
            header_label.set_text(f"{len(devices)} Dispositivos en LAN local")
            trusted = sum(1 for d in devices if d.trusted)
            suspicious = sum(1 for d in devices if not d.trusted and not d.is_gateway)
            summary_label.set_text(f"({trusted} seguros · {suspicious} sin confiar)")
            services_by_mac = context.repo.device_service_map()
            grid.clear()
            if not devices:
                with grid:
                    empty_state("Sin dispositivos. Ejecuta un escaneo LAN.", "lan")
                return
            with grid:
                for device in devices:
                    _device_card(context, device, render_grid.refresh, services_by_mac.get(device.mac, []))

        def on_search(event: Any) -> None:
            state["query"] = event.value or ""
            render_grid.refresh()

        def _after_arp(_result: object) -> None:
            ui.timer(0.1, render_grid.refresh, once=True)

        def do_arp() -> None:
            started = context.scan_async(include_lan=True, on_done=_after_arp)
            toast("Escaneo ARP en curso" if started else "Escaneo ya en curso", icon_name="search")

        def assign() -> None:
            mac = (mac_input.value or "").strip().upper().replace("-", ":")
            if len(mac.split(":")) != 6:
                toast("MAC no válida", icon_name="error", color=COLORS["coral"])
                return
            context.repo.set_device_trusted(mac, True, (alias_input.value or "").strip() or None)
            toast(f"Regla registrada para {mac}", icon_name="add_link")
            mac_input.set_value(None)
            alias_input.set_value(None)
            render_grid.refresh()

        search.on_value_change(on_search)
        arp_btn.on("click", do_arp)
        assign_btn.on("click", assign)
        render_grid()
        ui.timer(5.0, render_grid.refresh)


def _device_card(
    context: Any, device: LanDevice, refresh: Callable[..., Any], services: list[dict[str, Any]]
) -> None:
    kind = classify_device(device)
    trusted = device.trusted or device.is_gateway
    accent = COLORS["mint"] if trusted else COLORS["amber"]
    with ui.element("div").classes("ae-card flex flex-col gap-3").style(
        f"border-color:{accent if not trusted else COLORS['border']}"
    ):
        with ui.row().classes("items-center justify-between w-full"):
            ui.html(f'<span class="ae-chip">{icon(kind.icon, size=13)} {kind.label}</span>')
            ui.html(
                f'<span class="ae-chip{" active" if trusted else ""}">'
                f'{"SEGURO // VERIFICADO" if trusted else "NO CONFIABLE"}</span>'
            )
        with ui.row().classes("items-center justify-between w-full"):
            ui.label(device.display_name).classes("ae-headline text-base text-[#D8F5E3] truncate")
            ui.html(icon("edit", size=16, color=COLORS["text-muted"]))
        with ui.column().classes("gap-1 w-full"):
            _line("DIRECCIÓN IP", device.ip)
            _line("DIRECCIÓN MAC", device.mac)
            _line("HOSTNAME", device.hostname or "sin resolver")
            _line("FABRICANTE (OUI)", device.vendor or "Sin identificar")
            _line("IDENTIFICACIÓN", f"{kind.label} ({kind.confidence}) · {kind.reason}")
            if services:
                profile = classify_services([s["port"] for s in services])
                _line("PERFIL (SERVICIOS)", f"{profile.role} ({profile.confidence}) · {profile.reason}")
                _line("ÚLTIMO SONDEO", fmt_age(max(s["scanned_at"] for s in services)))
            _line("ÚLTIMA VEZ", fmt_age(device.last_seen))
        if services:
            with ui.column().classes("gap-1 w-full"):
                label_caps("SERVICIOS DETECTADOS")
                with ui.row().classes("gap-1 flex-wrap"):
                    for name in service_names([s["port"] for s in services]):
                        ui.html(f'<span class="ae-chip">{name}</span>')
        with ui.row().classes("items-center gap-2 w-full"):
            label = "Revocar Confianza" if trusted else "Marcar Confiable"
            toggle = ui.button(label, icon="verified_user" if trusted else "gpp_good").props(
                "unelevated no-caps dense"
            ).style(f"background:{COLORS['surface-2']};color:{accent};flex:1")
            identify = ui.button("Identificar", icon="travel_explore").props(
                "unelevated no-caps dense"
            ).style(f"background:{COLORS['surface-2']};color:{COLORS['cyan']};flex:1")
            identify.tooltip("Sonda puertos comunes en tu propia LAN (activo, bajo petición)")
            isolate = ui.button("Aislar", icon="block").props("unelevated no-caps dense disabled").style(
                f"background:{COLORS['surface-2']};color:{COLORS['text-dim']};flex:1"
            )
            isolate.tooltip("Aislar requiere integración con el router/firewall (pendiente)")

            def toggle_trust(_: Any = None, mac: str = device.mac, current: bool = trusted) -> None:
                context.repo.set_device_trusted(mac, not current)
                toast(f"{'Revocado' if current else 'Confiable'}: {mac}", icon_name="verified_user")
                refresh()

            async def start_identify(_: Any = None, dev: LanDevice = device) -> None:
                toast(f"Identificando {dev.ip}…", icon_name="travel_explore")

                def scan() -> None:
                    ports = probe_ports(dev.ip)
                    context.repo.save_device_fingerprint(dev.mac, dev.ip, ports)

                try:
                    # Sonda de red fuera del event loop; el refresco vuelve al hilo de UI.
                    await run.io_bound(scan)
                except Exception as exc:  # nunca romper la UI
                    log.exception("sonda de servicios falló para %s: %s", dev.ip, exc)
                refresh()

            toggle.on("click", toggle_trust)
            identify.on("click", start_identify)


def _line(key: str, value: str) -> None:
    with ui.row().classes("items-center justify-between w-full"):
        label_caps(key)
        ui.label(value).classes("ae-mono text-[11px] text-[#D8F5E3] truncate max-w-[60%]").tooltip(value)
