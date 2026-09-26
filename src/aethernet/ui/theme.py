"""Sistema de diseño "AETHERNET": paleta, tipografía y CSS propio.

Los tokens vienen del mockup de Stitch (Tailwind + DESIGN.md) y se exponen como
clases CSS semánticas para no depender de utilidades arbitrarias del runtime.
"""

from __future__ import annotations

from pathlib import Path

from ..models import Severity

# --------------------------------------------------------------------------- #
# Tokens de color (autoritativos: los del mockup)
# --------------------------------------------------------------------------- #
COLORS: dict[str, str] = {
    # Identidad "matrix": verdes vivos sobre negro profundo
    "void": "#030603",              # canvas
    "surface": "#060D08",           # Plane 1
    "surface-1": "#0A1510",         # paneles
    "surface-2": "#0E1E15",         # sub-paneles
    "surface-high": "#152C1D",      # hover / celdas
    "surface-highest": "#1C3A26",
    "border": "#1B3324",
    "border-hover": "#2A5A3B",
    "outline": "#4E8A63",
    "outline-variant": "#25543A",
    "text": "#D8F5E3",
    "text-dim": "#86B89B",
    "text-muted": "#3F6B52",
    "primary": "#7CFFB2",           # acento claro
    "mint": "#00FF9C",              # datos vivos (matrix)
    "cyan": "#39D0FF",              # secundario
    "cyan-solid": "#39D0FF",
    "amber": "#FFB000",             # aviso
    "coral": "#FF3131",             # alerta
    "error": "#FF6B6B",
    "magenta": "#FF2A6D",           # crítico
}

SEVERITY_COLORS: dict[Severity, str] = {
    Severity.INFO: COLORS["cyan"],
    Severity.WARNING: COLORS["amber"],
    Severity.ALERT: COLORS["coral"],
    Severity.CRITICAL: COLORS["magenta"],
}

GRADE_COLORS = {
    "excelente": COLORS["mint"],
    "buena": COLORS["primary"],
    "aceptable": COLORS["amber"],
    "degradada": COLORS["coral"],
    "crítica": COLORS["magenta"],
    "sin datos": COLORS["text-muted"],
}

NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("speed", "Dashboard", "/"),
    ("signal_cellular_alt", "Espectro", "/espectro"),
    ("wifi", "Redes", "/redes"),
    ("memory", "Dispositivos", "/dispositivos"),
    ("warning", "Alertas", "/alertas"),
    ("description", "Informes", "/informes"),
    ("settings", "Ajustes", "/ajustes"),
)

_FONT_DIR = Path(__file__).resolve().parent / "fonts"


def _font_faces() -> str:
    """Reglas ``@font-face`` auto-hospedadas (sin red saliente).

    Los woff2 viven en ``ui/fonts`` y se sirven por ``/ae-fonts``; si faltan
    (por ejemplo, un paquete incompleto) se degrada a las fuentes del sistema.
    """
    try:
        return (_FONT_DIR / "_faces.css").read_text(encoding="utf-8")
    except OSError:
        return ""

