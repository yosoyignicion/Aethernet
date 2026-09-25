"""Descubrimiento y diagnóstico del adaptador WiFi.

Fuente primaria: ``iw`` y ``nmcli``. Si ``iw`` no está, degradamos con lo poco
que ``nmcli`` pueda decir. Nada aquí necesita privilegios.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

from ..logging_setup import get_logger
from ..models import AdapterInfo, Band
from ..utils import run_command


class IwPhyInfo(TypedDict):
    """Resultado tipado de :func:`parse_iw_phy`."""

    bands: tuple[Band, ...]
    modes: set[str]
    injection_hint: bool

log = get_logger(__name__)

_IFACE_RE = re.compile(r"Interface\s+(\S+)")
_PHY_RE = re.compile(r"wiphy\s+(\d+)")
_TYPE_RE = re.compile(r"type\s+(\S+)")
_FREQ_RE = re.compile(r"(\d{4})\s+MHz")
_MODE_RE = re.compile(r"^\s*\*\s+([A-Za-z0-9_/ -]+?)\s*$")


def list_wireless_interfaces() -> list[str]:
    """Interfaces WiFi presentes, vía ``nmcli`` (preferido) o ``iw``."""
    result = run_command(["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"], timeout=6)
    ifaces: list[str] = []
    if result.ok:
        for line in result.lines():
            parts = line.split(":")
            if len(parts) >= 2 and parts[-1] == "wifi":
                ifaces.append(parts[0])
    if ifaces:
        return ifaces

    iw = run_command(["iw", "dev"], timeout=6)
    if iw.ok:
        return _IFACE_RE.findall(iw.stdout)
    return ifaces


def probe_adapter(interface: str) -> AdapterInfo:
    """Inspecciona un adaptador y devuelve sus capacidades reales."""
    if not interface:
        interface = _first_or_empty()
    driver, chipset = _driver_info(interface)
    mode, phy = _dev_info(interface)

    bands: tuple[Band, ...] = ()
    modes: set[str] = set()
    injection_hint = False
    if phy:
        info = run_command(["iw", "phy", phy, "info"], timeout=10)
        if info.ok:
            parsed = parse_iw_phy(info.stdout)
            bands = parsed["bands"]
            modes = parsed["modes"]
            injection_hint = parsed["injection_hint"]
    elif interface:
        info = run_command(["iw", "dev", interface, "info"], timeout=6)
        if info.ok:
            bands = _bands_from_text(info.stdout)

    supports_monitor = bool(modes & {"monitor"})
    return AdapterInfo(
        interface=interface,
        driver=driver,
        chipset=chipset,
        phy=phy,
        mode=mode or "managed",
        bands=bands,
        supports_monitor=supports_monitor,
        supports_injection=injection_hint and supports_monitor,
        supports_ap=bool(modes & {"AP", "ap"}),
        supports_5ghz=Band.GHZ_5 in bands or Band.GHZ_6 in bands,
        raw={"modes": sorted(modes)},
    )


def _first_or_empty() -> str:
    ifaces = list_wireless_interfaces()
    return ifaces[0] if ifaces else ""


def _driver_info(interface: str) -> tuple[str | None, str | None]:
    if not interface:
        return None, None
    driver = None
    sys_path = Path(f"/sys/class/net/{interface}/device/driver")
    try:
        driver = sys_path.resolve().name
    except OSError:
        driver = None
    chipset = None
    result = run_command(["ethtool", "-i", interface], timeout=5)
    if result.ok:
        fields = {}
        for line in result.lines():
            if ":" in line:
                key, _, value = line.partition(":")
                fields[key.strip()] = value.strip()
        driver = driver or fields.get("driver")
        bus = fields.get("bus-info")
        if bus:
            chipset = f"{fields.get('driver', driver)} @ {bus}"
    return driver, chipset


def _dev_info(interface: str) -> tuple[str | None, str | None]:
    if not interface:
        return None, None
    result = run_command(["iw", "dev", interface, "info"], timeout=6)
    if not result.ok:
        return None, None
    mode_match = _TYPE_RE.search(result.stdout)
    phy_match = _PHY_RE.search(result.stdout)
    return (mode_match.group(1) if mode_match else None, phy_match.group(1) if phy_match else None)


def _bands_from_text(text: str) -> tuple[Band, ...]:
    freqs = {int(m) for m in _FREQ_RE.findall(text)}
    bands = {Band.from_frequency(f) for f in freqs}
    return tuple(sorted((b for b in bands if b is not Band.UNKNOWN), key=lambda b: b.value))


def parse_iw_phy(text: str) -> IwPhyInfo:
    """Parser puro de ``iw phy <phy> info`` (testeable sin hardware)."""
    bands: set[Band] = set()
    modes: set[str] = set()
    injection_hint = "injection" in text.lower()
    in_modes = False
    for line in text.splitlines():
        for freq in _FREQ_RE.findall(line):
            band = Band.from_frequency(int(freq))
            if band is not Band.UNKNOWN:
                bands.add(band)
        if "Supported interface modes" in line or "Software interface modes" in line:
            in_modes = True
            continue
        if in_modes:
            match = _MODE_RE.match(line)
            if match:
                modes.add(match.group(1).strip())
                continue
            if line.strip() and not line.startswith((" ", "\t", "*")):
                in_modes = False
    ordered = tuple(sorted(bands, key=lambda b: b.value))
    return {"bands": ordered, "modes": modes, "injection_hint": injection_hint}


def honest_limits(adapter: AdapterInfo | None) -> list[str]:
    """Qué NO puede hacer la app con este hardware, en lenguaje claro."""
    limits: list[str] = []
    if adapter is None or not adapter.interface:
        return ["No se detectó ningún adaptador WiFi."]
    if not adapter.supports_monitor:
        limits.append("Sin monitor mode: no habrá detección de deauth/probes ni escaneo pasivo real.")
    if not adapter.supports_injection:
        limits.append("Sin inyección: no se puede auditar WPS ni hacer handshake capture.")
    if not adapter.bands:
        limits.append("No se pudieron determinar las bandas soportadas (instala 'iw' para saberlo).")
    elif not adapter.supports_5ghz:
        limits.append("Adaptador solo 2.4 GHz: las redes de 5/6 GHz no aparecerán en tus escaneos.")
    if not adapter.supports_ap:
        limits.append("Sin modo AP: no se puede montar un punto de acceso de señuelo.")
    return limits


def hardware_suggestions(adapter: AdapterInfo | None) -> list[str]:
    """Recomendaciones concretas para ampliar capacidades."""
    suggestions: list[str] = []
    if adapter is None or not adapter.supports_monitor:
        suggestions.append(
            "Para monitor mode busca un adaptador con chipset Atheros AR9271, "
            "RTL8812AU/8821AU o MediaTek MT7612U."
        )
    if adapter is not None and adapter.supports_monitor and not adapter.supports_injection:
        suggestions.append(
            "Tu adaptador parece soportar monitor mode; verifica inyección con "
            "'aireplay-ng --test' antes de confiar en ella."
        )
    return suggestions
