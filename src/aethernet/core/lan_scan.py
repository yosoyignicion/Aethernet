"""Inventario LAN: ARP scan con scapy y respaldo por tabla de vecinos.

Scapy es opcional. Sin él, o sin root, se lee ``ip neigh`` / ``arp -a``:
menos exhaustivo pero honesto y sin privilegios.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor

from ..logging_setup import get_logger
from ..models import LanDevice, LanScan, normalize_mac
from ..utils import guess_subnet, run_command
from .oui import vendor_for

log = get_logger(__name__)

_IP_NEIGH_RE = re.compile(
    r"^(?P<ip>\d+\.\d+\.\d+\.\d+)\s+dev\s+(?P<dev>\S+)\s+(?:lladdr\s+(?P<mac>[\da-fA-F:]{17})\s+)?(?P<state>\w+)"
)
_ARP_A_RE = re.compile(
    r"\((?P<ip>\d+\.\d+\.\d+\.\d+)\)\s+at\s+(?P<mac>[\da-fA-F:]{17})"
)


def parse_ip_neigh(output: str, gateway_ip: str | None = None) -> list[LanDevice]:
    """Parser puro de ``ip neigh show``."""
    devices: list[LanDevice] = []
    for line in output.splitlines():
        match = _IP_NEIGH_RE.match(line.strip())
        if not match:
            continue
        mac = normalize_mac(match.group("mac"))
        if not mac or mac == "00:00:00:00:00:00":
            continue
        state = match.group("state").upper()
        devices.append(
            LanDevice(
                mac=mac,
                ip=match.group("ip"),
                vendor=vendor_for(mac),
                online=state not in {"FAILED", "INCOMPLETE"},
                is_gateway=match.group("ip") == gateway_ip,
            )
        )
    return _dedupe(devices)


def parse_arp_a(output: str, gateway_ip: str | None = None) -> list[LanDevice]:
    """Parser puro de ``arp -a`` (formatos GNU/BSD)."""
    devices: list[LanDevice] = []
    for line in output.splitlines():
        match = _ARP_A_RE.search(line)
        if not match:
            continue
        mac = normalize_mac(match.group("mac"))
        if not mac:
            continue
        devices.append(
            LanDevice(
                mac=mac,
                ip=match.group("ip"),
                vendor=vendor_for(mac),
                online=True,
                is_gateway=match.group("ip") == gateway_ip,
            )
        )
    return _dedupe(devices)


def gateway_ip() -> str | None:
    result = run_command(["ip", "route", "show", "default"], timeout=5)
    if result.ok:
        match = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", result.stdout)
        if match:
            return match.group(1)
    return None


def _dedupe(devices: list[LanDevice]) -> list[LanDevice]:
    best: dict[str, LanDevice] = {}
    for device in devices:
        prev = best.get(device.mac)
        if prev is None or (not prev.online and device.online):
            best[device.mac] = device
    return sorted(best.values(), key=lambda d: tuple(int(p) for p in d.ip.split(".")) if d.ip else ())


def arp_sweep(subnet: str, interface: str | None = None, timeout: float = 2.0) -> list[LanDevice] | None:
    """ARP scan activo con scapy. Devuelve ``None`` si scapy no está disponible."""
    try:
        from scapy.all import ARP, Ether, srp  # type: ignore
    except ImportError:
        return None

    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        return None
    if network.version != 4 or network.num_addresses > 4096:
        return None

    packet = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=str(network))
    try:
        if interface:
            answered, _ = srp(packet, timeout=timeout, verbose=0, iface=interface)
        else:
            answered, _ = srp(packet, timeout=timeout, verbose=0)
    except (OSError, PermissionError) as exc:
        log.warning("ARP sweep falló (%s); usando tabla de vecinos", exc)
        return None

    gw = gateway_ip()
    devices: list[LanDevice] = []
    for _, received in answered:
        mac = normalize_mac(received.hwsrc)
        if not mac:
            continue
        devices.append(
            LanDevice(
                mac=mac,
                ip=received.psrc,
                vendor=vendor_for(mac),
                online=True,
                is_gateway=received.psrc == gw,
            )
        )
    return _dedupe(devices)


def resolve_hostnames(devices: list[LanDevice], timeout: float = 1.0, workers: int = 16) -> list[LanDevice]:
    """Reverse DNS best-effort y acotado, en paralelo."""
    if not devices:
        return devices

    socket.setdefaulttimeout(timeout)

    def resolve(device: LanDevice) -> LanDevice:
        if not device.ip:
            return device
        try:
            hostname, _, _ = socket.gethostbyaddr(device.ip)
        except (OSError, socket.herror):
            return device
        return LanDevice(
            mac=device.mac,
            ip=device.ip,
            hostname=hostname,
            vendor=device.vendor,
            alias=device.alias,
            trusted=device.trusted,
            first_seen=device.first_seen,
            last_seen=device.last_seen,
            online=device.online,
            is_gateway=device.is_gateway,
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(resolve, devices))


def scan_lan(
    subnet: str | None = None,
    interface: str | None = None,
    *,
    active: bool = True,
    timeout: float = 2.0,
    resolve_names: bool = False,
) -> LanScan:
    """Escanea la LAN. Activo con scapy+root; si no, tabla de vecinos."""
    subnet = subnet or guess_subnet(interface)
    ts = time.time()
    gw = gateway_ip()
    source = "neigh"
    devices: list[LanDevice] | None = None

    if active:
        devices = arp_sweep(subnet, interface, timeout)
        if devices is not None:
            source = "arp-scapy"

    if devices is None:
        neigh = run_command(["ip", "neigh", "show"], timeout=6)
        if neigh.ok and neigh.stdout.strip():
            devices = parse_ip_neigh(neigh.stdout, gw)
        else:
            arp = run_command(["arp", "-a"], timeout=6)
            devices = parse_arp_a(arp.stdout, gw) if arp.ok else []

    if resolve_names:
        devices = resolve_hostnames(devices)

    return LanScan(timestamp=ts, subnet=subnet, devices=tuple(devices), source=source)
