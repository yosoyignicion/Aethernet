"""Detección de capacidades del sistema (feature 11: configuración honesta).

No asume nada: comprueba binarios externos, módulos Python opcionales y el
adaptador. La UI y el CLI usan esto para decir la verdad sobre lo que se puede
hacer en este equipo.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolCapability:
    name: str
    available: bool
    detail: str = ""
    feature: str = ""


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    tools: tuple[ToolCapability, ...] = ()
    python: str = field(default_factory=lambda: sys.version.split()[0])
    is_root: bool = False
    wifi_interfaces: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def has(self, name: str) -> bool:
        return any(t.name == name and t.available for t in self.tools)

    def missing(self) -> tuple[ToolCapability, ...]:
        return tuple(t for t in self.tools if not t.available)

    def to_dict(self) -> dict[str, Any]:
        return {
            "python": self.python,
            "is_root": self.is_root,
            "wifi_interfaces": list(self.wifi_interfaces),
            "tools": [
                {
                    "name": t.name,
                    "available": t.available,
                    "detail": t.detail,
                    "feature": t.feature,
                }
                for t in self.tools
            ],
            "notes": list(self.notes),
        }


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def detect(interface: str | None = None) -> CapabilityReport:
    tools: list[ToolCapability] = []

    def tool(name: str, path_attr: str, feature: str) -> None:
        path = shutil.which(path_attr)
        tools.append(
            ToolCapability(
                name=name,
                available=path is not None,
                detail=path or "no instalado",
                feature=feature,
            )
        )

    tool("nmcli", "nmcli", "escaneo WiFi y estado del adaptador (esencial)")
    tool("iw", "iw", "capacidades del adaptador y modo monitor")
    tool("ethtool", "ethtool", "driver y chipset del adaptador")
    tool("notify-send", "notify-send", "notificaciones de escritorio")
    tool("ip", "ip", "subred y vecinos ARP")
    tool("arp", "arp", "respaldo de inventario LAN")
    tool("paplay", "paplay", "sonido opcional de alertas")
    tool("canberra-gtk-play", "canberra-gtk-play", "sonido opcional de alertas")

    for module, feature in (
        ("scapy", "ARP scan activo de la LAN"),
        ("fastapi", "API local (opcional)"),
        ("uvicorn", "servidor de la API local"),
        ("reportlab", "informes PDF"),
        ("matplotlib", "gráficos embebidos en informes"),
        ("speedtest", "test de velocidad correlacionado"),
        ("customtkinter", "interfaz gráfica"),
    ):
        available = _module_available(module)
        tools.append(
            ToolCapability(
                name=f"py:{module}",
                available=available,
                detail="importable" if available else "pip install necesario",
                feature=feature,
            )
        )

    try:
        is_root = os_geteuid() == 0
    except AttributeError:
        is_root = False

    wifi_interfaces: tuple[str, ...] = ()
    try:
        from .core.adapter import list_wireless_interfaces

        wifi_interfaces = tuple(list_wireless_interfaces())
    except Exception:  # pragma: no cover - hardware-dependent
        wifi_interfaces = ()

    notes: list[str] = []
    if not shutil.which("nmcli") and not shutil.which("iw"):
        notes.append("Sin nmcli ni iw no se puede escanear WiFi.")
    if wifi_interfaces:
        notes.append(f"Interfaces WiFi detectadas: {', '.join(wifi_interfaces)}.")
    else:
        notes.append("No se detectaron interfaces WiFi.")
    if not is_root:
        notes.append("Sin root: ARP scan activo y monitor mode pueden estar limitados.")

    return CapabilityReport(
        tools=tuple(tools),
        is_root=is_root,
        wifi_interfaces=wifi_interfaces,
        notes=tuple(notes),
    )


def os_geteuid() -> int:  # aislado para poder mockear en tests
    import os

    return os.geteuid()


def load_oui_database(paths: Path | None = None) -> int:
    """Punto de entrada para precargar la base OUI; devuelve entradas cargadas."""
    from .core.oui import OuiDatabase

    db = OuiDatabase(paths)
    db.load()
    return db.size
