"""Colores de MIIA. El rosa del PC (#e94560) se cambia por azul oscuro; el resto del tema se mantiene."""


def rgba(hex_color: str, alpha: float = 1.0):
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0, alpha)


# fondos (los mismos del PC)
BG = "#0a0a0a"          # fondo general y zona de la esfera
PANEL = "#1e1e1e"       # panel principal
HEADER = "#2a2a2a"
SURFACE = "#252525"     # caja del chat y tarjetas
SURFACE2 = "#333333"    # campos de texto

# acento: azul oscuro en lugar de rosa
ACCENT = "#1b4f9c"          # botones principales (antes #e94560)
ACCENT_PRESSED = "#143b78"  # (antes #c73a52)
ACCENT_TEXT = "#4f8fe0"     # títulos y bordes sobre fondo oscuro (legible)

BLUE = "#0f3460"            # botones secundarios (los mismos del PC)
BLUE_PRESSED = "#1a4a7a"
NEUTRAL = "#333333"
NEUTRAL_PRESSED = "#555555"
DANGER = "#5a2330"
DANGER_PRESSED = "#7a2f40"

TEXT = "#e0e0e0"
TEXT_DIM = "#888888"
TEXT_FAINT = "#666666"
INFO = "#8fb8cc"
OK = "#5fd38d"
WARN = "#e9a545"
ERR = "#ff6b81"             # errores (antes se usaba el rosa; un rojo claro se lee mejor)

# mensajes
BUBBLE_USER = "#1b4f9c"
BUBBLE_MIIA = "#252525"

# esfera (iguales al PC: cian -> negro, como el ícono)
ORB_LAYERS = [
    (1.55, "#03070c"), (1.40, "#06111c"),
    (1.29, "#082238"), (1.20, "#0b3857"),
    (1.135, "#0d5b82"), (1.075, "#1688b8"),
    (1.025, "#66d9ff"), (0.985, "#246c8d"),
    (0.925, "#0b2d40"), (0.855, "#031018"),
]
