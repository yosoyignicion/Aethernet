"""Exportador JSON para análisis externo."""

from __future__ import annotations

from pathlib import Path

from .base import ReportData


def export_json(data: ReportData, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(data.to_json(), encoding="utf-8")
    return destination
