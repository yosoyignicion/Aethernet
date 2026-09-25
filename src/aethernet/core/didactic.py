"""Módulo didáctico: explicaciones breves y glosario para tooltips.

Contenido estático y honesto. La UI hace hover sobre un término y busca aquí;
el "modo aprendizaje" muestra el cuerpo extendido.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Topic:
    key: str
    title: str
    summary: str
    body: str
    related: tuple[str, ...] = field(default_factory=tuple)


TOPICS: dict[str, Topic] = {
    "beacon": Topic(
        key="beacon",
        title="Beacon",
        summary="Anuncio periódico que emite cada punto de acceso.",
        body=(
            "Un beacon es una trama que el punto de acceso envía varias veces por segundo "
            "para anunciar su SSID, canal y capacidades. Es la base del escaneo pasivo: no "
            "necesitas conectarte para oírlos."
        ),
        related=("ssid", "bssid"),
    ),
    "probe": Topic(
        key="probe",
        title="Probe request",
        summary="Pregunta que lanza un dispositivo buscando redes.",
        body=(
            "Cuando activas el WiFi, tu móvil emite probe requests con nombres de redes que "
            "recuerda. Observarlos revela qué redes busca cada dispositivo. Requiere monitor mode."
        ),
        related=("monitor", "beacon"),
    ),
    "wps": Topic(
        key="wps",
        title="WPS",
        summary="Emparejamiento rápido mediante PIN o botón.",
        body=(
            "WPS permite conectar sin escribir la contraseña. El método de PIN de 8 dígitos es "
            "vulnerable a fuerza bruta. Si no lo usas, desactívalo."
        ),
        related=("wpa2",),
    ),
    "evil_twin": Topic(
        key="evil_twin",
        title="Evil twin",
        summary="AP falso que imita el nombre de tu red.",
        body=(
            "Un gemelo malvado copia tu SSID para que tus dispositivos se conecten a él. Se "
            "delata porque el BSSID no coincide con el de tu router. Nunca te conectes ni "
            "introduzcas contraseñas si lo detectas."
        ),
        related=("ssid", "bssid"),
    ),
    "rssi": Topic(
        key="rssi",
        title="RSSI (dBm)",
        summary="Potencia de señal recibida, en decibelios-milivatio.",
        body=(
            "El RSSI se mide en dBm y es negativo: -30 dBm es excelente y -90 dBm es casi "
            "inutilizable. Cada 3 dB es aproximadamente el doble de potencia. Un valor más "
            "cercano a cero es mejor."
        ),
        related=("beacon",),
    ),
    "channel_overlap": Topic(
        key="channel_overlap",
        title="Solapamiento de canales",
        summary="En 2.4 GHz, canales vecinos se interfieren.",
        body=(
            "Los canales de 2.4 GHz se pisan entre sí. Solo 1, 6 y 11 no se solapan. Si tu "
            "router está en un canal intermedio, pierdes rendimiento aunque la señal sea fuerte."
        ),
        related=("channel",),
    ),
    "monitor": Topic(
        key="monitor",
        title="Monitor mode",
        summary="Modo pasivo que escucha todo el espectro.",
        body=(
            "En monitor mode el adaptador captura todas las tramas del aire, no solo las de tu "
            "red. Habilita detección de deauth, probes y handshakes. No todos los chipsets lo "
            "soportan; la pestaña de configuración te dice si el tuyo puede."
        ),
        related=("probe", "deauth"),
    ),
    "deauth": Topic(
        key="deauth",
        title="Deauth",
        summary="Trama que expulsa a un cliente de la red.",
        body=(
            "Una trama de desautenticación puede forzar la desconexión de un dispositivo. Un "
            "flujo masivo de deauth sugiere un ataque de denegación de servicio contra tu red."
        ),
        related=("monitor",),
    ),
    "wpa2": Topic(
        key="wpa2",
        title="WPA2 / WPA3",
        summary="Estándares de cifrado WiFi.",
        body=(
            "WPA2 (AES-CCMP) es el mínimo recomendable. WPA3 añade protección contra ataques de "
            "diccionario offline con SAE. WEP y WPA están obsoletos y deben evitarse."
        ),
        related=("wps",),
    ),
    "ssid": Topic(
        key="ssid",
        title="SSID",
        summary="Nombre público de la red.",
        body="El SSID es el nombre que ves al buscar redes. No es único y cualquiera puede copiarlo.",
        related=("bssid",),
    ),
    "bssid": Topic(
        key="bssid",
        title="BSSID",
        summary="Dirección MAC del punto de acceso.",
        body=(
            "El BSSID identifica físicamente al AP. Es la huella que permite distinguir tu "
            "router de un gemelo malvado con el mismo SSID."
        ),
        related=("ssid", "oui"),
    ),
    "oui": Topic(
        key="oui",
        title="OUI",
        summary="Prefijo de MAC que identifica al fabricante.",
        body=(
            "Los primeros tres bytes de una MAC son el Organizationally Unique Identifier. "
            "Permiten adivinar el fabricante del AP o del dispositivo."
        ),
        related=("bssid",),
    ),
    "channel": Topic(
        key="channel",
        title="Canal",
        summary="Franja de frecuencia que usa una red.",
        body=(
            "El canal es la porción del espectro donde emite el AP. En 2.4 GHz usa 1/6/11; en "
            "5 GHz hay muchos más canales y menos interferencia."
        ),
        related=("channel_overlap",),
    ),
}

GLOSSARY: dict[str, str] = {key: topic.summary for key, topic in TOPICS.items()}
GLOSSARY.update(
    {
        "dBm": "Unidad de potencia logarítmica; en WiFi siempre negativa.",
        "LAN": "Red de área local; tus dispositivos dentro de casa.",
        "ARP": "Protocolo que traduce IP a MAC dentro de la red local.",
        "OUI": TOPICS["oui"].summary,
    }
)


def topic_for(term: str) -> Topic | None:
    key = term.strip().lower().replace(" ", "_")
    if key in TOPICS:
        return TOPICS[key]
    for topic in TOPICS.values():
        if term.strip().lower() in topic.title.lower():
            return topic
    return None


def glossary_term(term: str) -> str | None:
    return GLOSSARY.get(term.strip()) or GLOSSARY.get(term.strip().lower())


def all_topics() -> list[Topic]:
    return list(TOPICS.values())
