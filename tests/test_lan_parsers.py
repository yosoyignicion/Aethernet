from __future__ import annotations

from aethernet.core.lan_scan import parse_arp_a, parse_ip_neigh

NEIGH = """192.168.1.1 dev wlan0 lladdr AA:BB:CC:00:00:01 REACHABLE
192.168.1.20 dev wlan0 lladdr 22:33:44:55:66:77 STALE
192.168.1.30 dev wlan0 FAILED
"""

ARPA = """? (192.168.1.1) at aa:bb:cc:00:00:01 [ether] on wlan0
? (192.168.1.20) at 22:33:44:55:66:77 [ether] on wlan0
"""


def test_parse_ip_neigh_marks_gateway_and_online():
    devices = {d.mac: d for d in parse_ip_neigh(NEIGH, gateway_ip="192.168.1.1")}
    assert devices["AA:BB:CC:00:00:01"].is_gateway
    assert devices["AA:BB:CC:00:00:01"].online
    assert devices["22:33:44:55:66:77"].online
    assert len(devices) == 2  # la entrada FAILED sin MAC se ignora


def test_parse_arp_a():
    devices = {d.mac: d for d in parse_arp_a(ARPA, gateway_ip="192.168.1.1")}
    assert len(devices) == 2
    assert devices["AA:BB:CC:00:00:01"].ip == "192.168.1.1"


def test_parse_ip_neigh_ignores_null_mac():
    output = "192.168.1.5 dev wlan0 lladdr 00:00:00:00:00:00 REACHABLE\n"
    assert parse_ip_neigh(output) == []
