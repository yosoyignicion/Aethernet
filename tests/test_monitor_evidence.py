from __future__ import annotations

from aethernet.core.monitor.evidence import format_hexdump


def test_empty():
    assert format_hexdump(b"") == "(sin datos)"


def test_basic_line():
    dump = format_hexdump(b"ABC")
    assert dump.startswith("0000  41 42 43")
    assert "ABC" in dump


def test_max_lines_truncates():
    dump = format_hexdump(b"\x00" * 200, width=16, max_lines=3)
    lines = dump.splitlines()
    assert len(lines) == 4  # 3 líneas + aviso de resto
    assert "bytes más" in lines[-1]


def test_non_printable_as_dot():
    dump = format_hexdump(b"\x00\x01")
    assert dump.endswith("..")
