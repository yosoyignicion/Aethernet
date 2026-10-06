from __future__ import annotations

import socket

from aethernet.core.fingerprint import (
    COMMON_SERVICES,
    classify_services,
    probe_ports,
    service_names,
)


def test_classify_printer():
    profile = classify_services([80, 9100])
    assert profile.role == "Impresora"
    assert profile.confidence == "alta"
    assert profile.ports == (80, 9100)


def test_camera_wins_over_web():
    profile = classify_services([554, 80, 443])
    assert profile.role == "Cámara IP / RTSP"


def test_classify_nas():
    assert classify_services([5000, 22]).role == "NAS / almacenamiento"


def test_empty_is_honest():
    profile = classify_services([])
    assert profile.role == "Sin servicios visibles"
    assert profile.confidence == "nula"


def test_unknown_ports():
    profile = classify_services([12345])
    assert profile.role == "Desconocido"
    assert "no reconocidos" in profile.reason


def test_service_names_label_known_and_raw():
    names = service_names([22, 9999])
    assert "22 SSH" in names
    assert "9999" in names


def test_common_services_all_labelled():
    assert all(COMMON_SERVICES.get(port) for port in COMMON_SERVICES)


def test_probe_ports_invalid_ip_returns_empty():
    assert probe_ports("not-an-ip") == ()
    assert probe_ports("999.999.999.999") == ()


def test_probe_ports_detects_open_port():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert port in probe_ports("127.0.0.1", [port], timeout=0.5)
