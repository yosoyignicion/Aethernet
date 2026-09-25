"""Decodificadores puros de tramas 802.11 → :class:`DecodedFrame`.

scapy se importa de forma perezosa: el módulo se puede importar sin scapy y
solo falla si se intenta decodificar. Así el resto de la app no depende de él.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...models import normalize_bssid

KIND_DEAUTH = "deauth"
KIND_PROBE = "probe"
KIND_BEACON = "beacon"
KIND_EAPOL = "eapol"

_WPS_OUI = b"\x00\x50\xf2\x04"


@dataclass(frozen=True, slots=True)
class DecodedFrame:
    kind: str
    bssid: str = ""
    ssid: str = ""
    source_mac: str = ""
    channel: int = 0
    rssi: int = 0
    summary: str = ""
    detail: str = ""

    @property
    def subject(self) -> str:
        return self.bssid or self.source_mac or self.ssid


def _layers() -> tuple[Any, ...]:
    from scapy.layers.dot11 import (
        Dot11,
        Dot11Beacon,
        Dot11Deauth,
        Dot11Elt,
        Dot11ProbeReq,
    )
    from scapy.layers.eap import EAPOL

    return Dot11, Dot11Beacon, Dot11Deauth, Dot11Elt, Dot11ProbeReq, EAPOL


def _rssi(pkt: Any) -> int:
    value = getattr(pkt, "dBm_AntSignal", None)
    if value is None:
        try:
            from scapy.layers.radiotap import RadioTap

            value = pkt[RadioTap].dBm_AntSignal
        except Exception:  # noqa: BLE001 - sin radiotap no hay RSSI
            value = 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _iter_elts(pkt: Any, Dot11Elt: Any) -> list[Any]:
    elements: list[Any] = []
    elt = pkt.getlayer(Dot11Elt)
    while elt is not None:
        elements.append(elt)
        payload = getattr(elt, "payload", None)
        elt = payload.getlayer(Dot11Elt) if payload is not None else None
    return elements


def _ssid_from_elements(elements: list[Any]) -> str:
    for elt in elements:
        if getattr(elt, "ID", None) == 0:
            info = getattr(elt, "info", b"")
            if isinstance(info, bytes):
                return info.decode("utf-8", "replace")
    return ""


def _channel_from_elements(elements: list[Any]) -> int:
    for elt in elements:
        if getattr(elt, "ID", None) == 3:
            info = getattr(elt, "info", b"")
            if isinstance(info, bytes) and info:
                return info[0]
            if isinstance(info, int):
                return info
    return 0


def is_wps(elements: list[Any]) -> bool:
    """¿Algún elemento de información anuncia WPS (OUI 00:50:F2 tipo 4)?"""
    for elt in elements:
        if getattr(elt, "ID", None) == 221:
            info = getattr(elt, "info", b"")
            if isinstance(info, bytes) and info.startswith(_WPS_OUI):
                return True
    return False


def decode_frame(pkt: Any) -> DecodedFrame | None:
    """Decodifica una trama scapy en un :class:`DecodedFrame` o ``None``."""
    try:
        Dot11, Dot11Beacon, Dot11Deauth, Dot11Elt, Dot11ProbeReq, EAPOL = _layers()
    except ImportError:
        return None

    if not pkt.haslayer(Dot11):
        return None

    dot11 = pkt[Dot11]
    source = normalize_bssid(getattr(dot11, "addr2", ""))
    bssid = normalize_bssid(getattr(dot11, "addr3", "") or getattr(dot11, "addr1", ""))
    rssi = _rssi(pkt)

    if pkt.haslayer(Dot11Deauth):
        reason = int(getattr(pkt[Dot11Deauth], "reason", 0) or 0)
        return DecodedFrame(
            kind=KIND_DEAUTH,
            bssid=bssid,
            source_mac=source,
            rssi=rssi,
            summary=f"Deauth desde {source or '?'} hacia {bssid or 'broadcast'} (reason {reason})",
            detail=f"reason={reason}",
        )

    if pkt.haslayer(Dot11ProbeReq):
        elements = _iter_elts(pkt, Dot11Elt)
        ssid = _ssid_from_elements(elements)
        target = ssid or "*"
        return DecodedFrame(
            kind=KIND_PROBE,
            bssid="",
            ssid=ssid,
            source_mac=source,
            rssi=rssi,
            summary=f"Probe request de {source or '?'} buscando '{target}'",
            detail=f"ssid={ssid}",
        )

    if pkt.haslayer(Dot11Beacon):
        elements = _iter_elts(pkt, Dot11Elt)
        ssid = _ssid_from_elements(elements)
        channel = _channel_from_elements(elements)
        wps = is_wps(elements)
        return DecodedFrame(
            kind=KIND_BEACON,
            bssid=bssid,
            ssid=ssid,
            source_mac=source,
            channel=channel,
            rssi=rssi,
            summary=f"Beacon de '{ssid or '<oculta>'}' ({bssid}) CH {channel}",
            detail=f"wps={'1' if wps else '0'}",
        )

    if pkt.haslayer(EAPOL):
        return DecodedFrame(
            kind=KIND_EAPOL,
            bssid=bssid,
            source_mac=source,
            rssi=rssi,
            summary=f"Trama EAPOL entre {source or '?'} y {bssid or '?'}",
            detail="handshake",
        )

    return None
