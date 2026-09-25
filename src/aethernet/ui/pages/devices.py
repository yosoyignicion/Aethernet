"""Dispositivos: gestión de nodos LAN con confianza y alias."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from ...models import LanDevice
from ..components import empty_state, label_caps, toast
from ..shell import shell
from ..state import fmt_age, get_context
from ..theme import COLORS, icon

_TYPE_HINTS = (
    ("raspberry", "IOT", "sensors"),
    ("espressif", "IOT", "sensors"),
    ("sonoff", "IOT", "sensors"),
    ("apple", "MÓVIL", "smartphone"),
    ("samsung", "MÓVIL", "smartphone"),
    ("xiaomi", "MÓVIL", "smartphone"),
    ("sony", "TV", "tv"),
    ("lg electronics", "TV", "tv"),
    ("intel", "PC", "laptop_mac"),
    ("dell", "PC", "laptop_chromebook"),
    ("hewlett", "PC", "laptop_mac"),
    ("vmware", "VIRTUAL", "developer_board"),
    ("router", "ROUTER", "router"),
)


def _device_type(device: LanDevice) -> tuple[str, str]:
    if device.is_gateway:
        return "ROUTER", "router"
    haystack = f"{device.vendor or ''} {device.hostname or ''}".lower()
    for needle, label, icon_name in _TYPE_HINTS:
        if needle in haystack:
            return label, icon_name
    return "DESCONOCIDO", "device_unknown"


@ui.page("/dispositivos")
def devices_page() -> None:
    context = get_context()
    with shell("/dispositivos", "Dispositivos"):
        state: dict[str, Any] = {"query": ""}

        lan = context.repo.latest_lan_scan()
        subnet = lan.subnet if lan else "—"
        with ui.element("div").classes("ae-panel flex flex-wrap items-center justify-between gap-3"):
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
            grid.clear()
            if not devices:
                with grid:
                    empty_state("Sin dispositivos. Ejecuta un escaneo LAN.", "lan")
                return
            with grid:
                for device in devices:
                    _device_card(context, device, render_grid.refresh)

        def on_search(event: Any) -> None:
            state["query"] = event.value or ""
            render_grid.refresh()

        def do_arp() -> None:
            started = context.scan_async(include_lan=True, on_done=lambda _: ui.timer(0.1, render_grid.refresh, once=True))
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


def _device_card(context: Any, device: LanDevice, refresh: Callable[[], None]) -> None:
    type_label, type_icon = _device_type(device)
    trusted = device.trusted or device.is_gateway
    accent = COLORS["mint"] if trusted else COLORS["amber"]
    with ui.element("div").classes("ae-card flex flex-col gap-3").style(
        f"border-color:{accent if not trusted else COLORS['border']}"
    ):
        with ui.row().classes("items-center justify-between w-full"):
            ui.html(f'<span class="ae-chip">{icon(type_icon, size=13)} {type_label}</span>')
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
            _line("FABRICANTE (OUI)", device.vendor or "Sin identificar")
            _line("ÚLTIMA VEZ", fmt_age(device.last_seen))
        with ui.row().classes("items-center gap-2 w-full"):
            label = "Revocar Confianza" if trusted else "Marcar Confiable"
            toggle = ui.button(label, icon="verified_user" if trusted else "gpp_good").props(
                "unelevated no-caps dense"
            ).style(f"background:{COLORS['surface-2']};color:{accent};flex:1")
            isolate = ui.button("Aislar", icon="block").props("unelevated no-caps dense disabled").style(
                f"background:{COLORS['surface-2']};color:{COLORS['text-dim']};flex:1"
            )
            isolate.tooltip("Aislar requiere integración con el router/firewall (pendiente)")

            def toggle_trust(_: Any = None, mac: str = device.mac, current: bool = trusted) -> None:
                context.repo.set_device_trusted(mac, not current)
                toast(f"{'Revocado' if current else 'Confiable'}: {mac}", icon_name="verified_user")
                refresh()

            toggle.on("click", toggle_trust)


def _line(key: str, value: str) -> None:
    with ui.row().classes("items-center justify-between w-full"):
        label_caps(key)
        ui.label(value).classes("ae-mono text-[11px] text-[#D8F5E3] truncate max-w-[60%]")
