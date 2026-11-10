"""Definición de formularios independiente de la interfaz gráfica (la usan CustomTkinter y Flet)."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .dinero import a_centavos, a_tasa, formato


@dataclass
class Campo:
    clave: str
    etiqueta: str
    tipo: str = "texto"  # texto | monto | fecha | entero | tasa | opcion | check
    opciones: list[tuple[str, Any]] = field(default_factory=list)
    defecto: Any = None
    ayuda: str = ""
    opcional: bool = False
    visible_si: tuple[str, Any] | None = None


def parsear_fecha(texto: str) -> date:
    texto = texto.strip()
    for formato_fecha in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato_fecha).date()
        except ValueError:
            pass
    raise ValueError(f"Fecha inválida: {texto!r}. Usa AAAA-MM-DD o DD/MM/AAAA.")


def convertir(campo: Campo, crudo: str) -> Any:
    """Convierte el texto escrito en un campo a su valor (centavos, fecha, entero…)."""
    try:
        if campo.tipo == "monto":
            return a_centavos(crudo)
        if campo.tipo == "fecha":
            return parsear_fecha(crudo)
        if campo.tipo == "entero":
            return int(crudo)
        if campo.tipo == "tasa":
            return a_tasa(crudo)
        return crudo
    except ValueError as e:
        raise ValueError(f"«{campo.etiqueta}»: {e}") from None


def visible(campo: Campo, valores: dict[str, Any], visibles: set[str]) -> bool:
    """Si un campo con `visible_si` se muestra, dados los valores crudos y los campos ya visibles."""
    if campo.visible_si is None:
        return True
    clave, esperado = campo.visible_si
    valor = valores.get(clave)
    ok = valor in esperado if isinstance(esperado, tuple) else valor == esperado
    return ok and clave in visibles


def hoy_texto() -> str:
    return date.today().isoformat()


def pesos(centavos: int | None) -> str:
    return "" if centavos is None else formato(centavos)
