"""Score de salud WiFi (0-100) con desglose por factor y frase corta.

Nunca dice "estás seguro": describe la salud observable y recuerda los límites
del hardware cuando no hay red propia configurada.
"""

from __future__ import annotations

import statistics
import time

from ..models import AccessPoint, HealthFactor, HealthScore, WifiScan, security_rank

_WEIGHTS = {
    "security": 0.20,
    "congestion": 0.25,
    "channel": 0.20,
    "bandwidth": 0.15,
    "stability": 0.20,
}

_SECURITY_SCORES = {4: 100, 3: 85, 2: 50, 1: 15, 0: 0, -1: 60}


def score_health(
    scan: WifiScan,
    *,
    my_ssids: tuple[str, ...] = (),
    my_bssids: tuple[str, ...] = (),
    signal_history: dict[str, list[int]] | None = None,
    now: float | None = None,
) -> HealthScore:
    generated = now if now is not None else time.time()
    if not scan.aps:
        return HealthScore(
            total=0,
            grade="sin datos",
            headline="No hay redes visibles: comprueba el adaptador y vuelve a escanear.",
            factors=(),
            generated_at=generated,
        )

    target, is_mine = _select_target(scan, my_ssids, my_bssids)
    history = (signal_history or {}).get(target.bssid, [])
    neighbors = [ap for ap in scan.aps if ap.bssid != target.bssid and _overlaps(target, ap)]

    factors = (
        _security_factor(target),
        _congestion_factor(target, neighbors),
        _channel_factor(target, len(neighbors)),
        _bandwidth_factor(target),
        _stability_factor(target, history),
    )
    total = round(sum(f.score * f.weight for f in factors))
    total = max(0, min(100, total))
    headline = _headline(total, is_mine, my_ssids)
    return HealthScore(
        total=total,
        grade=HealthScore.grade_for(total),
        headline=headline,
        factors=factors,
        generated_at=generated,
    )


def _select_target(scan: WifiScan, my_ssids: tuple[str, ...], my_bssids: tuple[str, ...]) -> tuple[AccessPoint, bool]:
    if my_bssids:
        wanted = {b.upper() for b in my_bssids}
        for ap in scan.aps:
            if ap.bssid in wanted:
                return ap, True
    if my_ssids:
        wanted_ssid = {s.lower() for s in my_ssids}
        for ap in scan.aps:
            if ap.ssid.lower() in wanted_ssid:
                return ap, True
    for ap in scan.aps:
        if "connected" in ap.tags:
            return ap, True
    return sorted(scan.aps, key=lambda a: a.signal_dbm, reverse=True)[0], False


def _security_factor(ap: AccessPoint) -> HealthFactor:
    score = _SECURITY_SCORES.get(security_rank(ap.security), 60)
    if score >= 85:
        note = f"Cifrado sólido ({ap.security})."
    elif score >= 50:
        note = f"Cifrado aceptable pero antiguo ({ap.security})."
    elif score >= 15:
        note = f"Cifrado débil ({ap.security}); migra a WPA2/WPA3."
    else:
        note = "Red abierta: el tráfico viaja sin cifrar."
    return HealthFactor("security", "Seguridad", score, _WEIGHTS["security"], note)


def _congestion_factor(ap: AccessPoint, neighbors: list[AccessPoint]) -> HealthFactor:
    count = len(neighbors)
    score = max(0, 100 - 12 * count)
    if count == 0:
        note = f"Canal {ap.channel} despejado."
    elif count < 4:
        note = f"Canal {ap.channel} con {count} vecinos: llevadero."
    else:
        note = f"Canal {ap.channel} saturado: {count} vecinos compiten contigo."
    return HealthFactor("congestion", "Congestión", score, _WEIGHTS["congestion"], note)


def _channel_factor(ap: AccessPoint, neighbor_count: int) -> HealthFactor:
    if ap.band.value.endswith("5 GHz") or ap.band.value.endswith("6 GHz"):
        score = max(50, 100 - neighbor_count * 5)
        note = f"Banda de 5/6 GHz en canal {ap.channel}: buena elección."
    elif ap.channel in (1, 6, 11):
        score = max(40, 85 - neighbor_count * 8)
        note = f"Canal {ap.channel}: uno de los tres no solapados de 2.4 GHz."
    elif ap.channel:
        score = max(25, 60 - neighbor_count * 8)
        note = f"Canal {ap.channel} solapa con sus vecinos; usa 1, 6 u 11."
    else:
        score = 50
        note = "Canal desconocido."
    return HealthFactor("channel", "Canal", score, _WEIGHTS["channel"], note)


def _bandwidth_factor(ap: AccessPoint) -> HealthFactor:
    if ap.width_mhz:
        if ap.width_mhz >= 80:
            score, note = 100, f"Ancho de canal amplio ({ap.width_mhz} MHz)."
        elif ap.width_mhz >= 40:
            score, note = 80, f"Ancho de canal de {ap.width_mhz} MHz."
        else:
            score, note = 60, f"Ancho de canal estrecho ({ap.width_mhz} MHz)."
    elif ap.max_rate:
        if ap.max_rate >= 300:
            score, note = 100, f"Tasa enlace alta ({ap.max_rate:.0f} Mbit/s)."
        elif ap.max_rate >= 150:
            score, note = 80, f"Tasa enlace media ({ap.max_rate:.0f} Mbit/s)."
        else:
            score, note = 55, f"Tasa enlace baja ({ap.max_rate:.0f} Mbit/s)."
    else:
        score, note = 70, "Ancho/tasa desconocidos sin monitor mode."
    return HealthFactor("bandwidth", "Ancho de banda", score, _WEIGHTS["bandwidth"], note)


def _stability_factor(ap: AccessPoint, history: list[int]) -> HealthFactor:
    if len(history) < 3:
        if ap.signal_dbm >= -67:
            return HealthFactor("stability", "Estabilidad", 75, _WEIGHTS["stability"], "Aún sin histórico; señal razonable.")
        return HealthFactor("stability", "Estabilidad", 55, _WEIGHTS["stability"], "Aún sin histórico; señal justa.")
    spread = statistics.pstdev(history[-20:])
    score = max(0, 100 - spread * 4)
    weak_penalty = max(0, (-60 - ap.signal_dbm)) * 1.2
    score = max(0, score - weak_penalty)
    if spread <= 3:
        note = "Señal muy estable."
    elif spread <= 8:
        note = "Señal con oscilaciones leves."
    else:
        note = "Señal inestable; puede haber interferencia o distancia."
    return HealthFactor("stability", "Estabilidad", round(score), _WEIGHTS["stability"], note)


def _headline(total: int, is_mine: bool, my_ssids: tuple[str, ...]) -> str:
    prefix = "" if is_mine or my_ssids else "Sin red propia configurada; esto evalúa el entorno. "
    if total >= 80:
        return prefix + "No detecto problemas conocidos con el hardware actual."
    if total >= 60:
        return prefix + "Aceptable, con margen de mejora."
    if total >= 40:
        return prefix + "Hay problemas que conviene revisar."
    return prefix + "Red degradada: revisa los hallazgos recientes."


def _overlaps(a: AccessPoint, b: AccessPoint) -> bool:
    if not a.channel or not b.channel:
        return False
    if a.frequency_mhz and b.frequency_mhz:
        return abs(a.frequency_mhz - b.frequency_mhz) < 20
    if a.channel <= 14 and b.channel <= 14:
        return abs(a.channel - b.channel) <= 4
    return a.channel == b.channel
