"""Modelos de dominio inmutables y serializables.

Regla de oro: estos objetos no saben de SQLite, ni de nmcli, ni de Tkinter.
Son datos con tipo, comparables y fáciles de testear.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, cast


# --------------------------------------------------------------------------- #
# Enumeraciones con orden semántico
# --------------------------------------------------------------------------- #
class Severity(StrEnum):
    """Severidad de un hallazgo o evento."""

    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {
            Severity.INFO: 0,
            Severity.WARNING: 1,
            Severity.ALERT: 2,
            Severity.CRITICAL: 3,
        }[self]

    def at_least(self, other: Severity) -> bool:
        return self.rank >= other.rank


class Band(StrEnum):
    """Banda de frecuencia."""

    GHZ_24 = "2.4 GHz"
    GHZ_5 = "5 GHz"
    GHZ_6 = "6 GHz"
    UNKNOWN = "unknown"

    @classmethod
    def from_frequency(cls, freq_mhz: int | None) -> Band:
        if not freq_mhz:
            return cls.UNKNOWN
        if 2400 <= freq_mhz <= 2500:
            return cls.GHZ_24
        if 4900 <= freq_mhz <= 5895:
            return cls.GHZ_5
        if 5925 <= freq_mhz <= 7125:
            return cls.GHZ_6
        return cls.UNKNOWN

    @classmethod
    def from_channel(cls, channel: int | None) -> Band:
        if channel is None:
            return cls.UNKNOWN
        if 1 <= channel <= 14:
            return cls.GHZ_24
        if 32 <= channel <= 177:
            return cls.GHZ_5
        return cls.UNKNOWN


# Ranking de seguridad: mayor es mejor. -1 = desconocido.
_SECURITY_RANK = {
    "open": 0,
    "wep": 1,
    "wpa": 2,
    "wpa2": 3,
    "wpa3": 3,
    "wpa2/wpa3": 3,
}
def canonical_security(raw: str | None) -> str:
    """Normaliza los múltiples alias que devuelven nmcli/iw."""
    if raw is None:
        return "open"
    cleaned = re.sub(r"[\s_/+\-]", "", raw.strip().lower())
    if not cleaned:
        return "open"
    if "wpa3" in cleaned or "sae" in cleaned:
        return "wpa3"
    if "wpa2" in cleaned:
        return "wpa2"
    if "wpa" in cleaned:
        return "wpa"
    if "wep" in cleaned:
        return "wep"
    if cleaned in {"none", "open"}:
        return "open"
    return cleaned


def security_rank(raw: str | None) -> int:
    return _SECURITY_RANK.get(canonical_security(raw), -1)


def normalize_bssid(raw: str | None) -> str:
    """BSSID siempre en MAYÚSCULAS separado por dos puntos.

    Acepta ``aa:bb:..``, ``aa-bb-..`` y ``aabbccddeeff``.
    """
    if not raw:
        return ""
    hexchars = re.sub(r"[^0-9a-fA-F]", "", raw)
    if len(hexchars) == 12:
        return ":".join(hexchars[i : i + 2] for i in range(0, 12, 2)).upper()
    cleaned = raw.strip().lower().replace("-", ":")
    parts = [p.zfill(2) for p in cleaned.split(":") if p]
    return ":".join(parts).upper()


def normalize_mac(raw: str | None) -> str:
    return normalize_bssid(raw)


def _as_dict(value: Any) -> dict[str, Any]:
    """Igual que :func:`_dump` pero garantiza un dict tipado."""
    return cast("dict[str, Any]", _dump(value))


def _dump(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: _dump(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {k: _dump(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_dump(v) for v in value]
    return value


# --------------------------------------------------------------------------- #
# WiFi
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class AdapterInfo:
    """Capacidades reales del adaptador. Base de la 'configuración honesta'."""

    interface: str = ""
    driver: str | None = None
    chipset: str | None = None
    phy: str | None = None
    mode: str = "managed"
    bands: tuple[Band, ...] = ()
    supports_monitor: bool = False
    supports_injection: bool = False
    supports_ap: bool = False
    supports_5ghz: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(self)


@dataclass(frozen=True, slots=True)
class AccessPoint:
    """Un punto de acceso observado en un escaneo."""

    ssid: str
    bssid: str
    signal_dbm: int
    channel: int
    frequency_mhz: int = 0
    security: str = "open"
    quality: int = 0
    max_rate: float | None = None
    width_mhz: int | None = None
    vendor: str | None = None
    hidden: bool = False
    wps: bool = False
    first_seen: float | None = None
    last_seen: float | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.bssid:
            raise ValueError("AccessPoint requiere bssid")

    @property
    def band(self) -> Band:
        if self.frequency_mhz:
            return Band.from_frequency(self.frequency_mhz)
        return Band.from_channel(self.channel)

    @property
    def is_open(self) -> bool:
        return canonical_security(self.security) == "open"

    @property
    def is_secure(self) -> bool:
        return security_rank(self.security) >= 3

    @property
    def key(self) -> str:
        return self.bssid

    @property
    def display_ssid(self) -> str:
        return self.ssid or "<oculta>"

    @property
    def is_locally_administered(self) -> bool:
        """Bit *locally administered* del primer octeto: BSSID virtual/malla."""
        try:
            return bool(int(self.bssid.split(":")[0], 16) & 0b10)
        except (ValueError, IndexError):
            return False

    def to_dict(self) -> dict[str, Any]:
        data = _as_dict(self)
        data["band"] = self.band.value
        data["is_open"] = self.is_open
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AccessPoint:
        allowed = {f.name for f in dataclasses.fields(cls)}
        clean = {k: v for k, v in data.items() if k in allowed}
        if isinstance(clean.get("tags"), list):
            clean["tags"] = tuple(clean["tags"])
        return cls(**clean)


@dataclass(frozen=True, slots=True)
class WifiScan:
    """Fotografía completa del entorno WiFi en un instante."""

    timestamp: float
    interface: str = ""
    aps: tuple[AccessPoint, ...] = ()
    adapter: AdapterInfo | None = None
    source: str = "nmcli"

    @property
    def id(self) -> str:
        return scan_digest(self.timestamp, [ap.key for ap in self.aps])

    @property
    def count(self) -> int:
        return len(self.aps)

    def by_bssid(self) -> dict[str, AccessPoint]:
        return {ap.bssid: ap for ap in self.aps}

    def by_ssid(self) -> dict[str, list[AccessPoint]]:
        out: dict[str, list[AccessPoint]] = {}
        for ap in self.aps:
            if ap.ssid:
                out.setdefault(ap.ssid, []).append(ap)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "interface": self.interface,
            "source": self.source,
            "adapter": self.adapter.to_dict() if self.adapter else None,
            "aps": [ap.to_dict() for ap in self.aps],
        }


@dataclass(frozen=True, slots=True)
class WifiObservation:
    """Observación puntual de un AP, para histórico y tendencias."""

    bssid: str
    scan_id: str
    timestamp: float
    channel: int
    signal_dbm: int
    security: str
    ssid: str = ""


# --------------------------------------------------------------------------- #
# LAN
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class LanDevice:
    mac: str
    ip: str
    hostname: str | None = None
    vendor: str | None = None
    alias: str | None = None
    trusted: bool = False
    first_seen: float | None = None
    last_seen: float | None = None
    online: bool = True
    is_gateway: bool = False

    @property
    def display_name(self) -> str:
        return self.alias or self.hostname or self.ip

    @property
    def is_randomized_mac(self) -> bool:
        """MAC localmente administrada: probable aleatorización de privacidad."""
        try:
            first = int(self.mac.split(":")[0], 16)
        except (ValueError, IndexError):
            return False
        return bool(first & 0b00000010)

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(self)


@dataclass(frozen=True, slots=True)
class LanScan:
    timestamp: float
    subnet: str = ""
    devices: tuple[LanDevice, ...] = ()
    source: str = "arp"

    @property
    def count(self) -> int:
        return len(self.devices)

    def by_mac(self) -> dict[str, LanDevice]:
        return {d.mac: d for d in self.devices}

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "subnet": self.subnet,
            "source": self.source,
            "devices": [d.to_dict() for d in self.devices],
        }


# --------------------------------------------------------------------------- #
# Anomalías y eventos
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Finding:
    """Resultado de una regla de análisis."""

    rule_id: str
    severity: Severity
    title: str
    description: str
    suggestion: str = ""
    subject: str = ""
    subject_type: str = "bssid"
    evidence: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def fingerprint(self) -> str:
        """Estable entre ejecuciones: permite deduplicar sin perder hallazgos."""
        raw = f"{self.rule_id}|{self.subject_type}|{self.subject}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        data = _as_dict(self)
        data["severity"] = self.severity.value
        data["fingerprint"] = self.fingerprint
        return data


@dataclass(slots=True)
class Event:
    """Evento persistido en la bandeja; puede o no venir de un Finding."""

    severity: Severity
    title: str
    body: str = ""
    kind: str = "general"
    fingerprint: str = ""
    created_at: float = field(default_factory=time.time)
    read: bool = False
    muted: bool = False
    event_id: int | None = None
    dedup_count: int = 1
    evidence: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = _as_dict(self)
        data["severity"] = self.severity.value
        return data


# --------------------------------------------------------------------------- #
# Salud
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class HealthFactor:
    key: str
    label: str
    score: int
    weight: float
    note: str

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(self)


@dataclass(frozen=True, slots=True)
class HealthScore:
    total: int
    grade: str
    headline: str
    factors: tuple[HealthFactor, ...] = ()
    generated_at: float = field(default_factory=time.time)

    @property
    def severity(self) -> Severity:
        if self.total >= 80:
            return Severity.INFO
        if self.total >= 60:
            return Severity.WARNING
        if self.total >= 40:
            return Severity.ALERT
        return Severity.CRITICAL

    def to_dict(self) -> dict[str, Any]:
        data = _as_dict(self)
        data["severity"] = self.severity.value
        return data

    @staticmethod
    def grade_for(total: int) -> str:
        if total >= 90:
            return "excelente"
        if total >= 80:
            return "buena"
        if total >= 60:
            return "aceptable"
        if total >= 40:
            return "degradada"
        return "crítica"


# --------------------------------------------------------------------------- #
# Snapshots
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Snapshot:
    kind: str
    created_at: float
    label: str
    digest: str
    payload: dict[str, Any] = field(default_factory=dict)
    snapshot_id: int | None = None

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.created_at)

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(self)


def scan_digest(timestamp: float, keys: list[str] | tuple[str, ...]) -> str:
    """Identificador estable de un escaneo a partir de su timestamp y claves."""
    raw = f"{int(timestamp)}|{'|'.join(sorted(keys))}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def to_json(obj: Any, *, indent: int | None = 2) -> str:
    """Serializa modelos a JSON UTF-8 legible."""
    return json.dumps(_dump(obj), ensure_ascii=False, indent=indent, default=str)
