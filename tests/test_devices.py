from __future__ import annotations

from aethernet.core.devices import classify_device
from aethernet.models import LanDevice


def _dev(mac: str, ip: str = "192.168.1.10", *, vendor=None, hostname=None, gateway=False) -> LanDevice:
    return LanDevice(mac=mac, ip=ip, vendor=vendor, hostname=hostname, is_gateway=gateway)


def test_gateway_is_router():
    kind = classify_device(_dev("18:69:45:00:00:01", "192.168.1.1", gateway=True))
    assert "Router" in kind.label


def test_randomized_mac_detected():
    device = _dev("72:68:4F:F2:A2:D6", "172.19.0.2")
    assert device.is_randomized_mac
    assert classify_device(device).label == "MAC aleatoria"


def test_vendor_match_iot():
    kind = classify_device(_dev("00:11:22:33:44:55", vendor="Espressif Inc."))
    assert kind.label == "IoT"
    assert kind.confidence == "alta"


def test_hostname_match():
    kind = classify_device(_dev("00:11:22:33:44:66", hostname="raspberrypi"))
    assert "SBC" in kind.label


def test_unknown_device_honest():
    kind = classify_device(_dev("00:11:22:33:44:77"))
    assert kind.label == "Desconocido"
    assert kind.confidence == "nula"
