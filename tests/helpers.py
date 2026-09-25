"""Constructores de modelos para los tests (sin hardware)."""

from __future__ import annotations

from aethernet.models import AccessPoint, Band, LanDevice, WifiScan


def ap(
    ssid: str,
    bssid: str,
    *,
    dbm: int = -50,
    channel: int = 6,
    security: str = "wpa2",
    hidden: bool = False,
    wps: bool = False,
    tags: tuple[str, ...] = (),
    vendor: str | None = None,
) -> AccessPoint:
    if 1 <= channel <= 14:
        frequency = 2407 + channel * 5
    elif channel >= 32:
        frequency = 5000 + channel * 5
    else:
        frequency = 0
    return AccessPoint(
        ssid=ssid,
        bssid=bssid,
        signal_dbm=dbm,
        channel=channel,
        frequency_mhz=frequency,
        security=security,
        hidden=hidden,
        wps=wps,
        tags=tags,
        vendor=vendor,
    )


def scan(*aps: AccessPoint, ts: float = 1000.0) -> WifiScan:
    return WifiScan(timestamp=ts, interface="wlan0", aps=tuple(aps), source="test")


def device(mac: str, ip: str, *, trusted: bool = False, gateway: bool = False, hostname=None) -> LanDevice:
    return LanDevice(
        mac=mac,
        ip=ip,
        hostname=hostname,
        trusted=trusted,
        is_gateway=gateway,
        first_seen=1.0,
        last_seen=1.0,
    )


def band_of(channel: int) -> Band:
    return Band.from_channel(channel)
