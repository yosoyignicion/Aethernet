"""Utilidades transversales: ejecución de comandos, tiempo y sistema."""

from __future__ import annotations

import ipaddress
import re
import shutil
import subprocess
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .logging_setup import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CommandResult:
    argv: Sequence[str]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def lines(self) -> list[str]:
        return [line for line in self.stdout.splitlines() if line.strip()]


def which(program: str) -> str | None:
    return shutil.which(program)


def run_command(
    argv: Sequence[str],
    *,
    timeout: float = 20.0,
    check: bool = False,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> CommandResult:
    """Ejecuta un comando sin shell (seguro) y devuelve un resultado tipado."""
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            input=input_text,
            check=False,
        )
    except FileNotFoundError:
        return CommandResult(argv, 127, "", f"no encontrado: {argv[0]}", 0.0)
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        return CommandResult(argv, 124, partial, f"timeout tras {timeout}s", timeout * 1000)
    duration = (time.perf_counter() - start) * 1000
    result = CommandResult(argv, proc.returncode, proc.stdout, proc.stderr, duration)
    if check and not result.ok:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(argv)}\n{result.stderr}")
    return result


def now() -> float:
    return time.time()


def humanize_age(seconds: float) -> str:
    """Convierte segundos en una frase relativa corta en español."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "hace unos segundos"
    if seconds < 3600:
        minutes = seconds // 60
        return f"hace {minutes} min"
    if seconds < 86400:
        hours = seconds // 3600
        return f"hace {hours} h"
    days = seconds // 86400
    return f"hace {days} d" if days > 1 else "hace 1 d"


def signal_to_quality(dbm: int) -> int:
    """RSSI (dBm) → calidad 0-100. Aproximación tipo nmcli."""
    if dbm <= -110:
        return 0
    if dbm >= -30:
        return 100
    return int(round(2 * (dbm + 100)))


def quality_to_bars(quality: int) -> str:
    filled = max(0, min(4, round(quality / 25)))
    return "▂▄▆█"[:filled] or "·"


def guess_subnet(interface: str | None = None) -> str:
    """Deduce la subred local desde la tabla de rutas o las interfaces."""
    argv = ["ip", "-4", "-o", "addr", "show"]
    result = run_command(argv, timeout=5)
    best = "192.168.1.0/24"
    if result.ok:
        candidates: list[str] = []
        for line in result.lines():
            if interface and f" {interface} " not in f" {line} ":
                continue
            match = re.search(r"inet (\d+\.\d+\.\d+\.\d+/\d+)", line)
            if match:
                candidates.append(match.group(1))
        for cidr in candidates:
            try:
                net = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                continue
            if net.is_loopback:
                continue
            if net.version == 4 and net.num_addresses <= 1024:
                return str(net)
        if candidates:
            return candidates[0]
    return best


def host_in_subnet(ip: str, cidr: str) -> bool:
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def first(iterable: Iterable[object], default: object = None) -> object:
    for item in iterable:
        return item
    return default
