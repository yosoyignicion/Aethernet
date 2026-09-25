from __future__ import annotations

from aethernet.core.forecast import coverage, predict_channel, weekly_grid

BUCKETS = [
    {"weekday": 5, "hour": 0, "best_channel": 1, "n": 3, "availability": 100, "interference": 0.0},
    {"weekday": 5, "hour": 0, "best_channel": 1, "n": 2, "availability": 90, "interference": 0.4},
    {"weekday": 5, "hour": 0, "best_channel": 6, "n": 1, "availability": 60, "interference": 1.2},
    {"weekday": 6, "hour": 9, "best_channel": 11, "n": 4, "availability": 70, "interference": 0.5},
]


def test_predict_majority_channel():
    prediction = predict_channel(BUCKETS, weekday=5, hour=0)
    assert prediction is not None
    assert prediction.channel == 1
    assert prediction.samples == 6
    assert prediction.confidence > 0.8
    assert prediction.alternatives[0][0] == 1


def test_predict_requires_min_samples():
    tiny = [{"weekday": 0, "hour": 3, "best_channel": 6, "n": 1, "availability": 80, "interference": 0.2}]
    assert predict_channel(tiny, 0, 3) is None


def test_predict_unknown_slot_is_none():
    assert predict_channel(BUCKETS, weekday=2, hour=14) is None


def test_weekly_grid_shape():
    grid = weekly_grid(BUCKETS, weekday=5)
    assert grid["label"] == "Sáb"
    assert len(grid["hours"]) == 24
    assert grid["hours"][0]["channel"] == 1
    assert grid["hours"][1]["channel"] == 0  # sin datos


def test_coverage():
    cov = coverage(BUCKETS)
    assert cov["slots"] == 2
    assert cov["slots_total"] == 168
    assert cov["observations"] == 10
