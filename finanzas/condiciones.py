"""Condiciones de financiación: plantilla por producto y fotografía por crédito.

Se guardan como JSON en `productos_credito.condiciones` (plantilla editable) y en
`creditos.condiciones` (copia de la oferta aceptada, que no cambia aunque se
actualice la plantilla). Ninguna tasa ni cargo está fijo en el código: todo
viene de lo que el usuario registra para cada entidad u operación.

Estructura:
{
  "acreedor": {"tipo": "fintech", "nombre": "", "identificacion": "", "financiador": ""},
  "modalidad_legal": "consumo",
  "tasa": {"valor": 0.0, "modalidad": "EA"},          # EA | MV | NAMV
  "sistema": "cuota_fija",                            # cuota_fija | abono_constante
  "periodicidad": "mensual",                          # mensual | quincenal | semanal
  "cargos": [Cargo.como_dict(), ...],
  "cargos_prepago": "se_mantienen",                   # se_mantienen | se_eliminan
  "mora": {"tasa_ea": null, "cobranza": [ReglaCobranza.como_dict(), ...]},  # tasa null = usura vigente
  "orden_pagos": ["cobranza", "mora", "otros", "interes", "capital"],
  "prepago": {"penalidad_pct": 0},
  "vigente_desde": "AAAA-MM-DD"
}
"""

import copy
import json
from datetime import date

from .credito import (ABONO_CONSTANTE, COMPONENTES, CUOTA_FIJA, MODALIDADES_TASA, PERIODOS_ANIO, Cargo,
                      ReglaCobranza, a_ea)

TIPOS_ACREEDOR = {
    "entidad_financiera": "Entidad financiera (banco, cooperativa)",
    "fintech": "Plataforma de crédito (Addi, Sistecrédito…)",
    "almacen_directo": "Almacén – crédito directo",
    "almacen_tercero": "Almacén – financiado por un tercero",
}

ORDENES_PAGO = {
    "cobranza, mora, cargos, intereses, capital": ("cobranza", "mora", "otros", "interes", "capital"),
    "cobranza, mora, intereses, cargos, capital": ("cobranza", "mora", "interes", "otros", "capital"),
    "cobranza, mora, intereses, capital, cargos": ("cobranza", "mora", "interes", "capital", "otros"),
    "intereses, capital, cargos, mora, cobranza": ("interes", "capital", "otros", "mora", "cobranza"),
}

BASE = {
    "acreedor": {"tipo": "entidad_financiera", "nombre": "", "identificacion": "", "financiador": ""},
    "modalidad_legal": "consumo",
    "tasa": {"valor": 0.0, "modalidad": "EA"},
    "sistema": CUOTA_FIJA,
    "periodicidad": "mensual",
    "cargos": [],
    "cargos_prepago": "se_eliminan",
    "mora": {"tasa_ea": None, "cobranza": []},
    "orden_pagos": list(COMPONENTES),
    "prepago": {"penalidad_pct": 0.0},
    "vigente_desde": None,
}


def _mezclar(base: dict, datos: dict) -> dict:
    resultado = copy.deepcopy(base)
    for clave, valor in datos.items():
        if isinstance(valor, dict) and isinstance(resultado.get(clave), dict):
            resultado[clave] = _mezclar(resultado[clave], valor)
        else:
            resultado[clave] = copy.deepcopy(valor)
    return resultado


def por_defecto(tipo_producto: str, tasa_ea: float) -> dict:
    """Condiciones mínimas cuando el producto no tiene plantilla: solo su tasa y sistema."""
    return _mezclar(BASE, {
        "acreedor": {"tipo": "fintech" if tipo_producto == "cupo" else "entidad_financiera"},
        "tasa": {"valor": float(tasa_ea), "modalidad": "EA"},
        "sistema": ABONO_CONSTANTE if tipo_producto == "tarjeta" else CUOTA_FIJA,
        "vigente_desde": date.today().isoformat(),
    })


def cargar(texto: str | None, respaldo: dict) -> dict:
    """Lee un JSON de condiciones; lo que falte se completa con `respaldo`."""
    if not texto:
        return copy.deepcopy(respaldo)
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        return copy.deepcopy(respaldo)
    return _mezclar(respaldo, datos)


def de_credito(fila) -> dict:
    """Condiciones de un crédito: su fotografía, o las deducidas de sus columnas si es anterior."""
    legado = _mezclar(BASE, {"tasa": {"valor": float(fila["tasa_ea"]), "modalidad": "EA"},
                             "sistema": fila["metodo"], "periodicidad": fila["periodicidad"] or "mensual"})
    return cargar(fila["condiciones"], legado)


def validar(cond: dict) -> dict:
    if cond["tasa"]["modalidad"] not in MODALIDADES_TASA:
        raise ValueError("Modalidad de tasa inválida")
    if float(cond["tasa"]["valor"]) < 0:
        raise ValueError("La tasa no puede ser negativa")
    if cond["sistema"] not in (CUOTA_FIJA, ABONO_CONSTANTE):
        raise ValueError("Sistema de amortización inválido")
    if cond["periodicidad"] not in PERIODOS_ANIO:
        raise ValueError("Periodicidad inválida")
    if sorted(cond["orden_pagos"]) != sorted(COMPONENTES):
        raise ValueError("El orden de aplicación de pagos debe incluir todos los componentes una vez")
    for c in cond["cargos"]:
        cargo = Cargo.desde_dict(c)
        if cargo.valor < 0 or cargo.iva_pct < 0:
            raise ValueError(f"El cargo «{cargo.nombre}» no puede ser negativo")
        if cargo.base == "pct_saldo" and cargo.cobro != "por_cuota":
            raise ValueError(f"El cargo «{cargo.nombre}» sobre saldo solo puede cobrarse por cuota")
    return cond


def tasa_ea(cond: dict) -> float:
    return a_ea(float(cond["tasa"]["valor"]), cond["tasa"]["modalidad"])


def cargos(cond: dict) -> list[Cargo]:
    return [Cargo.desde_dict(c) for c in cond.get("cargos", [])]


def reglas_cobranza(cond: dict) -> list[ReglaCobranza]:
    return [ReglaCobranza.desde_dict(r) for r in cond.get("mora", {}).get("cobranza", [])]


def orden(cond: dict) -> tuple[str, ...]:
    return tuple(cond.get("orden_pagos") or COMPONENTES)


def a_texto(cond: dict) -> str:
    return json.dumps(cond, ensure_ascii=False)
