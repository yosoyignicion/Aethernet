"""Huella de servicios de un dispositivo LAN: qué expone y qué rol sugiere.

Saber **qué hace** un dispositivo exige mirar sus servicios, y eso requiere una
**sonda activa** (conexión TCP a puertos comunes). Igual que el escaneo ARP, la
sonda solo se ejecuta si el usuario la pide y contra su propia LAN. La lógica de
clasificación es pura y testeable sin red; la sonda de red vive aparte y degrada
con gracia (IP inválida o sin permisos devuelven vacío, nunca rompen).
"""

from __future__ import annotations

import socket
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

# Puerto -> etiqueta legible. Solo puertos que típicamente aceptan TCP.
COMMON_SERVICES: dict[int, str] = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    139: "NetBIOS",
    143: "IMAP",
    443: "HTTPS",
    445: "SMB",
    515: "LPD (impresión)",
    554: "RTSP (cámara)",
    631: "IPP (impresión)",
    1883: "MQTT",
    2049: "NFS",
    3306: "MySQL",
    3389: "RDP",
    5000: "UPnP/NAS",
    5900: "VNC",
    8080: "HTTP-alt",
    8443: "HTTPS-alt",
    9100: "Impresión RAW",
    32400: "Plex",
}

DEFAULT_PORTS: tuple[int, ...] = tuple(sorted(COMMON_SERVICES))

# (rol, puertos que lo delatan, confianza, motivo). El orden marca prioridad.
_ROLE_RULES: tuple[tuple[str, frozenset[int], str, str], ...] = (
    ("Impresora", frozenset({9100, 631, 515}), "alta", "expone impresión"),
    ("Cámara IP / RTSP", frozenset({554}), "alta", "expone streaming RTSP"),
    ("Servidor multimedia", frozenset({32400}), "media", "expone Plex"),
    ("NAS / almacenamiento", frozenset({5000, 2049}), "media", "expone servicios de NAS"),
    ("Domótica / IoT", frozenset({1883}), "media", "expone broker MQTT"),
    ("Compartición de archivos", frozenset({445, 139}), "media", "expone SMB/NetBIOS"),
    ("Servidor DNS / red", frozenset({53}), "media", "responde DNS"),
    ("Acceso remoto", frozenset({22, 3389, 5900}), "media", "expone SSH/RDP/VNC"),
    ("Interfaz web", frozenset({80, 443, 8080, 8443}), "baja", "expone HTTP/HTTPS"),
)


@dataclass(frozen=True, slots=True)
class ServiceProfile:
    """Rol estimado de un dispositivo a partir de sus puertos abiertos."""

    role: str
    confidence: str
    reason: str
    ports: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "confidence": self.confidence,
            "reason": self.reason,
            "ports": list(self.ports),
        }


def service_names(ports: Sequence[int]) -> tuple[str, ...]:
    """Etiquetas legibles de los puertos, con el número delante."""
    labels: list[str] = []
    for port in sorted({int(p) for p in ports}):
        label = COMMON_SERVICES.get(port)
        labels.append(f"{port} {label}" if label else str(port))
    return tuple(labels)


def classify_services(open_ports: Sequence[int]) -> ServiceProfile:
    """Rol heurístico y **explicable** a partir de los puertos abiertos."""
    ports = tuple(sorted({int(p) for p in open_ports}))
    if not ports:
        return ServiceProfile(
            "Sin servicios visibles", "nula", "no respondió en los puertos sondeados", ports
        )
    for role, candidates, confidence, reason in _ROLE_RULES:
        matched = sorted(candidates.intersection(ports))
        if matched:
            join = ", ".join(str(p) for p in matched)
            return ServiceProfile(role, confidence, f"{reason} ({join})", ports)
    known = tuple(p for p in ports if p in COMMON_SERVICES)
    if known:
        join = ", ".join(str(p) for p in known)
        return ServiceProfile("Dispositivo con red", "baja", f"abiertos: {join}", ports)
    return ServiceProfile("Desconocido", "nula", "puertos abiertos no reconocidos", ports)


def probe_ports(
    ip: str,
    ports: Sequence[int] = DEFAULT_PORTS,
    *,
    timeout: float = 0.6,
    workers: int = 32,
) -> tuple[int, ...]:
    """Sonda TCP (connect) y devuelve los puertos que aceptan conexión.

    **Activa**: solo debe invocarse bajo petición del usuario y sobre su propia
    red. Un IP inválido o un fallo de socket devuelven tupla vacía.
    """
    try:
        socket.inet_aton(ip)
    except OSError:
        return ()

    def is_open(port: int) -> int | None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                if sock.connect_ex((ip, port)) == 0:
                    return port
        except OSError:
            return None
        return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(is_open, ports)
    return tuple(port for port in results if port is not None)
