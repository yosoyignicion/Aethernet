from __future__ import annotations

from aethernet.core.text import levenshtein, normalize_ssid, similar_ssid


def test_levenshtein_basic():
    assert levenshtein("", "") == 0
    assert levenshtein("abc", "abc") == 0
    assert levenshtein("abc", "abd") == 1
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein("", "abc") == 3


def test_levenshtein_symmetric():
    assert levenshtein("flaw", "lawn") == levenshtein("lawn", "flaw")


def test_normalize_ssid():
    assert normalize_ssid(" Mi_WiFi-5G. ") == "MiWiFi5G"


def test_similar_ssid_detects_lookalike():
    similar, distance = similar_ssid("MiWiFi_5G", "MiWifi_5G")
    assert similar
    assert distance <= 1


def test_similar_ssid_ignores_unrelated():
    similar, _ = similar_ssid("Casa", "Hotel")
    assert not similar


def test_similar_ssid_exact_is_not_flagged():
    similar, distance = similar_ssid("MiRed", "MiRed")
    assert not similar
    assert distance == 0
