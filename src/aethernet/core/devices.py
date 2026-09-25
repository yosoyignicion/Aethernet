"""Identificación de dispositivos LAN: tipo reconocible a partir de pistas.

Heurística **explicable**: fabricante (OUI), hostname y pistas de modelo. Nunca
afirma más de lo que las pistas permiten; si no reconoce, dice "desconocido".
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import LanDevice

# (subcadena en vendor/hostname, etiqueta, icono, confianza)
_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("raspberry", "SBC / IoT", "memory", "alta"),
    ("espressif", "IoT", "sensors", "alta"),
    ("sonoff", "IoT (domótica)", "sensors", "alta"),
    ("tuya", "IoT (domótica)", "sensors", "media"),
    ("shelly", "IoT (domótica)", "sensors", "alta"),
    ("apple", "Apple", "phone_iphone", "alta"),
    ("iphone", "Apple iPhone", "phone_iphone", "media"),
    ("ipad", "Apple iPad", "tablet_mac", "media"),
    ("macbook", "Apple Mac", "laptop_mac", "media"),
    ("samsung", "Samsung", "smartphone", "media"),
    ("xiaomi", "Xiaomi", "smartphone", "media"),
    ("redmi", "Xiaomi Redmi", "smartphone", "media"),
    ("huawei", "Huawei", "smartphone", "media"),
    ("oneplus", "OnePlus", "smartphone", "media"),
    ("sony", "Sony", "tv", "media"),
    ("playstation", "PlayStation", "sports_esports", "media"),
    ("lg electronics", "LG", "tv", "media"),
    ("philips", "Philips (Hue/TV)", "lightbulb", "media"),
    ("intel", "PC", "laptop_mac", "baja"),
    ("dell", "PC Dell", "laptop_chromebook", "media"),
    ("hewlett", "PC HP", "laptop_mac", "media"),
    ("lenovo", "PC Lenovo", "laptop_mac", "media"),
    ("asustek", "PC Asus", "laptop_mac", "media"),
    ("vmware", "Máquina virtual", "developer_board", "alta"),
    ("qemu", "Máquina virtual", "developer_board", "alta"),
    ("proxmox", "Hipervisor", "dns", "media"),
    ("docker", "Contenedor", "view_in_ar", "media"),
    ("synology", "NAS", "storage", "alta"),
    ("qnap", "NAS", "storage", "alta"),
    ("printer", "Impresora", "print", "media"),
    ("hp inc", "Impresora HP", "print", "media"),
    ("brother", "Impresora Brother", "print", "media"),
    ("tp-link", "Red / router", "router", "media"),
    ("netgear", "Red / router", "router", "media"),
    ("ubiquiti", "Red / AP", "router", "media"),
    ("mikrotik", "Red / router", "router", "media"),
    ("routerboard", "Red / router", "router", "media"),
    ("chromecast", "Chromecast", "cast", "media"),
    ("roku", "Roku", "tv", "media"),
    ("amazon", "Amazon (Echo/Fire)", "speaker", "media"),
    ("google", "Google", "cast", "baja"),
    ("nintendo", "Nintendo", "sports_esports", "media"),
)


@dataclass(frozen=True, slots=True)
class DeviceKind:
    label: str
    icon: str
    confidence: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"label": self.label, "icon": self.icon, "confidence": self.confidence, "reason": self.reason}


def classify_device(device: LanDevice) -> DeviceKind:
    """Tipo reconocible del dispositivo a partir de las pistas disponibles."""
    if device.is_gateway:
        return DeviceKind("Router / gateway", "router", "alta", "es la puerta de enlace")
    if device.is_randomized_mac:
        return DeviceKind(
            "MAC aleatoria", "shuffle", "media", "MAC localmente administrada (privacidad o contenedor)"
        )
    haystack = f"{device.vendor or ''} {device.hostname or ''} {device.alias or ''}".lower()
    for needle, label, icon, confidence in _RULES:
        if needle in haystack:
            return DeviceKind(label, icon, confidence, f"coincide '{needle}'")
    if device.vendor:
        return DeviceKind(device.vendor, "devices_other", "baja", "solo fabricante OUI")
    return DeviceKind("Desconocido", "device_unknown", "nula", "sin pistas")
