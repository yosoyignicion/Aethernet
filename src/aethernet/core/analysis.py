"""Motor de reglas: convierte observaciones en hallazgos con severidad.

Cada regla es una clase pequeña e independiente que recibe un contexto y
devuelve hallazgos. Añadir una regla no toca las demás. Todas las reglas son
puras: dependen solo del contexto, así que se testean sin red ni GUI.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..models import AccessPoint, Finding, LanScan, Severity, WifiScan
from .text import similar_ssid


# --------------------------------------------------------------------------- #
# Contexto y eventos de modo monitor
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class MonitorEvent:
    """Evento capturado en modo monitor (deauth, probe request, beacon flood)."""

    kind: str
    timestamp: float
    bssid: str = ""
    ssid: str = ""
    source_mac: str = ""
    channel: int = 0
    rssi: int = 0
    count: int = 1
    detail: str = ""


@dataclass(slots=True)
class AnalysisContext:
    scan: WifiScan
    previous: WifiScan | None = None
    lan_scan: LanScan | None = None
    previous_lan: LanScan | None = None
    my_ssids: tuple[str, ...] = ()
    my_bssids: tuple[str, ...] = ()
    known_bssids: set[str] = field(default_factory=set)
    known_lan_macs: set[str] = field(default_factory=set)
    trusted_macs: set[str] = field(default_factory=set)
    signal_history: dict[str, list[int]] = field(default_factory=dict)
    monitor_events: list[MonitorEvent] = field(default_factory=list)
    watchlist: dict[str, dict[str, Any]] = field(default_factory=dict)
    disabled_rules: set[str] = field(default_factory=set)
    now: float = field(default_factory=time.time)

    def legit_bssids(self) -> set[str]:
        """BSSIDs que consideramos de nuestra red."""
        legit = {b.upper() for b in self.my_bssids}
        wanted = {s.lower() for s in self.my_ssids}
        for ap in self.scan.aps:
            if "connected" in ap.tags and (not wanted or ap.ssid.lower() in wanted):
                legit.add(ap.bssid)
        return legit

    def is_mine(self, ap: AccessPoint) -> bool:
        if ap.bssid in {b.upper() for b in self.my_bssids}:
            return True
        if self.my_ssids and ap.ssid.lower() in {s.lower() for s in self.my_ssids}:
            return True
        return "connected" in ap.tags


@runtime_checkable
class Rule(Protocol):
    rule_id: str
    severity: Severity

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]: ...


def _finding(
    rule_id: str,
    severity: Severity,
    title: str,
    description: str,
    *,
    suggestion: str = "",
    subject: str = "",
    subject_type: str = "bssid",
    evidence: dict[str, Any] | None = None,
    timestamp: float | None = None,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=severity,
        title=title,
        description=description,
        suggestion=suggestion,
        subject=subject,
        subject_type=subject_type,
        evidence=evidence or {},
        timestamp=timestamp if timestamp is not None else time.time(),
    )


# --------------------------------------------------------------------------- #
# Reglas WiFi
# --------------------------------------------------------------------------- #
class EvilTwinRule:
    rule_id = "evil_twin"
    severity = Severity.CRITICAL

    def evaluate(self, ctx: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        legit = ctx.legit_bssids()
        if not ctx.my_ssids or not legit:
            return findings
        wanted = {s.lower(): s for s in ctx.my_ssids}
        for ap in ctx.scan.aps:
            reference = wanted.get(ap.ssid.lower())
            if reference is None or ap.bssid in legit:
                continue
            findings.append(
                _finding(
                    self.rule_id,
                    Severity.CRITICAL,
                    f"Posible gemelo malvado de '{ap.ssid}'",
                    (
                        f"Se anuncia tu SSID '{ap.ssid}' desde un BSSID que no es el tuyo "
                        f"({ap.bssid}). Podría ser un punto de acceso falso."
                    ),
                    suggestion=(
                        "No te conectes a esa red. Compara el BSSID con el de tu router y, "
                        "si persiste, cambia la contraseña del WiFi."
                    ),
                    subject=ap.bssid,
                    evidence={
                        "bssid": ap.bssid,
                        "ssid": ap.ssid,
                        "legit_bssids": sorted(legit),
                        "signal_dbm": ap.signal_dbm,
                        "channel": ap.channel,
                        "vendor": ap.vendor,
                    },
                    timestamp=ctx.now,
                )
            )
        return findings


class BssidSsidMismatchRule:
    rule_id = "bssid_ssid_mismatch"
    severity = Severity.ALERT

    def evaluate(self, ctx: AnalysisContext) -> list[Finding]:
        mine = {b.upper() for b in ctx.my_bssids}
        if not mine:
            return []
        wanted = {s.lower() for s in ctx.my_ssids}
        findings: list[Finding] = []
        for ap in ctx.scan.aps:
            if ap.bssid not in mine:
                continue
            if wanted and ap.ssid.lower() not in wanted:
                findings.append(
                    _finding(
                        self.rule_id,
                        Severity.ALERT,
                        "Tu router anuncia un SSID distinto",
                        f"El BSSID {ap.bssid} (tu router) ahora anuncia '{ap.display_ssid}'.",
                        suggestion="¿Cambiaste el nombre de la red? Si no, revisa tu router.",
                        subject=ap.bssid,
                        evidence={"bssid": ap.bssid, "ssid": ap.ssid, "expected": sorted(wanted)},
                        timestamp=ctx.now,
                    )
                )
        return findings


class SimilarSsidRule:
    rule_id = "similar_ssid"
    severity = Severity.ALERT

    def evaluate(self, ctx: AnalysisContext) -> list[Finding]:
        if not ctx.my_ssids:
            return []
        findings: list[Finding] = []
        seen: set[tuple[str, str]] = set()
        for ap in ctx.scan.aps:
            if ctx.is_mine(ap) or not ap.ssid:
                continue
            for reference in ctx.my_ssids:
                looks_similar, distance = similar_ssid(ap.ssid, reference)
                key = (ap.bssid, reference)
                if looks_similar and key not in seen:
                    seen.add(key)
                    findings.append(
                        _finding(
                            self.rule_id,
                            Severity.ALERT,
                            f"SSID sospechosamente parecido a '{reference}'",
                            f"'{ap.ssid}' se parece a tu red (distancia {distance}).",
                            suggestion="Comprueba que no sea un intento de suplantación.",
                            subject=ap.bssid,
                            evidence={
                                "candidate": ap.ssid,
                                "reference": reference,
                                "distance": distance,
                                "bssid": ap.bssid,
                            },
                            timestamp=ctx.now,
                        )
                    )
        return findings


class NewStrongApRule:
    rule_id = "new_strong_ap"
    severity = Severity.WARNING

    def evaluate(self, ctx: AnalysisContext) -> list[Finding]:
        if not ctx.known_bssids:
            return []  # primer escaneo: todo es "nuevo", no aporta
        findings: list[Finding] = []
        for ap in ctx.scan.aps:
            if ap.bssid in ctx.known_bssids or ctx.is_mine(ap):
                continue
            if ap.signal_dbm >= -62:
                findings.append(
                    _finding(
                        self.rule_id,
                        Severity.WARNING,
                        f"AP nuevo con señal fuerte: {ap.display_ssid}",
                        (
                            f"'{ap.display_ssid}' ({ap.bssid}) no se había visto antes y llega a "
                            f"{ap.signal_dbm} dBm en el canal {ap.channel}."
                        ),
                        suggestion="Puede ser un vecino nuevo o un dispositivo recién instalado.",
                        subject=ap.bssid,
                        evidence={
                            "bssid": ap.bssid,
                            "ssid": ap.ssid,
                            "signal_dbm": ap.signal_dbm,
                            "channel": ap.channel,
                            "vendor": ap.vendor,
                        },
                        timestamp=ctx.now,
                    )
                )
        return findings


class ChannelChangeRule:
    rule_id = "my_channel_change"
    severity = Severity.WARNING

    def evaluate(self, ctx: AnalysisContext) -> list[Finding]:
        if ctx.previous is None:
            return []
        legit = ctx.legit_bssids()
        prev = ctx.previous.by_bssid()
        findings: list[Finding] = []
        for ap in ctx.scan.aps:
            if ap.bssid not in legit or ap.bssid not in prev:
                continue
            old = prev[ap.bssid]
            if old.channel and ap.channel and old.channel != ap.channel:
                findings.append(
                    _finding(
                        self.rule_id,
                        Severity.WARNING,
                        "Tu router cambió de canal",
                        f"Pasó del canal {old.channel} al {ap.channel}.",
                        suggestion=(
                            "Si no lo cambiaste tú, revisa el 'auto' del router o "
                            "comprueba si alguien accedió a su configuración."
                        ),
                        subject=ap.bssid,
                        evidence={"from": old.channel, "to": ap.channel, "bssid": ap.bssid},
                        timestamp=ctx.now,
                    )
                )
        return findings


class SignalDropRule:
    rule_id = "signal_drop"
    severity = Severity.ALERT

    def evaluate(self, ctx: AnalysisContext) -> list[Finding]:
        legit = ctx.legit_bssids()
        if not legit:
            return []
        findings: list[Finding] = []
        for ap in ctx.scan.aps:
            if ap.bssid not in legit:
                continue
            history = ctx.signal_history.get(ap.bssid, [])
            if len(history) < 3:
                continue
            baseline = statistics.median(history[-10:])
            if baseline - ap.signal_dbm >= 15:
                findings.append(
                    _finding(
                        self.rule_id,
                        Severity.ALERT,
                        "Caída brusca de señal en tu red",
                        (
                            f"La señal de {ap.display_ssid} bajó de {baseline:.0f} a "
                            f"{ap.signal_dbm} dBm."
                        ),
                        suggestion="Comprueba obstáculos, interferencias o interferencia de otro equipo.",
                        subject=ap.bssid,
                        evidence={"baseline_dbm": baseline, "current_dbm": ap.signal_dbm},
                        timestamp=ctx.now,
                    )
                )
        return findings


class NewOpenNetworkRule:
    rule_id = "new_open_network"
    severity = Severity.WARNING

    def evaluate(self, ctx: AnalysisContext) -> list[Finding]:
        if not ctx.known_bssids:
            return []
        findings: list[Finding] = []
        for ap in ctx.scan.aps:
            if ap.is_open and ap.bssid not in ctx.known_bssids and not ap.hidden:
                findings.append(
                    _finding(
                        self.rule_id,
                        Severity.WARNING,
                        f"Red abierta nueva: {ap.display_ssid}",
                        "Apareció una red sin cifrado que no habías visto antes.",
                        suggestion="Evita conectarte: el tráfico viaja sin cifrar.",
                        subject=ap.bssid,
                        evidence={"bssid": ap.bssid, "ssid": ap.ssid, "signal_dbm": ap.signal_dbm},
                        timestamp=ctx.now,
                    )
                )
        return findings


class WpsDetectionRule:
    rule_id = "wps_enabled"
    severity = Severity.WARNING

    def evaluate(self, ctx: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        for ap in ctx.scan.aps:
            if not ap.wps:
                continue
            mine = ctx.is_mine(ap)
            findings.append(
                _finding(
                    self.rule_id,
                    Severity.WARNING if mine else Severity.INFO,
                    ("WPS activo en tu red" if mine else f"WPS activo en {ap.display_ssid}"),
                    "WPS permite emparejar con un PIN que puede ser vulnerable a fuerza bruta.",
                    suggestion=(
                        "Desactiva WPS en tu router si no lo usas."
                        if mine
                        else "Red ajena con WPS: solo informativo."
                    ),
                    subject=ap.bssid,
                    evidence={"bssid": ap.bssid, "ssid": ap.ssid, "mine": mine},
                    timestamp=ctx.now,
                )
            )
        return findings


class DeauthFloodRule:
    rule_id = "deauth_flood"
    severity = Severity.CRITICAL

    def evaluate(self, ctx: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        legit = ctx.legit_bssids()
        for event in ctx.monitor_events:
            if event.kind != "deauth":
                continue
            if legit and event.bssid and event.bssid not in legit:
                continue
            if event.count >= 20:
                findings.append(
                    _finding(
                        self.rule_id,
                        Severity.CRITICAL,
                        "Posible deauth flood contra tu red",
                        f"Se detectaron {event.count} tramas de desautenticación.",
                        suggestion=(
                            "Alguien puede estar expulsando clientes de tu red. "
                            "Considera WPA3 o revisa dispositivos cercanos."
                        ),
                        subject=event.bssid or "broadcast",
                        evidence={
                            "count": event.count,
                            "source_mac": event.source_mac,
                            "bssid": event.bssid,
                        },
                        timestamp=event.timestamp,
                    )
                )
        return findings


class ProbeRequestRule:
    rule_id = "probe_request"
    severity = Severity.INFO

    def evaluate(self, ctx: AnalysisContext) -> list[Finding]:
        if not ctx.my_ssids:
            return []
        wanted = {s.lower() for s in ctx.my_ssids}
        findings: list[Finding] = []
        for event in ctx.monitor_events:
            if event.kind != "probe" or event.ssid.lower() not in wanted:
                continue
            findings.append(
                _finding(
                    self.rule_id,
                    Severity.INFO,
                    "Un dispositivo busca tu red",
                    (
                        f"{event.source_mac or 'Un dispositivo'} emitió un probe request "
                        f"buscando '{event.ssid}'."
                    ),
                    suggestion="Normal si es un dispositivo tuyo; si no lo reconoces, anótalo.",
                    subject=event.source_mac or event.ssid,
                    subject_type="mac",
                    evidence={"source_mac": event.source_mac, "ssid": event.ssid, "count": event.count},
                    timestamp=event.timestamp,
                )
            )
        return findings


class NewLanDeviceRule:
    rule_id = "new_lan_device"
    severity = Severity.WARNING

    def evaluate(self, ctx: AnalysisContext) -> list[Finding]:
        if ctx.lan_scan is None:
            return []
        first_lan_scan = not ctx.known_lan_macs
        findings: list[Finding] = []
        for device in ctx.lan_scan.devices:
            if device.is_gateway or device.mac in ctx.known_lan_macs:
                continue
            known_trusted = device.trusted or device.mac in ctx.trusted_macs
            severity = Severity.INFO if (known_trusted or first_lan_scan) else Severity.WARNING
            findings.append(
                _finding(
                    self.rule_id,
                    severity,
                    f"Dispositivo {'conocido' if known_trusted else 'nuevo'} en tu red: {device.display_name}",
                    f"{device.ip} · {device.mac}" + (f" · {device.vendor}" if device.vendor else ""),
                    suggestion=(
                        "Márcalo como confiable con un nombre si lo reconoces."
                        if not known_trusted
                        else "Ya está marcado como confiable."
                    ),
                    subject=device.mac,
                    subject_type="mac",
                    evidence={
                        "mac": device.mac,
                        "ip": device.ip,
                        "hostname": device.hostname,
                        "vendor": device.vendor,
                        "randomized_mac": device.is_randomized_mac,
                    },
                    timestamp=ctx.now,
                )
            )
        return findings


class WatchlistChangeRule:
    rule_id = "watchlist_change"
    severity = Severity.WARNING

    def evaluate(self, ctx: AnalysisContext) -> list[Finding]:
        if not ctx.watchlist:
            return []
        current = ctx.scan.by_bssid()
        previous = ctx.previous.by_bssid() if ctx.previous else {}
        findings: list[Finding] = []
        for bssid, meta in ctx.watchlist.items():
            ap = current.get(bssid)
            ssid = str(meta.get("ssid") or "")
            if ap is None:
                if bssid in previous:
                    findings.append(
                        _finding(
                            self.rule_id,
                            Severity.WARNING,
                            f"Red vigilada desapareció: {ssid or bssid}",
                            "El BSSID que estabas vigilando ya no está visible.",
                            suggestion="Puede haberse apagado, movido o cambiado de BSSID.",
                            subject=bssid,
                            evidence={"bssid": bssid, "ssid": ssid},
                            timestamp=ctx.now,
                        )
                    )
                continue
            expected_channel = meta.get("expected_channel")
            expected_security = meta.get("expected_security")
            if expected_channel and ap.channel and int(ap.channel) != int(expected_channel):
                findings.append(
                    _finding(
                        self.rule_id,
                        Severity.WARNING,
                        f"Red vigilada cambió de canal: {ssid or bssid}",
                        f"Pasó de CH{int(expected_channel):02d} a CH{ap.channel:02d}.",
                        suggestion="Si no lo cambiaste tú, revisa el router.",
                        subject=bssid,
                        evidence={"bssid": bssid, "from": expected_channel, "to": ap.channel},
                        timestamp=ctx.now,
                    )
                )
            if expected_security and ap.security != expected_security:
                findings.append(
                    _finding(
                        self.rule_id,
                        Severity.ALERT,
                        f"Red vigilada cambió de seguridad: {ssid or bssid}",
                        f"Pasó de {expected_security} a {ap.security}.",
                        suggestion="Un cambio a 'open'/'wep' es mala señal.",
                        subject=bssid,
                        evidence={"bssid": bssid, "from": expected_security, "to": ap.security},
                        timestamp=ctx.now,
                    )
                )
        return findings


class CongestionRule:
    rule_id = "channel_congestion"
    severity = Severity.WARNING
    neighbors_warning = 4
    neighbors_alert = 7

    def evaluate(self, ctx: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        targets = [ap for ap in ctx.scan.aps if ctx.is_mine(ap)] or _strongest(ctx)
        for ap in targets:
            if not ap.channel:
                continue
            neighbors = [other for other in ctx.scan.aps if other.bssid != ap.bssid and _overlaps(ap, other)]
            count = len(neighbors)
            if count < self.neighbors_warning:
                continue
            severity = Severity.ALERT if count >= self.neighbors_alert else Severity.WARNING
            findings.append(
                _finding(
                    self.rule_id,
                    severity,
                    f"Canal {ap.channel} saturado: {count} vecinos compiten contigo",
                    (
                        f"Tu red en el canal {ap.channel} comparte espectro con {count} "
                        "redes cercanas."
                    ),
                    suggestion=(
                        "Cámbiate a un canal menos ocupado (1, 6 u 11 en 2.4 GHz; DFS o "
                        "36-48 en 5 GHz)."
                    ),
                    subject=ap.bssid,
                    evidence={
                        "channel": ap.channel,
                        "neighbors": count,
                        "neighbor_bssids": [n.bssid for n in neighbors][:20],
                    },
                    timestamp=ctx.now,
                )
            )
        return findings


def _strongest(ctx: AnalysisContext, n: int = 1) -> list[AccessPoint]:
    return sorted(ctx.scan.aps, key=lambda a: a.signal_dbm, reverse=True)[:n]


def _overlaps(a: AccessPoint, b: AccessPoint) -> bool:
    """Solapamiento por canal. En 2.4 GHz cualquier canal a ±4 interfiere."""
    if not a.channel or not b.channel:
        return False
    if a.frequency_mhz and b.frequency_mhz:
        return abs(a.frequency_mhz - b.frequency_mhz) < 20
    if a.channel <= 14 and b.channel <= 14:
        return abs(a.channel - b.channel) <= 4
    return a.channel == b.channel


# --------------------------------------------------------------------------- #
# Registro y ejecución
# --------------------------------------------------------------------------- #
DEFAULT_RULES: tuple[type, ...] = (
    EvilTwinRule,
    BssidSsidMismatchRule,
    SimilarSsidRule,
    NewStrongApRule,
    ChannelChangeRule,
    SignalDropRule,
    NewOpenNetworkRule,
    WpsDetectionRule,
    DeauthFloodRule,
    ProbeRequestRule,
    NewLanDeviceRule,
    WatchlistChangeRule,
    CongestionRule,
)


def run_rules(ctx: AnalysisContext) -> list[Finding]:
    """Ejecuta todas las reglas habilitadas y devuelve hallazgos ordenados."""
    findings: list[Finding] = []
    for rule_cls in DEFAULT_RULES:
        rule = rule_cls()
        if rule.rule_id in ctx.disabled_rules:
            continue
        try:
            findings.extend(rule.evaluate(ctx))
        except Exception as exc:  # una regla rota nunca tumba el escaneo
            from ..logging_setup import get_logger

            get_logger(__name__).exception("regla %s falló: %s", rule.rule_id, exc)
    return sorted(findings, key=lambda f: (-f.severity.rank, f.rule_id))