_CSS = """
:root {
  --ae-void: #030603; --ae-surface: #060D08; --ae-surface-1: #0A1510;
  --ae-surface-2: #0E1E15; --ae-surface-high: #152C1D; --ae-surface-highest: #1C3A26;
  --ae-border: #1B3324; --ae-border-hover: #2A5A3B; --ae-outline: #4E8A63;
  --ae-text: #D8F5E3; --ae-text-dim: #86B89B; --ae-text-muted: #3F6B52;
  --ae-mint: #00FF9C; --ae-primary: #7CFFB2; --ae-cyan: #39D0FF;
  --ae-amber: #FFB000; --ae-coral: #FF3131;
}
html, body { background: var(--ae-void) !important; color: var(--ae-text); }
body { font-family: 'Inter', system-ui, sans-serif; overscroll-behavior: none; }
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: var(--ae-void); }
::-webkit-scrollbar-thumb { background: var(--ae-surface-high); border-radius: 9999px; }

.ae-mono { font-family: 'JetBrains Mono', ui-monospace, 'DejaVu Sans Mono', monospace; }
.ae-headline { font-family: 'Space Grotesk', 'Inter', system-ui, sans-serif; }
:focus-visible { outline: 2px solid var(--ae-mint); outline-offset: 2px; border-radius: 6px; }
.q-field--outlined .q-field__control:focus-within { box-shadow: inset 0 0 0 1px var(--ae-mint); }
.ae-label {
  font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600;
  letter-spacing: 0.08em; text-transform: uppercase; color: var(--ae-text-dim);
}
.ae-panel {
  background: var(--ae-surface-1); border: 1px solid var(--ae-border);
  border-radius: 12px; padding: 1.25rem;
}
.ae-sub {
  background: var(--ae-surface-2); border: 1px solid var(--ae-border);
  border-radius: 12px;
}
.ae-card {
  background: var(--ae-surface-1); border: 1px solid var(--ae-border);
  border-radius: 12px; padding: 1.25rem; transition: all .18s ease-out;
}
.ae-card:hover { background: var(--ae-surface-2); border-color: var(--ae-border-hover); }
.ae-metric { font-family: 'JetBrains Mono', monospace; font-weight: 700; line-height: 1.1; }
.ae-chip {
  display: inline-flex; align-items: center; gap: .35rem; padding: 3px 9px;
  border-radius: 9999px; border: 1px solid var(--ae-border);
  background: var(--ae-surface-2); font-family: 'JetBrains Mono', monospace;
  font-size: 10px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  color: var(--ae-text-dim); white-space: nowrap;
}
.ae-chip.active { color: var(--ae-mint); border-color: var(--ae-mint); }
.ae-icon { font-family: 'Material Symbols Outlined'; font-weight: normal;
  font-style: normal; line-height: 1; letter-spacing: normal; text-transform: none;
  display: inline-block; white-space: nowrap; direction: ltr;
  -webkit-font-smoothing: antialiased; font-variation-settings: 'FILL' 0, 'wght' 300; }
.ae-divider { height: 1px; background: var(--ae-border); }
@keyframes ae-pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
.ae-pulse { animation: ae-pulse 1.6s ease-in-out infinite; }
@keyframes ae-ping { 0% { transform: scale(1); opacity: .8; } 75%,100% { transform: scale(2.2); opacity: 0; } }
.ae-ping { animation: ae-ping 1.8s cubic-bezier(0,0,.2,1) infinite; }

/* --- animaciones AETHERNET (respetan prefers-reduced-motion) --- */
@keyframes ae-fade-up { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
.ae-fade-up { animation: ae-fade-up .35s cubic-bezier(.4,0,.2,1) both; }
@keyframes ae-glitch {
  0%,100% { transform: none; text-shadow: none; }
  20% { transform: translateX(-1px); text-shadow: 1px 0 var(--ae-coral), -1px 0 var(--ae-cyan); }
  40% { transform: translateX(1px); }
  60% { opacity: .85; }
}
.ae-glitch { animation: ae-glitch 2.4s steps(2,end) infinite; }
@keyframes ae-sweep { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.ae-sweep {
  position: absolute; inset: 0; border-radius: 9999px; pointer-events: none;
  background: conic-gradient(from 0deg, rgba(0,255,156,.30), transparent 55%);
  animation: ae-sweep 4s linear infinite; transform-origin: 50% 50%;
  will-change: transform; contain: paint;
}
@keyframes ae-glow { 0%,100% { box-shadow: 0 0 0 rgba(0,255,156,0); } 50% { box-shadow: 0 0 18px rgba(0,255,156,.35); } }
.ae-glow { animation: ae-glow 2.8s ease-in-out infinite; }
.ae-hover-glow { transition: box-shadow .2s ease, border-color .2s ease; }
.ae-hover-glow:hover { box-shadow: 0 0 0 1px var(--ae-mint), 0 0 18px rgba(0,255,156,.25); border-color: var(--ae-mint) !important; }
@keyframes ae-scanline { from { background-position: 0 0; } to { background-position: 0 100%; } }
.ae-scanline {
  background-image: repeating-linear-gradient(0deg, rgba(0,255,156,.05) 0 1px, transparent 1px 4px);
  animation: ae-scanline 8s linear infinite;
}
@media (prefers-reduced-motion: reduce) {
  .ae-fade-up, .ae-glitch, .ae-sweep, .ae-glow, .ae-scanline, .ae-pulse, .ae-ping { animation: none !important; }
}

/* modo compacto (toggle de la cabecera) */
.ae-compact .q-table tbody td { padding: 2px 8px !important; font-size: 11px !important; }
.ae-compact .ae-panel { padding: .85rem; }
.ae-compact .ae-card { padding: .85rem; min-height: 104px !important; }
.ae-compact .ae-metric { font-size: 1.6rem; }
.ae-compact .ae-label { font-size: 9px; }

.q-table__container, .q-table { background: transparent !important; color: var(--ae-text) !important; }
.q-table thead tr { background: var(--ae-surface) !important; }
.q-table thead th { color: var(--ae-text-dim) !important; font-family: 'JetBrains Mono', monospace !important;
  font-size: 10px !important; letter-spacing: .08em; text-transform: uppercase; border-color: var(--ae-border) !important; }
.q-table tbody td { color: var(--ae-text) !important; border-color: var(--ae-border) !important;
  font-family: 'JetBrains Mono', monospace; font-size: 12px; }
.q-table tbody tr:hover { background: var(--ae-surface-2) !important; }
.q-table__bottom { color: var(--ae-text-dim) !important; }
.ae-selected-row { background: rgba(0, 184, 255, .08) !important; box-shadow: inset 2px 0 0 var(--ae-cyan); }
"""


_head_installed = False


def install_shared() -> None:
    """Inyecta fuentes locales y CSS compartidos una sola vez (seguro en startup)."""
    global _head_installed
    if _head_installed:
        return
    from nicegui import app, ui

    if _FONT_DIR.is_dir():
        app.add_static_files("/ae-fonts", str(_FONT_DIR))
    ui.add_head_html(f"<style>{_font_faces()}{_CSS}</style>", shared=True)
    _head_installed = True


def install() -> None:
    """Inyecta fuentes/CSS (una vez) y aplica los colores de marca del cliente."""
    from nicegui import ui

    install_shared()
    ui.colors(
        primary=COLORS["mint"],
        secondary=COLORS["cyan"],
        accent=COLORS["amber"],
        positive=COLORS["mint"],
        negative=COLORS["coral"],
        warning=COLORS["amber"],
        info=COLORS["cyan"],
        dark=COLORS["surface-2"],
    )


def icon(name: str, *, size: int = 20, color: str | None = None) -> str:
    """HTML de un icono Material Symbols Outlined."""
    style = f"font-size:{size}px;"
    if color:
        style += f"color:{color};"
    return f'<span class="ae-icon" style="{style}">{name}</span>'
