"""Montos en COP: se guardan como enteros en centavos y se muestran con formato colombiano."""

import re

_MILES = re.compile(r"^\d{1,3}(\.\d{3})+$")


def a_centavos(texto: str | int | float) -> int:
    """Convierte lo que escribe el usuario a centavos.

    Acepta formato colombiano ("1.750.905", "469.027,32"), números simples
    ("1750905", "1750905.5") y el signo "$".
    """
    if isinstance(texto, int):
        return texto * 100
    if isinstance(texto, float):
        return round(texto * 100)
    t = texto.strip().replace("$", "").replace(" ", "").replace("'", ".")
    if not t:
        raise ValueError("Monto vacío")
    negativo = t.startswith("-")
    t = t.lstrip("+-")
    if "," in t:
        # La coma es el separador decimal; los puntos son de miles.
        t = t.replace(".", "").replace(",", ".")
    elif _MILES.match(t):
        t = t.replace(".", "")
    try:
        valor = round(float(t) * 100)
    except ValueError:
        raise ValueError(f"Monto inválido: {texto!r}") from None
    return -valor if negativo else valor


def formato(centavos: int | float, decimales: bool = False, signo: bool = True) -> str:
    """Formatea centavos como "$1.750.905" (o "$469.027,32" con decimales)."""
    negativo = centavos < 0
    centavos = abs(round(centavos))
    if decimales:
        entero, resto = divmod(centavos, 100)
        texto = f"{entero:,}".replace(",", ".") + f",{resto:02d}"
    else:
        texto = f"{round(centavos / 100):,}".replace(",", ".")
    texto = ("$" if signo else "") + texto
    return "-" + texto if negativo else texto


def porcentaje(valor: float, decimales: int = 1) -> str:
    """Formatea 0.447 como "44,7 %"."""
    return f"{valor * 100:.{decimales}f}".replace(".", ",") + " %"


def a_tasa(texto: str | float) -> float:
    """Convierte "30", "30 %" o "2,21" a porcentaje numérico (30.0, 2.21)."""
    if isinstance(texto, (int, float)):
        return float(texto)
    t = texto.strip().replace("%", "").replace(" ", "").replace(",", ".")
    if not t:
        raise ValueError("Tasa vacía")
    return float(t)


def tasa(valor: float, decimales: int = 2) -> str:
    """Formatea 28.5 como "28,50"."""
    return f"{valor:.{decimales}f}".replace(".", ",")
