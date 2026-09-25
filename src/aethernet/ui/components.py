"""Componentes reutilizables de la interfaz AETHERNET."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from nicegui import ui

from ..models import Severity
from .theme import COLORS, SEVERITY_COLORS, icon


def label_caps(text: str, color: str | None = None) -> ui.label:
    element = ui.label(text).classes("ae-label")
    if color:
        element.style(f"color:{color}")
    return element


def status_dot(color: str, *, pulse: bool = False) -> None:
    with ui.element("div").classes("relative inline-flex").style("width:9px;height:9px"):
        if pulse:
            ui.element("span").classes("absolute inline-flex rounded-full ae-ping").style(
                f"width:9px;height:9px;background:{color}"
            )
        ui.element("span").classes("relative inline-flex rounded-full").style(
            f"width:9px;height:9px;background:{color}"
        )


def chip(text: str, *, active: bool = False, color: str | None = None, icon_name: str | None = None) -> ui.element:
    html = ""
    if icon_name:
        html += icon(icon_name, size=13) + " "
    html += text
    element = ui.html(html).classes("ae-chip" + (" active" if active else ""))
    if color:
        element.style(f"color:{color};border-color:{color}")
    return element


def severity_chip(severity: Severity) -> ui.element:
    return chip(severity.value.upper(), color=SEVERITY_COLORS[severity])


@contextmanager
def panel(*, classes: str = "", padding: str = "p-5") -> Iterator[ui.element]:
    with ui.element("div").classes(f"ae-panel {padding} {classes}") as container:
        yield container


def panel_header(icon_name: str, title: str, subtitle: str | None = None, accent: str | None = None) -> None:
    with ui.row().classes("items-center gap-3 w-full"):
        ui.html(icon(icon_name, size=20, color=accent or COLORS["cyan"]))
        with ui.column().classes("gap-0"):
            ui.label(title).classes("ae-headline text-base text-[#dfe2eb] leading-tight")
            if subtitle:
                label_caps(subtitle)


def metric_card(
    *,
    label: str,
    value: str,
    unit: str,
    icon_name: str,
    accent: str,
    hint: str = "",
    badge: str = "",
) -> None:
    with ui.element("div").classes("ae-card flex flex-col justify-between gap-3 min-h-[132px]"):
        with ui.row().classes("items-center justify-between w-full"):
            with ui.row().classes("items-center gap-2"):
                status_dot(accent, pulse=accent == COLORS["coral"])
                label_caps(label)
            ui.html(icon(icon_name, size=20, color=accent))
        with ui.row().classes("items-baseline gap-2"):
            ui.label(value).classes("ae-metric text-4xl").style(f"color:{accent}")
            label_caps(unit)
        with ui.row().classes("items-center justify-between w-full ae-sub px-2 py-1"):
            ui.label(hint or "—").classes("text-[11px] text-[#94A3B8] truncate")
            if badge:
                label_caps(badge, accent)


def kv_row(key: str, value: str, value_color: str | None = None) -> None:
    with ui.row().classes("items-center justify-between w-full py-1"):
        label_caps(key)
        ui.label(value).classes("ae-mono text-[12px] text-[#dfe2eb]").style(
            f"color:{value_color}" if value_color else ""
        )


def empty_state(message: str, icon_name: str = "search_off") -> None:
    with ui.column().classes("items-center justify-center gap-2 w-full py-10 opacity-70"):
        ui.html(icon(icon_name, size=32, color=COLORS["text-muted"]))
        ui.label(message).classes("text-[#94A3B8] text-sm")


def toast(message: str, *, icon_name: str = "check_circle", color: str | None = None) -> None:
    ui.notify(message, position="top", color=color or COLORS["surface-high"], icon=icon_name, timeout=3200)
