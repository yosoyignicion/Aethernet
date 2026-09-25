"""Formateo de evidencia cruda (hexdump) para el inspector. Pura y testeable."""

from __future__ import annotations


def format_hexdump(data: bytes, *, width: int = 16, max_lines: int = 24) -> str:
    """Volcado estilo ``hexdump -C`` acotado a ``max_lines``.

    Cada línea: offset, bytes en hex y representación ASCII imprimible.
    """
    if not data:
        return "(sin datos)"
    lines: list[str] = []
    for offset in range(0, len(data), width):
        chunk = data[offset : offset + width]
        hex_part = " ".join(f"{byte:02x}" for byte in chunk)
        hex_part = hex_part.ljust(width * 3 - 1)
        ascii_part = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        lines.append(f"{offset:04x}  {hex_part}  {ascii_part}")
        if len(lines) >= max_lines:
            remaining = len(data) - offset - width
            if remaining > 0:
                lines.append(f"... ({remaining} bytes más)")
            break
    return "\n".join(lines)
