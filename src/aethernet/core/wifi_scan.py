"""Escaneo WiFi vía ``nmcli`` y ``iw``, con parseo robusto y testeable.

Los parsers son funciones puras: reciben la salida cruda y devuelven modelos.
Así se testean sin adaptador y sin permisos. ``scan_wifi`` es solo el pegamento
que llama a los binarios y aplica los parsers.
"""

from __future__ import annotations

import re
import time
from typing import Any

from ..logging_setup import get_logger
from ..models import AccessPoint, WifiScan, canonical_security, normalize_bssid
from ..utils import run_command, signal_to_quality
from .adapter import list_wireless_interfaces, probe_adapter
from .oui import vendor_for

log = get_logger(__name__)

_NMCLI_FIELDS = "IN-USE,SSID,BSSID,CHAN,FREQ,SIGNAL,RATE,SECURITY"

_HIDDEN_SSIDS = {"", "--", "<hidden>"}


# --------------------------------------------------------------------------- #
# nmcli
# --------------------------------------------------------------------------- #
def split_nmcli_terse(line: str) -> list[str]:
    """Divide una línea ``nmcli -t`` respetando los escapes ``\\:`` y ``\\\\``."""
    fields: list[str] = []
    current: list[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            nxt = line[i + 1]
            if nxt in {":", "\\"}:
                current.append(nxt)
                i += 2
                continue
            current.append(ch)
            i += 1
            continue
        if ch == ":":
            fields.append("".join(current))
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    fields.append("".join(current))
    return fields


def _parse_freq(value: str) -> int:
    match = re.search(r"(\d{3,4})", value)
    return int(match.group(1)) if match else 0


def _parse_rate(value: str) -> float | None:
    match = re.search(r"([\d.]+)", value)
    return float(match.group(1)) if match else None


def parse_nmcli_wifi(output: str, timestamp: float | None = None, interface: str = "") -> list[AccessPoint]:
    """Parsea la salida de ``nmcli -t -f ... dev wifi list``."""
    ts = timestamp if timestamp is not None else time.time()
    aps: list[AccessPoint] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = split_nmcli_terse(line)
        if len(fields) < 7:
            continue
        in_use, ssid, bssid, chan, freq, signal, rate = fields[:7]
        security = fields[7] if len(fields) > 7 else ""
        bssid = normalize_bssid(bssid)
        if not bssid:
            continue
        hidden = ssid.strip() in _HIDDEN_SSIDS
        try:
            channel = int(chan)
        except ValueError:
            channel = 0
        try:
            dbm = int(signal) if signal.startswith("-") else int(signal) - 100
        except ValueError:
            dbm = 0
        aps.append(
            AccessPoint(
                ssid="" if hidden else ssid.strip(),
                bssid=bssid,
                signal_dbm=dbm,
                channel=channel,
                frequency_mhz=_parse_freq(freq),
                security=canonical_security(security),
                quality=signal_to_quality(dbm),
                max_rate=_parse_rate(rate),
                vendor=vendor_for(bssid),
                hidden=hidden,
                first_seen=ts,
                last_seen=ts,
                tags=("connected",) if in_use.strip() == "*" else (),
            )
        )
    return _dedupe(aps)


# --------------------------------------------------------------------------- #
# iw
# --------------------------------------------------------------------------- #
_FREQ_LINE = re.compile(r"freq:\s*(\d+)")
_SIGNAL_LINE = re.compile(r"signal:\s*(-?[\d.]+)\s*dBm")
_SSID_LINE = re.compile(r"SSID:\s*(.*)")
_DS_CHANNEL = re.compile(r"channel\s+(\d+)")
_BSS_LINE = re.compile(r"^BSS\s+([0-9a-fA-F:]{17})")
PRIMARY_CHANNEL = re.compile(r"primary channel:\s*(\d+)")


def parse_iw_scan(output: str, timestamp: float | None = None) -> list[AccessPoint]:
    """Parsea la salida de ``iw dev <if> scan``."""
    ts = timestamp if timestamp is not None else time.time()
    aps: list[AccessPoint] = []
    current: dict[str, Any] | None = None

    def flush() -> None:
        if not current:
            return
        bssid = normalize_bssid(str(current.get("bssid") or ""))
        if bssid:
            ssid_raw = str(current.get("ssid") or "")
            hidden = ssid_raw.strip() in _HIDDEN_SSIDS
            dbm = int(current.get("signal", 0))
            channel = int(current.get("channel") or 0)
            aps.append(
                AccessPoint(
                    ssid="" if hidden else ssid_raw.strip(),
                    bssid=bssid,
                    signal_dbm=dbm,
                    channel=channel,
                    frequency_mhz=int(current.get("freq") or 0),
                    security=_iw_security(current),
                    quality=signal_to_quality(dbm),
                    vendor=vendor_for(bssid),
                    hidden=hidden,
                    wps=bool(current.get("wps")),
                    first_seen=ts,
                    last_seen=ts,
                )
            )

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        bss_match = _BSS_LINE.match(line)
        if bss_match:
            flush()
            current = {"bssid": bss_match.group(1)}
            continue
        if current is None:
            continue
        stripped = line.strip()
        if freq_match := _FREQ_LINE.search(stripped):
            current["freq"] = int(freq_match.group(1))
            current["channel"] = channel_from_frequency(int(freq_match.group(1)))
        if signal_match := _SIGNAL_LINE.search(stripped):
            current["signal"] = int(float(signal_match.group(1)))
        if ssid_match := _SSID_LINE.search(stripped):
            current["ssid"] = ssid_match.group(1)
        if stripped.startswith(("RSN:", "WPA:", "WEP:")):
            key = stripped.split(":", 1)[0].lower()
            current.setdefault("security_tokens", []).append(key)
        if "SAE" in stripped:
            current["sae"] = True
        if stripped.startswith("WPS:"):
            current["wps"] = True
        if "Privacy" in stripped and "capability" in stripped:
            current["privacy"] = True
        if "channel" in stripped:
            ds_match = _DS_CHANNEL.search(stripped)
            if ds_match:
                current["channel"] = int(ds_match.group(1))
            primary = PRIMARY_CHANNEL.search(stripped)
            if primary:
                current["channel"] = int(primary.group(1))
    flush()
    return _dedupe(aps)


def channel_from_frequency(freq: int) -> int:
    """Frecuencia (MHz) → número de canal 2.4/5 GHz (aproximado)."""
    if 2412 <= freq <= 2472:
        return (freq - 2407) // 5
    if freq == 2484:
        return 14
    if 5000 <= freq <= 5895:
        return (freq - 5000) // 5
    return 0


def _iw_security(current: dict[str, Any]) -> str:
    tokens = current.get("security_tokens") or []
    if current.get("sae"):
        return "wpa3"
    if "rsn" in tokens:
        return "wpa3" if current.get("sae") else "wpa2"
    if "wpa" in tokens:
        return "wpa"
    if "wep" in tokens or current.get("privacy"):
        return "wep"
    return "open"


# --------------------------------------------------------------------------- #
# Orquestación
# --------------------------------------------------------------------------- #
def _dedupe(aps: list[AccessPoint]) -> list[AccessPoint]:
    """Un AP por BSSID, conservando la mejor señal y fusionando etiquetas."""
    best: dict[str, AccessPoint] = {}
    for ap in aps:
        prev = best.get(ap.bssid)
        if prev is None or ap.signal_dbm > prev.signal_dbm:
            if prev is not None and prev.tags:
                ap = _with_tags(ap, prev.tags)
            best[ap.bssid] = ap
        elif prev is not None and ap.tags:
            best[ap.bssid] = _with_tags(prev, ap.tags)
    return sorted(best.values(), key=lambda a: (-a.signal_dbm, a.ssid.lower()))


def _with_tags(ap: AccessPoint, extra: tuple[str, ...]) -> AccessPoint:
    merged = tuple(dict.fromkeys((*ap.tags, *extra)))
    return AccessPoint(
        ssid=ap.ssid,
        bssid=ap.bssid,
        signal_dbm=ap.signal_dbm,
        channel=ap.channel,
        frequency_mhz=ap.frequency_mhz,
        security=ap.security,
        quality=ap.quality,
        max_rate=ap.max_rate,
        width_mhz=ap.width_mhz,
        vendor=ap.vendor,
        hidden=ap.hidden,
        wps=ap.wps,
        first_seen=ap.first_seen,
        last_seen=ap.last_seen,
        tags=merged,
    )


def scan_wifi(
    interface: str | None = None,
    *,
    active: bool = False,
    timeout: float = 25.0,
    enrich_with_iw: bool = False,
) -> WifiScan:
    """Realiza un escaneo y devuelve un :class:`WifiScan`.

    ``active=False`` (por defecto) pide a nmcli los resultados en caché sin
    forzar un barrido de radio: modo pasivo y discreto.
    """
    ts = time.time()
    iface = interface or (list_wireless_interfaces() or [""])[0]
    adapter = probe_adapter(iface) if iface else None

    argv = [
        "nmcli",
        "-t",
        "-e",
        "yes",
        "-f",
        _NMCLI_FIELDS,
        "dev",
        "wifi",
        "list",
        "--rescan",
        "yes" if active else "no",
    ]
    result = run_command(argv, timeout=timeout)
    aps: list[AccessPoint] = []
    if result.ok and result.stdout.strip():
        aps = parse_nmcli_wifi(result.stdout, ts, iface)
    elif iface:
        iw_result = run_command(["iw", "dev", iface, "scan"], timeout=timeout)
        if iw_result.ok:
            aps = parse_iw_scan(iw_result.stdout, ts)
        else:
            log.warning("nmcli e iw fallaron al escanear: %s", iw_result.stderr.strip())

    if enrich_with_iw and iface and aps:
        iw_result = run_command(["iw", "dev", iface, "scan"], timeout=timeout)
        if iw_result.ok:
            aps = _merge_enrichment(aps, parse_iw_scan(iw_result.stdout, ts))

    return WifiScan(timestamp=ts, interface=iface, aps=tuple(aps), adapter=adapter, source="nmcli")


def _merge_enrichment(base: list[AccessPoint], rich: list[AccessPoint]) -> list[AccessPoint]:
    rich_by_bssid = {ap.bssid: ap for ap in rich}
    merged: list[AccessPoint] = []
    for ap in base:
        other = rich_by_bssid.get(ap.bssid)
        if other is None:
            merged.append(ap)
            continue
        merged.append(
            AccessPoint(
                ssid=other.ssid or ap.ssid,
                bssid=ap.bssid,
                signal_dbm=other.signal_dbm,
                channel=other.channel or ap.channel,
                frequency_mhz=other.frequency_mhz or ap.frequency_mhz,
                security=other.security if other.security != "open" else ap.security,
                quality=other.quality,
                max_rate=ap.max_rate,
                width_mhz=other.width_mhz or ap.width_mhz,
                vendor=other.vendor or ap.vendor,
                hidden=other.hidden,
                wps=other.wps,
                first_seen=ap.first_seen,
                last_seen=ap.last_seen,
                tags=ap.tags,
            )
        )
    known = {ap.bssid for ap in base}
    merged.extend(ap for ap in rich if ap.bssid not in known)
    return sorted(merged, key=lambda a: (-a.signal_dbm, a.ssid.lower()))


def scan_from_nmcli_output(output: str, interface: str = "") -> WifiScan:
    """Construye un escaneo desde salida ya capturada (también para importar)."""
    ts = time.time()
    return WifiScan(
        timestamp=ts,
        interface=interface,
        aps=tuple(parse_nmcli_wifi(output, ts, interface)),
        adapter=probe_adapter(interface) if interface else None,
        source="import",
    )
