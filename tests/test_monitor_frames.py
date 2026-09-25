from __future__ import annotations

import pytest

pytest.importorskip("scapy")

from scapy.layers.dot11 import (  # noqa: E402
    Dot11,
    Dot11Beacon,
    Dot11Deauth,
    Dot11Elt,
    Dot11ProbeReq,
)

from aethernet.core.monitor.frames import (  # noqa: E402
    KIND_BEACON,
    KIND_DEAUTH,
    KIND_PROBE,
    decode_frame,
    is_wps,
)

BSSID = "aa:bb:cc:00:00:01"
SRC = "00:11:22:33:44:55"


def _deauth():
    return Dot11(type=0, subtype=12, addr1="ff:ff:ff:ff:ff:ff", addr2=SRC, addr3=BSSID) / Dot11Deauth(reason=7)


def _probe(ssid=b"MiRed"):
    return (
        Dot11(type=0, subtype=4, addr1="ff:ff:ff:ff:ff:ff", addr2=SRC, addr3="ff:ff:ff:ff:ff:ff")
        / Dot11ProbeReq()
        / Dot11Elt(ID=0, info=ssid)
    )


def _beacon(wps: bool):
    packet = (
        Dot11(type=0, subtype=8, addr1="ff:ff:ff:ff:ff:ff", addr2=BSSID, addr3=BSSID)
        / Dot11Beacon()
        / Dot11Elt(ID=0, info=b"Vecino")
        / Dot11Elt(ID=3, info=b"\x06")
    )
    if wps:
        packet = packet / Dot11Elt(ID=221, info=b"\x00\x50\xf2\x04\x01")
    return packet


def test_decode_deauth():
    frame = decode_frame(_deauth())
    assert frame is not None
    assert frame.kind == KIND_DEAUTH
    assert frame.bssid == "AA:BB:CC:00:00:01"
    assert frame.source_mac == "00:11:22:33:44:55"


def test_decode_probe():
    frame = decode_frame(_probe())
    assert frame is not None
    assert frame.kind == KIND_PROBE
    assert frame.ssid == "MiRed"
    assert frame.source_mac == "00:11:22:33:44:55"


def test_decode_beacon_channel_and_ssid():
    frame = decode_frame(_beacon(wps=False))
    assert frame is not None
    assert frame.kind == KIND_BEACON
    assert frame.ssid == "Vecino"
    assert frame.channel == 6


def test_is_wps_detects_oui():
    elements = [Dot11Elt(ID=221, info=b"\x00\x50\xf2\x04\x01")]
    assert is_wps(elements) is True
    assert is_wps([Dot11Elt(ID=221, info=b"\x00\x50\xf2\x05\x01")]) is False


def test_non_dot11_returns_none():
    from scapy.layers.l2 import Ether

    assert decode_frame(Ether() / b"data") is None
