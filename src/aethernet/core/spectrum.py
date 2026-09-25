"""Analizador de espectro: ocupación, solapamiento, heatmap y radar polar.

TODO aquí son funciones puras sobre un :class:`WifiScan` o filas agregadas del
repositorio. La UI solo dibuja lo que estos datos describen.
"""

from __future__ import annotations

import math
from typing import Any

from ..models import Band, WifiScan

CHANNELS_24: tuple[int, ...] = tuple(range(1, 14))
CHANNELS_5: tuple[int, ...] = (36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 132, 136, 140, 149, 153, 157, 161, 165)
CHANNELS_24_NON_OVERLAP: tuple[int, ...] = (1, 6, 11)


def band_channels(band: Band | str = Band.GHZ_24) -> tuple[int, ...]:
    value = band.value if isinstance(band, Band) else band
    if "5" in value:
        return CHANNELS_5
    if "6" in value:
        return tuple(range(1, 234, 4))
    return CHANNELS_24


def occupancy(scan: WifiScan, band: Band | str = Band.GHZ_24) -> list[dict[str, Any]]:
    """Por canal: cuántas redes y la señal más fuerte vista."""
    channels = band_channels(band)
    buckets: dict[int, list[int]] = {}
    for ap in scan.aps:
        if ap.channel in channels:
            buckets.setdefault(ap.channel, []).append(ap.signal_dbm)
    return [
        {
            "channel": channel,
            "networks": len(buckets.get(channel, [])),
            "strongest_dbm": max(buckets[channel]) if buckets.get(channel) else None,
            "avg_dbm": round(sum(buckets[channel]) / len(buckets[channel])) if buckets.get(channel) else None,
        }
        for channel in channels
    ]


def _kernel(distance: float, band: Band | str) -> float:
    value = band.value if isinstance(band, Band) else band
    if "5" in value or "6" in value:
        return 1.0 if distance == 0 else 0.0
    return max(0.0, 1.0 - distance / 5.0)


def overlap_series(scan: WifiScan, band: Band | str = Band.GHZ_24) -> list[dict[str, Any]]:
    """Curva de interferencia: cuánto se pisan los canales entre sí."""
    channels = band_channels(band)
    series: list[dict[str, Any]] = []
    for target in channels:
        interference = 0.0
        contributors: list[str] = []
        for ap in scan.aps:
            if ap.channel not in channels:
                continue
            weight = _kernel(abs(ap.channel - target), band)
            if weight <= 0:
                continue
            # Señal más fuerte ⇒ más peso. Normalizamos -90..-30 → 0..1.
            strength = max(0.0, min(1.0, (ap.signal_dbm + 90) / 60.0))
            interference += weight * strength
            contributors.append(ap.bssid)
        series.append(
            {
                "channel": target,
                "interference": round(interference, 3),
                "contributors": len(contributors),
            }
        )
    return series


def recommend_channel(scan: WifiScan, band: Band | str = Band.GHZ_24) -> dict[str, Any]:
    """Canal recomendado con estimación de disponibilidad."""
    value = band.value if isinstance(band, Band) else band
    series = {row["channel"]: row for row in overlap_series(scan, band)}

    candidates = list(CHANNELS_24_NON_OVERLAP) if "2.4" in value else list(band_channels(band))

    best_channel = candidates[0]
    best_interference = math.inf
    for channel in candidates:
        row = series.get(channel)
        interference = row["interference"] if row else 0.0
        if interference < best_interference:
            best_interference, best_channel = interference, channel

    free_pct = max(0, min(100, round(100 - best_interference * 25)))
    if best_interference <= 0:
        free_pct = 100
    return {
        "channel": best_channel,
        "free_pct": free_pct,
        "interference": round(best_interference, 3),
        "band": value,
        "reason": f"Canal {best_channel}: libre el {free_pct} % del tiempo observado.",
    }


def heatmap(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Matriz hora-del-día × canal a partir de filas agregadas del repositorio."""
    hours = list(range(24))
    channels = sorted({int(r["channel"]) for r in rows if r.get("channel")})
    matrix: dict[int, list[int]] = {c: [0] * 24 for c in channels}
    for row in rows:
        channel = row.get("channel")
        hour = row.get("hour")
        if channel in matrix and hour is not None and 0 <= int(hour) <= 23:
            matrix[int(channel)][int(hour)] += int(row.get("samples", 0) or 0)
    return {
        "hours": hours,
        "channels": channels,
        "matrix": matrix,
        "max": max((max(v) for v in matrix.values()), default=0),
    }


def polar_points(scan: WifiScan) -> list[dict[str, Any]]:
    """Cada red como punto en un radar: ángulo por canal, radio por señal."""
    aps = scan.aps
    if not aps:
        return []
    max_channel = max((ap.channel or 1) for ap in aps)
    points: list[dict[str, Any]] = []
    for ap in aps:
        angle = 360.0 * ((ap.channel or 1) - 1) / max(max_channel, 1)
        radius = max(0.05, min(1.0, (ap.signal_dbm + 100) / 60.0))
        points.append(
            {
                "bssid": ap.bssid,
                "ssid": ap.display_ssid,
                "channel": ap.channel,
                "signal_dbm": ap.signal_dbm,
                "angle_deg": round(angle, 1),
                "radius": round(radius, 3),
                "band": ap.band.value,
                "security": ap.security,
                "mine": "connected" in ap.tags,
            }
        )
    return points


def spectrum_snapshot(scan: WifiScan, band: Band | str = Band.GHZ_24) -> dict[str, Any]:
    """Paquete completo listo para serializar y pintar en la UI."""
    return {
        "band": band.value if isinstance(band, Band) else band,
        "occupancy": occupancy(scan, band),
        "overlap": overlap_series(scan, band),
        "recommendation": recommend_channel(scan, band),
        "polar": polar_points(scan),
    }
