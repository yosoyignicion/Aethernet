from __future__ import annotations

from pathlib import Path

from aethernet.core.oui import OuiDatabase

IEEE_SAMPLE = "\n".join(
    [
        "Registry included Below",
        "08-60-83   (hex)\t\tzte corporation",
        "086083     (base 16)\t\tzte corporation",
        "18-69-45   (hex)\t\tAcme Networks",
        "186945     (base 16)\t\tAcme Networks",
    ]
)


def _db(tmp_path: Path, content: str, name: str = "oui.txt") -> OuiDatabase:
    source = tmp_path / name
    source.write_text(content, encoding="utf-8")
    return OuiDatabase(paths=None, extra_files=(source,))


def test_parses_hex_and_base16_lines(tmp_path):
    db = _db(tmp_path, IEEE_SAMPLE).load()
    assert db.lookup("08:60:83:00:00:01") == "zte corporation"
    assert db.lookup("186945AABBCC") == "Acme Networks"


def test_vendor_not_polluted_with_format_prefix(tmp_path):
    db = _db(tmp_path, IEEE_SAMPLE).load()
    assert not db.lookup("08:60:83:00:00:01").startswith("(")


def test_tsv_fallback(tmp_path):
    db = _db(tmp_path, "00000C\tCisco Systems\n", name="oui.tsv").load()
    # el archivador TSV sin cabecera csv se parsea por líneas
    assert db.size >= 1


def test_unknown_oui_returns_none(tmp_path):
    db = _db(tmp_path, IEEE_SAMPLE).load()
    assert db.lookup("FF:FF:FF:FF:FF:FF") is None
