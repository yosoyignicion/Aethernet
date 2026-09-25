"""Constructores de opciones ECharts con la estética AETHERNET.

Funciones puras: reciben datos reales del backend y devuelven un dict que
``ui.echart`` renderiza. Nada de estado.
"""

from __future__ import annotations

from typing import Any

from .theme import COLORS, GRADE_COLORS

_MONO = "JetBrains Mono"
_GRID = "#0E1E15"
_AXIS = "#3F6B52"


def update(chart: Any, options: dict[str, Any]) -> None:
    """Actualiza un ``ui.echart`` en el sitio (la propiedad ``options`` no tiene setter)."""
    chart.options.clear()
    chart.options.update(options)
    chart.update()


def _base() -> dict[str, Any]:
    return {
        "backgroundColor": "transparent",
        "textStyle": {"fontFamily": _MONO, "color": COLORS["text-dim"]},
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": COLORS["surface-2"],
            "borderColor": COLORS["border"],
            "textStyle": {"color": COLORS["text"], "fontFamily": _MONO, "fontSize": 11},
        },
    }


def gauge(score: int, grade: str) -> dict[str, Any]:
    color = GRADE_COLORS.get(grade, COLORS["amber"])
    return {
        "backgroundColor": "transparent",
        "series": [
            {
                "type": "gauge",
                "startAngle": 225,
                "endAngle": -45,
                "min": 0,
                "max": 100,
                "radius": "92%",
                "progress": {"show": True, "roundCap": True, "width": 12, "itemStyle": {"color": color}},
                "axisLine": {"roundCap": True, "lineStyle": {"width": 12, "color": [[1, _GRID]]}},
                "pointer": {"show": True, "length": "58%", "width": 3, "itemStyle": {"color": COLORS["text"]}},
                "anchor": {"show": True, "size": 12, "itemStyle": {"color": COLORS["text"]}},
                "axisTick": {"distance": -18, "splitNumber": 5, "lineStyle": {"color": _AXIS}},
                "splitLine": {"distance": -20, "length": 10, "lineStyle": {"color": _AXIS}},
                "axisLabel": {"distance": -6, "color": _AXIS, "fontSize": 9, "fontFamily": _MONO},
                "detail": {"show": False},
                "data": [{"value": score}],
            }
        ],
    }


def channel_bars(occupancy: list[dict[str, Any]], recommended: int | None = None) -> dict[str, Any]:
    channels = [f"C{r['channel']}" for r in occupancy]
    networks = [r["networks"] for r in occupancy]
    peak = max(networks) if networks else 0
    colors = []
    for row in occupancy:
        if recommended is not None and row["channel"] == recommended:
            colors.append(COLORS["mint"])
        elif peak and row["networks"] >= peak:
            colors.append(COLORS["amber"])
        elif row["networks"] == 0:
            colors.append(COLORS["surface-high"])
        else:
            colors.append(COLORS["cyan"])
    options = _base()
    options.update(
        {
            "grid": {"left": 34, "right": 12, "top": 16, "bottom": 24},
            "xAxis": {
                "type": "category",
                "data": channels,
                "axisLine": {"lineStyle": {"color": COLORS["border"]}},
                "axisLabel": {"color": _AXIS, "fontSize": 9, "fontFamily": _MONO},
            },
            "yAxis": {
                "type": "value",
                "splitLine": {"lineStyle": {"color": _GRID}},
                "axisLabel": {"color": _AXIS, "fontSize": 9, "fontFamily": _MONO},
                "name": "redes",
                "nameTextStyle": {"color": _AXIS, "fontSize": 9},
            },
            "series": [
                {
                    "type": "bar",
                    "data": [
                        {"value": n, "itemStyle": {"color": c, "borderRadius": [3, 3, 0, 0]}}
                        for n, c in zip(networks, colors, strict=False)
                    ],
                    "barWidth": "62%",
                }
            ],
        }
    )
    return options


