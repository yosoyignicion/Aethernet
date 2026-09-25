"""Distancia de cadenas y heurísticas de SSID sospechosos."""

from __future__ import annotations

_UNSAFE_CHARS = str.maketrans({"'": "'", "`": "'", '"': "'"})


def levenshtein(a: str, b: str) -> int:
    """Distancia de Levenshtein con dos filas (O(min·max) tiempo, O(min) memoria)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) > len(b):
        a, b = b, a
    previous = list(range(len(a) + 1))
    for j, char_b in enumerate(b, start=1):
        current = [j]
        for i, char_a in enumerate(a, start=1):
            cost = 0 if char_a == char_b else 1
            current.append(
                min(
                    previous[i] + 1,      # borrado
                    current[i - 1] + 1,   # inserción
                    previous[i - 1] + cost,  # sustitución
                )
            )
        previous = current
    return previous[-1]


def normalize_ssid(ssid: str) -> str:
    """Quita separadores decorativos pero conserva mayúsculas/minúsculas.

    La diferencia de caja es precisamente una de las señales de suplantación
    (``MiWiFi`` vs ``MiWifi``), así que no la descartamos.
    """
    cleaned = ssid.strip()
    for char in ("_", "-", ".", " "):
        cleaned = cleaned.replace(char, "")
    return cleaned


def similar_ssid(candidate: str, reference: str) -> tuple[bool, int]:
    """¿Es ``candidate`` sospechosamente parecido a ``reference``?

    Devuelve ``(parecido, distancia)``. Detecta tanto erratas/leetspeak como
    redes que solo cambian mayúsculas y minúsculas.
    """
    if not candidate or not reference:
        return False, 999
    a, b = normalize_ssid(candidate), normalize_ssid(reference)
    if a == b:
        return False, 0
    distance = levenshtein(a.lower(), b.lower())
    if distance == 0:
        return True, 0  # solo difieren en la caja: sospechoso
    longest = max(len(a), len(b))
    if longest <= 4:
        threshold = 0
    elif longest <= 8:
        threshold = 1
    else:
        threshold = 2
    return distance <= threshold, distance


def looks_like_hidden(ssid: str) -> bool:
    return not ssid or ssid in {"--", "<hidden>"}
