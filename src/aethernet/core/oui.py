"""Resolución de fabricante por OUI (primeros 3 bytes de la MAC).

Funciona 100% offline: usa la base del sistema si existe, una caché propia y
un conjunto mínimo de OUIs comunes. La descarga de la base IEEE es una acción
explícita del usuario (``aethernet oui --refresh``); nunca automática.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any

from ..logging_setup import get_logger
from ..utils import atomic_write, run_command

log = get_logger(__name__)

_SYSTEM_OUI_FILES = (
    Path("/usr/share/ieee-data/oui.txt"),
    Path("/var/lib/ieee-data/oui.txt"),
    Path("/usr/share/hwdata/oui.txt"),
    Path("/usr/share/misc/oui.txt"),
    Path("/usr/share/arp-scan/ieee-oui.txt"),
)

_IEEE_URL = "https://standards-oui.ieee.org/oui/oui.csv"

# Pequeño subconjunto para que la app sea útil sin base del sistema.
_BUNDLED: dict[str, str] = {
    "000C42": "Routerboard (MikroTik)",
    "001018": "Broadcom",
    "001E14": "Cisco",
    "0024A5": "Buffalo",
    "0026F2": "NETGEAR",
    "00D0F8": "AcerNet",
    "105172": "Cisco",
    "14CC20": "TP-Link",
    "1C7EE5": "Actiontec",
    "240AC4": "Xiaomi",
    "28C68E": "NETGEAR",
    "2C3033": "NETGEAR",
    "3C7C3F": "ASUS",
    "3C84C6": "Software Technologies Group",
    "441CA8": "Huawei",
    "48C9B0": "Arcadyan",
    "50C7BF": "TP-Link",
    "58D56E": "D-Link",
    "60A4D0": "Samsung",
    "689423": "Askey Computer",
    "6C5AB0": "Tenda",
    "70EE50": "ARRIS",
    "78D294": "NETGEAR",
    "7C4CA5": "Sky UK",
    "84C9B2": "D-Link",
    "88C9D0": "Arcadyan",
    "8C3BAD": "NETGEAR",
    "9C3DCF": "NETGEAR",
    "A0F3C1": "TP-Link",
    "AC84C6": "TP-Link",
    "B0BE76": "TP-Link",
    "B827EB": "Raspberry Pi Foundation",
    "C0A8E7": "Huawei",
    "C46E1F": "TP-Link",
    "D8D385": "Hewlett Packard",
    "DC4EF4": "Shenzhen",
    "E0B94D": "Motorola Mobility",
    "E4F4C6": "NETGEAR",
    "EC2280": "D-Link",
    "F4EC38": "TP-Link",
    "F8D111": "TP-Link",
}

_PATTERNS = (
    re.compile(r"^(?P<prefix>[0-9A-Fa-f]{2}[:-]){2}(?P<last>[0-9A-Fa-f]{2})\s*\(hex\)\s*(?P<vendor>.+)$"),
    re.compile(r"^(?P<prefix>[0-9A-Fa-f]{6})\s+(?P<vendor>.+)$"),
)


class OuiDatabase:
    """Índice OUI → fabricante con carga perezosa y caché local."""

    def __init__(self, paths: Any = None, extra_files: tuple[Path, ...] = ()) -> None:
        self._paths = paths
        self._extra_files = extra_files
        self._table: dict[str, str] = {}
        self._loaded = False

    @property
    def size(self) -> int:
        return len(self._table)

    def load(self) -> OuiDatabase:
        if self._loaded:
            return self
        self._table = dict(_BUNDLED)
        for path in self._candidate_files():
            try:
                self._load_file(path)
            except OSError:
                continue
        self._loaded = True
        return self

    def lookup(self, mac: str | None) -> str | None:
        if not mac:
            return None
        self.load()
        prefix = re.sub(r"[^0-9A-Fa-f]", "", mac)[:6].upper()
        if len(prefix) < 6:
            return None
        return self._table.get(prefix)

    # -- internos --------------------------------------------------------- #
    def _candidate_files(self) -> list[Path]:
        candidates: list[Path] = []
        if self._paths is not None and self._paths.oui_cache.exists():
            candidates.append(self._paths.oui_cache)
        candidates.extend(self._extra_files)
        candidates.extend(p for p in _SYSTEM_OUI_FILES if p.exists())
        return candidates

    def _load_file(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8", errors="replace")
        if path == getattr(self._paths, "oui_cache", None):
            self._parse_tsv(text)
        elif text.lstrip().startswith(("Registry", "Assignment")):
            self._parse_csv(text)
        else:
            self._parse_text(text)

    def _parse_tsv(self, text: str) -> None:
        for line in text.splitlines():
            prefix, _, vendor = line.partition("\t")
            if len(prefix) == 6:
                self._table.setdefault(prefix.upper(), vendor.strip())

    def _parse_csv(self, text: str) -> None:
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            value = (row.get("Assignment") or "").strip().upper()
            vendor = (row.get("Organization Name") or "").strip()
            if len(value) >= 6 and vendor:
                self._table.setdefault(value[:6], vendor)

    def _parse_text(self, text: str) -> None:
        for line in text.splitlines():
            for pattern in _PATTERNS:
                match = pattern.match(line.strip())
                if match:
                    vendor = match.group("vendor").strip()
                    if "prefix" in match.groupdict():
                        prefix = re.sub(r"[^0-9A-Fa-f]", "", match.group("prefix"))
                    else:  # pragma: no cover - formato alternativo
                        prefix = ""
                    if prefix and vendor:
                        self._table.setdefault(prefix.upper(), vendor)
                    break

    def save_cache(self) -> bool:
        if self._paths is None:
            return False
        lines = [f"{prefix}\t{vendor}" for prefix, vendor in sorted(self._table.items())]
        try:
            atomic_write(self._paths.oui_cache, "\n".join(lines) + "\n")
            return True
        except OSError:
            return False

    def refresh_from_ieee(self, timeout: float = 60.0) -> int:
        """Descarga explícita de la base IEEE CSV. Devuelve entradas añadidas."""
        result = run_command(["curl", "-fsSL", "--max-time", str(int(timeout)), _IEEE_URL], timeout=timeout + 5)
        if not result.ok:
            return 0
        before = len(self._table)
        self._parse_csv(result.stdout)
        self._loaded = True
        self.save_cache()
        return len(self._table) - before


_default: OuiDatabase | None = None


def vendor_for(mac: str | None, paths: Any = None) -> str | None:
    """API de conveniencia con instancia compartida."""
    global _default
    if _default is None:
        _default = OuiDatabase(paths)
    return _default.lookup(mac)
