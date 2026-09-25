from __future__ import annotations

from aethernet.core.wifi_scan import (
    channel_from_frequency,
    parse_iw_scan,
    parse_nmcli_wifi,
    split_nmcli_terse,
)

NMCLI_SAMPLE = "\n".join(
    [
        "*:Mi\\:Red:AA\\:BB\\:CC\\:DD\\:EE\\:FF:6:2437 MHz:78:130 Mbit/s:WPA2",
        ":--:11\\:22\\:33\\:44\\:55\\:66:1:2412 MHz:60:54 Mbit/s:",
        ":Vecino:22\\:33\\:44\\:55\\:66\\:77:11:2462 MHz:40:72 Mbit/s:WPA1 WPA2",
    ]
)

IW_SAMPLE = """BSS 00:11:22:33:44:55 (on wlan0)
\tfreq: 2412
\tsignal: -45.00 dBm
\tcapability: ESS Privacy (0x0411)
\tSSID: MiRed
\tRSN:\t * Version: 1
\t\t * Authentication suites: PSK
\tWPS:\t * Version: 1.0
BSS 66:77:88:99:aa:bb (on wlan0)
\tfreq: 5180
\tsignal: -60.00 dBm
\tcapability: ESS (0x0401)
\tSSID: Otra
\tRSN:\t * Authentication suites: SAE
"""


def test_split_nmcli_terse_handles_escaped_colons():
    fields = split_nmcli_terse("*:Mi\\:Red:AA\\:BB\\:CC\\:DD\\:EE\\:FF:6:2437 MHz:78:130 Mbit/s:WPA2")
    assert fields == ["*", "Mi:Red", "AA:BB:CC:DD:EE:FF", "6", "2437 MHz", "78", "130 Mbit/s", "WPA2"]


def test_parse_nmcli_wifi():
    aps = {ap.bssid: ap for ap in parse_nmcli_wifi(NMCLI_SAMPLE, timestamp=5.0)}
    assert len(aps) == 3
    mine = aps["AA:BB:CC:DD:EE:FF"]
    assert mine.ssid == "Mi:Red"
    assert mine.channel == 6
    assert mine.frequency_mhz == 2437
    assert mine.signal_dbm == -22
    assert mine.security == "wpa2"
    assert "connected" in mine.tags

    hidden = aps["11:22:33:44:55:66"]
    assert hidden.hidden
    assert hidden.display_ssid == "<oculta>"
    assert hidden.is_open

    neighbor = aps["22:33:44:55:66:77"]
    assert neighbor.security == "wpa2"


def test_parse_iw_scan_detects_wpa3_and_wps():
    aps = {ap.bssid: ap for ap in parse_iw_scan(IW_SAMPLE, timestamp=7.0)}
    assert len(aps) == 2
    mine = aps["00:11:22:33:44:55"]
    assert mine.ssid == "MiRed"
    assert mine.channel == 1
    assert mine.signal_dbm == -45
    assert mine.security == "wpa2"
    assert mine.wps is True

    other = aps["66:77:88:99:AA:BB"]
    assert other.channel == 36
    assert other.security == "wpa3"


def test_channel_from_frequency():
    assert channel_from_frequency(2412) == 1
    assert channel_from_frequency(2437) == 6
    assert channel_from_frequency(2462) == 11
    assert channel_from_frequency(5180) == 36


def test_dedupe_keeps_strongest():
    output = "\n".join(
        [
            ":Uno:AA\\:BB\\:CC\\:00\\:00\\:01:6:2437 MHz:30:54 Mbit/s:WPA2",
            ":Uno:AA\\:BB\\:CC\\:00\\:00\\:01:6:2437 MHz:70:54 Mbit/s:WPA2",
        ]
    )
    aps = parse_nmcli_wifi(output)
    assert len(aps) == 1
    assert aps[0].signal_dbm == -30
