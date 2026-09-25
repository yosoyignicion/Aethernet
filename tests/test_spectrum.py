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


def test_recommend_from_stats_prefers_free_channel():
    from aethernet.core.spectrum import recommend_from_stats

    observations = [
        {"channel": 6, "aps": 8, "avg_signal": -45},
        {"channel": 1, "aps": 1, "avg_signal": -80},
        {"channel": 11, "aps": 0, "avg_signal": None},
    ]
    rec = recommend_from_stats(observations, Band.GHZ_24)
    assert rec["channel"] == 11
    assert rec["availability"] == 100
    assert rec["ranking"][0] == 11


def test_recommend_from_stats_avoids_busy_but_is_defined_when_empty():
    from aethernet.core.spectrum import recommend_from_stats

    assert recommend_from_stats([], Band.GHZ_24)["channel"] in (1, 6, 11)
    busy = [{"channel": 1, "aps": 6, "avg_signal": -40}]
    assert recommend_from_stats(busy, Band.GHZ_24)["channel"] != 1


def test_channel_table_ranks_busy_channel_last():
    from aethernet.core.spectrum import channel_table

    stats = [{"channel": 6, "aps": 8, "avg_signal": -45}, {"channel": 11, "aps": 0, "avg_signal": None}]
    table = {r["channel"]: r for r in channel_table(stats, Band.GHZ_24)}
    assert table[11]["rank"] < table[6]["rank"]
    assert table[11]["availability"] == 100
    assert table[6]["availability"] < 100
    assert table[6]["networks"] == 8


def test_evaluate_channel_improvement_vs_current():
    from aethernet.core.spectrum import evaluate_channel

    stats = [{"channel": 6, "aps": 8, "avg_signal": -45}]
    result = evaluate_channel(11, stats, Band.GHZ_24, current=6)
    assert result["channel"] == 11
    assert result["vs_current"]["better"] is True
    assert result["vs_current"]["interference_delta"] > 0
    assert result["vs_current"]["availability_delta"] > 0


def test_advise_channel_change():
    from aethernet.core.spectrum import advise_channel_change

    table = [
        {"channel": 6, "interference": 4.0, "availability": 0, "rank": 3, "networks": 8},
        {"channel": 11, "interference": 0.0, "availability": 100, "rank": 1, "networks": 0},
        {"channel": 1, "interference": 1.0, "availability": 75, "rank": 2, "networks": 1},
    ]
    advice = advise_channel_change(table, 6, min_improvement=15)
    assert advice is not None
    assert advice["recommended"] == 11
    assert advice["improvement_pct"] == 100
    assert advise_channel_change(table, 11) is None


def test_advise_threshold_ignores_marginal():
    from aethernet.core.spectrum import advise_channel_change

    table = [
        {"channel": 6, "interference": 1.0, "availability": 75, "rank": 2, "networks": 1},
        {"channel": 11, "interference": 0.95, "availability": 76, "rank": 1, "networks": 1},
    ]
    assert advise_channel_change(table, 6, min_improvement=15) is None


def test_occupancy_split_separates_mine_from_neighbors():
    from aethernet.core.spectrum import occupancy_split

    s = scan(
        ap("MiRed", "AA:BB:CC:00:00:01", channel=6, tags=("connected",)),
        ap("Vecino", "AA:BB:CC:00:00:02", channel=6),
        ap("Vecino2", "AA:BB:CC:00:00:03", channel=6),
        ap("Otro", "AA:BB:CC:00:00:04", channel=1),
    )
    rows = {r["channel"]: r for r in occupancy_split(s, my_ssids=("MiRed",))}
    assert rows[6]["mine"] == 1
    assert rows[6]["others"] == 2
    assert rows[1]["mine"] == 0
    assert rows[1]["others"] == 1
