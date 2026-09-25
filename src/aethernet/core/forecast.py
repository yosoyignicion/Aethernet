"""Previsión de canal por hora y día de la semana.

Puro y testeable: recibe los "buckets" agregados del repositorio
(``weekday, hour, best_channel, n, availability, interference``) y decide qué
canal conviene en un momento dado, con una medida de confianza basada en
cuántas observaciones respaldan la predicción.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

WEEKDAYS: tuple[str, ...] = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")

MIN_SAMPLES = 2


@dataclass(frozen=True, slots=True)
class Prediction:
    channel: int
    confidence: float
    samples: int
    avg_availability: int
    alternatives: tuple[tuple[int, float], ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "confidence": self.confidence,
            "samples": self.samples,
            "avg_availability": self.avg_availability,
            "alternatives": [{"channel": c, "share": s} for c, s in self.alternatives],
            "reason": self.reason,
        }


def predict_channel(buckets: list[dict[str, Any]], weekday: int, hour: int) -> Prediction | None:
    """Canal más probable para ``(weekday, hour)`` a partir del histórico."""
    rows = [b for b in buckets if int(b["weekday"]) == weekday and int(b["hour"]) == hour]
    if not rows:
        return None
    votes: dict[int, int] = defaultdict(int)
    avail: dict[int, list[int]] = defaultdict(list)
    for row in rows:
        channel = int(row["best_channel"])
        votes[channel] += int(row["n"])
        avail[channel].append(int(row["availability"]))
    total = sum(votes.values())
    if total < MIN_SAMPLES:
        return None

    def score(channel: int) -> tuple[int, float]:
        average = sum(avail[channel]) / len(avail[channel]) if avail[channel] else 0.0
        return votes[channel], average

    best = max(votes, key=score)
    confidence = votes[best] / total
    alternatives = tuple(
        sorted(((c, votes[c] / total) for c in votes), key=lambda item: -item[1])
    )
    avg_availability = round(sum(avail[best]) / len(avail[best])) if avail[best] else 0
    reason = (
        f"{WEEKDAYS[weekday]} {hour:02d}:00 → canal {best} en el "
        f"{confidence * 100:.0f}% de {total} observaciones."
    )
    return Prediction(
        channel=best,
        confidence=round(confidence, 2),
        samples=total,
        avg_availability=avg_availability,
        alternatives=alternatives,
        reason=reason,
    )


def weekly_grid(buckets: list[dict[str, Any]], weekday: int) -> dict[str, Any]:
    """Serie hora a hora para un día concreto, para pintar en la UI."""
    hours: list[dict[str, Any]] = []
    for hour in range(24):
        prediction = predict_channel(buckets, weekday, hour)
        hours.append(
            {
                "hour": hour,
                "channel": prediction.channel if prediction else 0,
                "availability": prediction.avg_availability if prediction else 0,
                "confidence": prediction.confidence if prediction else 0.0,
                "samples": prediction.samples if prediction else 0,
            }
        )
    return {"weekday": weekday, "label": WEEKDAYS[weekday], "hours": hours}


def coverage(buckets: list[dict[str, Any]]) -> dict[str, int]:
    """Cobertura del histórico: franjas con datos y total de observaciones."""
    slots = {(int(b["weekday"]), int(b["hour"])) for b in buckets}
    return {
        "slots": len(slots),
        "slots_total": 7 * 24,
        "observations": sum(int(b["n"]) for b in buckets),
    }
