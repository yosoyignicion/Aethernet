from __future__ import annotations

from aethernet.core.health import score_health
from helpers import ap, scan


def test_no_data():
    health = score_health(scan())
    assert health.total == 0
    assert health.grade == "sin datos"
    assert health.factors == ()


def test_healthy_network_scores_high():
    target = ap("MiRed", "AA:AA:AA:AA:AA:AA", dbm=-45, channel=11, security="wpa3")
    target = ap("MiRed", "AA:AA:AA:AA:AA:AA", dbm=-45, channel=11, security="wpa3")
    health = score_health(
        scan(target),
        my_ssids=("MiRed",),
        my_bssids=("AA:AA:AA:AA:AA:AA",),
        signal_history={"AA:AA:AA:AA:AA:AA": [-45, -45, -46, -45]},
    )
    assert health.total >= 80
    assert health.grade in {"buena", "excelente"}
    assert len(health.factors) == 5


def test_congested_network_scores_lower():
    target = ap("MiRed", "AA:AA:AA:AA:AA:AA", dbm=-50, channel=6)
    neighbors = [ap(f"V{i}", f"0{i}:00:00:00:00:0{i}", channel=6) for i in range(1, 9)]
    health = score_health(
        scan(target, *neighbors),
        my_ssids=("MiRed",),
        my_bssids=("AA:AA:AA:AA:AA:AA",),
    )
    assert health.total < 55
    assert any(f.key == "congestion" and f.score < 20 for f in health.factors)


def test_weights_sum_to_one():
    health = score_health(scan(ap("X", "AA:BB:CC:00:00:01")), my_ssids=("X",))
    assert abs(sum(f.weight for f in health.factors) - 1.0) < 1e-9


def test_headline_is_honest_without_my_network():
    health = score_health(scan(ap("Vecino", "AA:BB:CC:00:00:01")))
    assert "entorno" in health.headline
