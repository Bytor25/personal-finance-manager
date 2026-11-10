"""Colores y tema. Los colores propios van en pares (claro, oscuro) y se resuelven con `c()`."""

import flet as ft

VERDE = ("#15803d", "#4ade80")       # Efectivo / bien
MORADO = ("#7c3aed", "#a78bfa")      # Tarjeta / deuda
ROJO = ("#b91c1c", "#f87171")
NARANJA = ("#c2410c", "#fb923c")
AMARILLO = ("#a16207", "#facc15")
AZUL = ("#0369a1", "#38bdf8")
GRIS = ft.Colors.ON_SURFACE_VARIANT

COLOR_NIVEL = {"sano": VERDE, "moderado": AMARILLO, "alto": NARANJA, "critico": ROJO}
ICONO_NIVEL = {"sano": "🟢", "moderado": "🟡", "alto": "🟠", "critico": "🔴"}
PALETA_PRODUCTOS = [("#7c3aed", "#a78bfa"), ("#0891b2", "#22d3ee"), ("#db2777", "#f472b6"),
                    ("#ca8a04", "#facc15"), ("#059669", "#34d399"), ("#4f46e5", "#818cf8")]

SEMILLA = "#7c3aed"
MODOS = {"System": ft.ThemeMode.SYSTEM, "Light": ft.ThemeMode.LIGHT, "Dark": ft.ThemeMode.DARK}

_estado = {"oscuro": False}


def c(par) -> str:
    """Color según el modo actual. Acepta un par (claro, oscuro) o un color de Flet."""
    if isinstance(par, tuple):
        return par[1] if _estado["oscuro"] else par[0]
    return par


def aplicar(page: ft.Page, apariencia: str) -> None:
    page.theme = ft.Theme(color_scheme_seed=SEMILLA, use_material3=True, visual_density=ft.VisualDensity.COMFORTABLE)
    page.dark_theme = ft.Theme(color_scheme_seed=SEMILLA, use_material3=True,
                               visual_density=ft.VisualDensity.COMFORTABLE)
    page.theme_mode = MODOS.get(apariencia, ft.ThemeMode.SYSTEM)
    actualizar_brillo(page)


def actualizar_brillo(page: ft.Page) -> None:
    if page.theme_mode == ft.ThemeMode.SYSTEM:
        _estado["oscuro"] = page.platform_brightness == ft.Brightness.DARK
    else:
        _estado["oscuro"] = page.theme_mode == ft.ThemeMode.DARK


def oscuro() -> bool:
    return _estado["oscuro"]
