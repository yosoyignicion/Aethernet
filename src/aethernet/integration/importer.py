"""Importa escaneos externos (JSON de WiFi Analyzer del móvil).

Sirve para cubrir bandas que tu adaptador no ve: escaneas con el móvil y
enriqueces el inventario local sin nube ni cuentas.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from ..core.oui import vendor_for
from ..core.wifi_scan import channel_from_frequency
from ..logging_setup import get_logger
from ..models import AccessPoint, WifiScan, canonical_security, normalize_bssid
from ..utils import signal_to_quality

log = get_logger(__name__)

_CAP_RE = re.compile(r"\[([^\]]+)\]")


def security_from_capabilities(capabilities: str | None) -> str:
    """Interpreta el campo capabilities de WiFi Analyzer: '[WPA2-PSK-CCMP][ESS]'."""
    if not capabilities:
        return "open"
    text = capabilities.upper()
    if "WPA3" in text or "SAE" in text:
        return "wpa3"
    if "WPA2" in text or "RSN" in text:
        return "wpa2"
    if "WPA" in text:
        return "wpa"
    if "WEP" in text:
        return "wep"
    return "open"


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("networks", "results", "accessPoints", "wifi", "aps", "data"):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
        # tal vez un único registro o un dict de ssid→datos
        values = [v for v in payload.values() if isinstance(v, dict)]
        if values and all("bssid" in v or "BSSID" in v for v in values):
            return values
    return []


def _pick(record: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
        lower = key.lower()
        for actual, value in record.items():
            if actual.lower() == lower and value not in (None, ""):
                return value
    return default


def parse_wifi_analyzer(payload: Any, timestamp: float | None = None) -> list[AccessPoint]:
    ts = timestamp if timestamp is not None else time.time()
    aps: list[AccessPoint] = []
    for record in _extract_records(payload):
        bssid = normalize_bssid(str(_pick(record, "BSSID", "bssid", "mac", "macAddress", default="")))
        if not bssid:
            continue
        ssid = str(_pick(record, "SSID", "ssid", "name", default="") or "")
        frequency = _as_int(_pick(record, "frequency", "freq", "frequencyMhz", default=0))
        channel = _as_int(_pick(record, "channel", "primaryChannel", default=0))
        if not channel and frequency:
            channel = channel_from_frequency(frequency)
        dbm = _as_int(_pick(record, "level", "signal", "rssi", "signalDbm", default=0))
        capabilities = _pick(record, "capabilities", "security", "encryption", "auth", default="")
        security = (
            security_from_capabilities(str(capabilities))
            if isinstance(capabilities, str) and capabilities
            else canonical_security(str(capabilities) if capabilities else None)
        )
        aps.append(
            AccessPoint(
                ssid=ssid,
                bssid=bssid,
                signal_dbm=dbm,
                channel=channel,
                frequency_mhz=frequency,
                security=security,
                quality=signal_to_quality(dbm),
                vendor=vendor_for(bssid),
                hidden=not ssid,
                first_seen=ts,
                last_seen=ts,
                tags=("imported",),
            )
        )
    return aps


def import_wifi_analyzer(path: Path | str, timestamp: float | None = None) -> WifiScan:
    """Lee un JSON exportado y devuelve un :class:`WifiScan` de origen externo."""
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    ts = timestamp or time.time()
    aps = parse_wifi_analyzer(payload, ts)
    return WifiScan(timestamp=ts, interface="imported", aps=tuple(aps), adapter=None, source="import")


def import_and_save(repo, path: Path | str, my_bssids: set[str] | None = None) -> int:
    scan = import_wifi_analyzer(path)
    repo.save_wifi_scan(scan, my_bssids=my_bssids or set())
    log.info("importadas %d redes desde %s", scan.count, path)
    return scan.count


def _as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0