def congestion_area(hourly: list[dict[str, Any]]) -> dict[str, Any]:
    hours = [f"{r['hour']:02d}:00" for r in hourly]
    band24 = [r["band24"] for r in hourly]
    band5 = [r["band5"] for r in hourly]
    options = _base()
    options.update(
        {
            "grid": {"left": 36, "right": 16, "top": 20, "bottom": 28},
            "legend": {
                "data": ["2.4 GHz", "5 GHz"],
                "textStyle": {"color": COLORS["text-dim"], "fontSize": 10, "fontFamily": _MONO},
                "top": 0,
                "right": 0,
            },
            "xAxis": {
                "type": "category",
                "data": hours,
                "boundaryGap": False,
                "axisLine": {"lineStyle": {"color": COLORS["border"]}},
                "axisLabel": {"color": _AXIS, "fontSize": 9, "fontFamily": _MONO, "interval": 3},
            },
            "yAxis": {
                "type": "value",
                "splitLine": {"lineStyle": {"color": _GRID}},
                "axisLabel": {"color": _AXIS, "fontSize": 9, "fontFamily": _MONO},
            },
            "series": [
                {
                    "name": "2.4 GHz",
                    "type": "line",
                    "smooth": True,
                    "symbol": "none",
                    "data": band24,
                    "lineStyle": {"color": COLORS["mint"], "width": 2},
                    "areaStyle": {"color": "rgba(0,229,160,0.22)"},
                },
                {
                    "name": "5 GHz",
                    "type": "line",
                    "smooth": True,
                    "symbol": "none",
                    "data": band5,
                    "lineStyle": {"color": COLORS["cyan"], "width": 1.5, "type": "dashed"},
                },
            ],
        }
    )
    return options


def heatmap(grid: dict[str, Any]) -> dict[str, Any]:
    hours = grid.get("hours", [])
    channels = grid.get("channels", [])
    matrix = grid.get("matrix", {})
    data: list[list[int]] = []
    for channel in channels:
        row = matrix.get(channel, [])
        for hour in hours:
            value = row[hour] if hour < len(row) else 0
            data.append([hour, channels.index(channel), value])
    return {
        "backgroundColor": "transparent",
        "tooltip": {
            "position": "top",
            "backgroundColor": COLORS["surface-2"],
            "borderColor": COLORS["border"],
            "textStyle": {"color": COLORS["text"], "fontFamily": _MONO, "fontSize": 11},
        },
        "grid": {"left": 40, "right": 12, "top": 8, "bottom": 40},
        "xAxis": {
            "type": "category",
            "data": [f"{h:02d}" for h in hours],
            "axisLabel": {"color": _AXIS, "fontSize": 8, "fontFamily": _MONO},
            "axisLine": {"lineStyle": {"color": COLORS["border"]}},
        },
        "yAxis": {
            "type": "category",
            "data": [f"CH {c:02d}" for c in channels],
            "axisLabel": {"color": _AXIS, "fontSize": 8, "fontFamily": _MONO},
            "axisLine": {"lineStyle": {"color": COLORS["border"]}},
        },
        "visualMap": {
            "min": 0,
            "max": grid.get("max", 1) or 1,
            "calculable": False,
            "orient": "horizontal",
            "left": "center",
            "bottom": 0,
            "itemHeight": 90,
            "textStyle": {"color": _AXIS, "fontSize": 9, "fontFamily": _MONO},
            "inRange": {"color": [COLORS["void"], "#062b1f", COLORS["mint"], COLORS["amber"], COLORS["coral"]]},
        },
        "series": [
            {
                "type": "heatmap",
                "data": data,
                "itemStyle": {"borderColor": COLORS["void"], "borderWidth": 1},
                "emphasis": {"itemStyle": {"borderColor": COLORS["text"], "borderWidth": 1}},
            }
        ],
    }


