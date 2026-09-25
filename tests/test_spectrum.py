from __future__ import annotations

from aethernet.core.spectrum import (
    heatmap,
    occupancy,
    polar_points,
    recommend_channel,
    spectrum_snapshot,
)
from aethernet.models import Band
from helpers import ap, scan


def test_occupancy_counts_per_channel():
    s = scan(
        ap("A", "AA:BB:CC:00:00:01", channel=6),
        ap("B", "AA:BB:CC:00:00:02", channel=6),
        ap("C", "AA:BB:CC:00:00:03", channel=1),
    )
    rows = {r["channel"]: r for r in occupancy(s, Band.GHZ_24)}
    assert rows[6]["networks"] == 2
    assert rows[1]["networks"] == 1
    assert rows[11]["networks"] == 0


def test_recommendation_avoids_busy_channel():
    busy = [ap(f"V{i}", f"0{i}:00:00:00:00:0{i}", channel=6, dbm=-40) for i in range(1, 7)]
    s = scan(*busy)
    rec = recommend_channel(s, Band.GHZ_24)
    assert rec["channel"] in (1, 11)
    assert rec["free_pct"] > 50


def test_polar_points_have_geometry():
    s = scan(ap("A", "AA:BB:CC:00:00:01", channel=1, dbm=-40))
    points = polar_points(s)
    assert len(points) == 1
    assert 0 <= points[0]["radius"] <= 1
    assert 0 <= points[0]["angle_deg"] <= 360


def test_heatmap_matrix():
    rows = [
        {"hour": 3, "channel": 6, "samples": 5},
        {"hour": 3, "channel": 1, "samples": 2},
        {"hour": 4, "channel": 6, "samples": 1},
    ]
    grid = heatmap(rows)
    assert grid["channels"] == [1, 6]
    assert grid["matrix"][6][3] == 5
    assert grid["matrix"][6][4] == 1
    assert grid["max"] == 5


def test_spectrum_snapshot_shape():
    payload = spectrum_snapshot(scan(ap("A", "AA:BB:CC:00:00:01")), Band.GHZ_24)
    assert {"band", "occupancy", "overlap", "recommendation", "polar"} <= set(payload)
