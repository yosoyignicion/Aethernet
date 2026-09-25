"""Exportadores de informes: Markdown, JSON, CSV y PDF opcional."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .base import ReportData, ReportDependencyError, build_report_data, output_path, redact_mac

Format = Literal["md", "markdown", "json", "csv", "pdf"]


def export(data: ReportData, fmt: Format, destination: Path) -> list[Path]:
    """Exporta en el formato pedido. Devuelve las rutas escritas."""
    fmt = fmt.lower()  # type: ignore[assignment]
    if fmt in ("md", "markdown"):
        from .markdown import export_markdown

        return [export_markdown(data, destination)]
    if fmt == "json":
        from .json_export import export_json

        return [export_json(data, destination)]
    if fmt == "csv":
        from .csv_export import export_csv

        return export_csv(data, destination)
    if fmt == "pdf":
        from .pdf import export_pdf

        return [export_pdf(data, destination)]
    raise ValueError(f"formato no soportado: {fmt}")


__all__ = [
    "Format",
    "ReportData",
    "ReportDependencyError",
    "build_report_data",
    "export",
    "output_path",
    "redact_mac",
]