def polar(points: list[dict[str, Any]]) -> dict[str, Any]:
    max_channel = max((p["channel"] or 1) for p in points) if points else 1
    categories = [str(c) for c in range(1, int(max_channel) + 1)]
    data = [
        {
            "value": [p["channel"] - 1, round(p["radius"] * 100)],
            "name": p["ssid"],
            "symbolSize": 8,
        }
        for p in points
    ]
    return {
        "backgroundColor": "transparent",
        "tooltip": {
            "backgroundColor": COLORS["surface-2"],
            "borderColor": COLORS["border"],
            "textStyle": {"color": COLORS["text"], "fontFamily": _MONO, "fontSize": 11},
        },
        "polar": {"radius": "78%"},
        "angleAxis": {
            "type": "category",
            "data": categories,
            "startAngle": 90,
            "axisLabel": {"color": _AXIS, "fontSize": 8, "fontFamily": _MONO},
            "splitLine": {"lineStyle": {"color": _GRID}},
            "axisLine": {"lineStyle": {"color": COLORS["border"]}},
        },
        "radiusAxis": {
            "min": 0,
            "max": 100,
            "axisLabel": {"color": _AXIS, "fontSize": 8, "fontFamily": _MONO},
            "splitLine": {"lineStyle": {"color": _GRID}},
        },
        "series": [
            {
                "type": "scatter",
                "coordinateSystem": "polar",
                "data": data,
                "itemStyle": {"color": COLORS["mint"], "opacity": 0.85},
            }
        ],
    }


def sparkline(series: list[tuple[float, int]], color: str | None = None) -> dict[str, Any]:
    color = color or COLORS["cyan"]
    values = [s for _, s in series]
    return {
        "backgroundColor": "transparent",
        "grid": {"left": 0, "right": 0, "top": 4, "bottom": 4},
        "xAxis": {"type": "category", "show": False, "boundaryGap": False, "data": list(range(len(values)))},
        "yAxis": {"type": "value", "show": False, "min": "dataMin", "max": "dataMax"},
        "series": [
            {
                "type": "line",
                "data": values or [0],
                "smooth": True,
                "symbol": "none",
                "lineStyle": {"color": color, "width": 1.6},
                "areaStyle": {"color": "rgba(0,184,255,0.15)"},
            }
        ],
    }


def forecast_bars(hours: list[dict[str, Any]]) -> dict[str, Any]:
    """Disponibilidad prevista por hora, coloreada por canal recomendado."""
    labels = [f"{h['hour']:02d}" for h in hours]
    palette = {1: COLORS["mint"], 6: COLORS["cyan"], 11: COLORS["amber"]}
    data = []
    for row in hours:
        channel = int(row.get("channel") or 0)
        availability = int(row.get("availability") or 0)
        if channel == 0:
            data.append({"value": 0, "itemStyle": {"color": COLORS["surface-high"], "borderRadius": [3, 3, 0, 0]}})
        else:
            data.append(
                {
                    "value": availability,
                    "itemStyle": {"color": palette.get(channel, COLORS["coral"]), "borderRadius": [3, 3, 0, 0]},
                }
            )
    options = _base()
    options.update(
        {
            "grid": {"left": 34, "right": 12, "top": 16, "bottom": 24},
            "xAxis": {
                "type": "category",
                "data": labels,
                "axisLine": {"lineStyle": {"color": COLORS["border"]}},
                "axisLabel": {"color": _AXIS, "fontSize": 9, "fontFamily": _MONO},
            },
            "yAxis": {
                "type": "value",
                "max": 100,
                "splitLine": {"lineStyle": {"color": _GRID}},
                "axisLabel": {"color": _AXIS, "fontSize": 9, "fontFamily": _MONO},
            },
            "series": [{"type": "bar", "data": data, "barWidth": "70%"}],
        }
    )
    return options


def occupancy_report_bars(values: list[int], labels: list[str], peak_index: int | None = None) -> dict[str, Any]:
    colors = [
        COLORS["amber"] if peak_index is not None and i == peak_index else COLORS["mint"]
        for i in range(len(values))
    ]
    return {
        "backgroundColor": "transparent",
        "grid": {"left": 28, "right": 8, "top": 8, "bottom": 22},
        "xAxis": {
            "type": "category",
            "data": labels,
            "axisLabel": {"color": _AXIS, "fontSize": 8, "fontFamily": _MONO},
            "axisLine": {"lineStyle": {"color": COLORS["border"]}},
        },
        "yAxis": {
            "type": "value",
            "max": 100,
            "axisLabel": {"color": _AXIS, "fontSize": 8, "fontFamily": _MONO},
            "splitLine": {"lineStyle": {"color": _GRID}},
        },
        "series": [
            {
                "type": "bar",
                "data": [
                    {"value": v, "itemStyle": {"color": c, "borderRadius": [2, 2, 0, 0]}}
                    for v, c in zip(values, colors, strict=False)
                ],
                "barWidth": "60%",
            }
        ],
    }
