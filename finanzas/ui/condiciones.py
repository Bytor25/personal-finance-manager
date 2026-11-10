"""Campos de formulario para las condiciones de financiación (plantilla del producto u oferta de una compra)."""

from datetime import date

from .. import condiciones as cond_mod
from ..credito import ABONO_CONSTANTE, CUOTA_FIJA
from ..dinero import formato
from ..campos import Campo

MODALIDADES = [("E.A. (efectiva anual)", "EA"), ("M.V. (mes vencido)", "MV"), ("N.A.M.V. (nominal anual)", "NAMV")]
SISTEMAS = [("Cuota fija (la mayoría de créditos)", CUOTA_FIJA),
            ("Capital fijo + intereses (cuota que baja)", ABONO_CONSTANTE)]
PERIODICIDADES = [("Mensual", "mensual"), ("Quincenal", "quincenal"), ("Semanal", "semanal")]
COBROS = [("Repartido en las cuotas", "prorrateado"), ("Al inicio (se paga al comprar)", "inicial"),
          ("En cada cuota (el % se cobra cada vez)", "por_cuota")]
MODALIDADES_LEGALES = [("Consumo y ordinario", "consumo"), ("Consumo de bajo monto", "bajo_monto"),
                       ("Microcrédito", "microcredito"), ("Otra", "otra")]

# Cargos que maneja el formulario (otros cargos guardados en el JSON se conservan tal cual).
FIJOS = ("Seguro", "Seguro sobre saldo", "Administración", "Estudio de crédito", "Otros cargos por cuota",
         "Otros cargos iniciales")


def _num(valor: float) -> str:
    return f"{valor:g}".replace(".", ",")


def _pesos(centavos) -> str | None:
    return formato(int(centavos), signo=False) if centavos else None


def campos(cond: dict, visible_si: tuple | None = None) -> list[Campo]:
    """Campos con los valores de `cond`. Con `visible_si`, solo se muestran si se cumple esa condición."""
    cargos = {c["nombre"]: c for c in cond.get("cargos", [])}
    fianza = next((c for c in cond.get("cargos", []) if c.get("tipo") in ("fianza", "aval")), None)
    cobranza = (cond.get("mora", {}).get("cobranza") or [{}])[0]
    acreedor = cond.get("acreedor", {})
    orden = next((k for k, v in cond_mod.ORDENES_PAGO.items() if list(v) == list(cond["orden_pagos"])),
                 next(iter(cond_mod.ORDENES_PAGO)))

    def c(*args, **kwargs) -> Campo:
        kwargs.setdefault("visible_si", visible_si)
        return Campo(*args, **kwargs)

    return [
        c("c_acreedor", "Tipo de acreedor", "opcion", [(v, k) for k, v in cond_mod.TIPOS_ACREEDOR.items()],
          defecto=acreedor.get("tipo")),
        c("c_nombre", "Acreedor / almacén", opcional=True, defecto=acreedor.get("nombre") or None),
        c("c_identificacion", "NIT o identificación del acreedor", opcional=True,
          defecto=acreedor.get("identificacion") or None),
        c("c_financiador", "Entidad que financia (si el almacén usa un tercero)", opcional=True,
          defecto=acreedor.get("financiador") or None),
        c("c_tasa", "Tasa de interés (%)", "tasa", defecto=_num(float(cond["tasa"]["valor"])),
          ayuda="La tasa remuneratoria que te ofrecieron y aceptaste. 0 si es sin intereses."),
        c("c_modalidad", "La tasa está expresada en", "opcion", MODALIDADES, defecto=cond["tasa"]["modalidad"]),
        c("c_sistema", "Sistema de amortización", "opcion", SISTEMAS, defecto=cond["sistema"]),
        c("c_periodicidad", "Periodicidad de las cuotas", "opcion", PERIODICIDADES, defecto=cond["periodicidad"]),
        c("c_fianza_nombre", "Nombre de la fianza / aval", opcional=True,
          defecto=fianza["nombre"] if fianza else None, ayuda="Ej.: Fianza FGA, Aval. Vacío si no tiene."),
        c("c_fianza_pct", "Fianza / aval (% del capital financiado)", "tasa", opcional=True,
          defecto=_num(fianza["valor"]) if fianza else None),
        c("c_fianza_iva", "IVA de la fianza / aval (%)", "tasa", opcional=True,
          defecto=_num(fianza["iva_pct"]) if fianza and fianza.get("iva_pct") else None),
        c("c_fianza_cobro", "¿Cómo se cobra la fianza / aval?", "opcion", COBROS,
          defecto=fianza["cobro"] if fianza else "prorrateado"),
        c("c_fianza_interes", "Según mi contrato, la fianza / aval cuenta como interés", "check",
          defecto=bool(fianza and fianza.get("es_interes")),
          ayuda="Solo para comparar con la tasa de usura. La app no decide la naturaleza legal de un cobro."),
        c("c_seguro", "Seguro por cuota ($, con IVA)", "monto", opcional=True,
          defecto=_pesos(cargos.get("Seguro", {}).get("valor"))),
        c("c_seguro_saldo", "Seguro sobre saldo (% del saldo en cada cuota)", "tasa", opcional=True,
          defecto=_num(cargos["Seguro sobre saldo"]["valor"]) if "Seguro sobre saldo" in cargos else None),
        c("c_admin", "Cuota de administración por cuota ($)", "monto", opcional=True,
          defecto=_pesos(cargos.get("Administración", {}).get("valor"))),
        c("c_estudio", "Estudio de crédito ($, se paga al inicio)", "monto", opcional=True,
          defecto=_pesos(cargos.get("Estudio de crédito", {}).get("valor"))),
        c("c_otros_cuota", "Otros cargos por cuota ($)", "monto", opcional=True,
          defecto=_pesos(cargos.get("Otros cargos por cuota", {}).get("valor"))),
        c("c_otros_inicial", "Otros cargos al inicio ($)", "monto", opcional=True,
          defecto=_pesos(cargos.get("Otros cargos iniciales", {}).get("valor"))),
        c("c_mantener", "Los cargos se siguen debiendo si pago antes (prepago)", "check",
          defecto=cond["cargos_prepago"] == "se_mantienen"),
        c("c_prepago_causado", "Si pago antes del vencimiento, solo se cobra el interés de los días corridos",
          "check", defecto=cond["prepago"].get("interes") == "causado",
          ayuda="Márcalo si tu contrato o la plataforma liquida así la cancelación anticipada. Si no, se cobra el "
                "interés del periodo completo."),
        c("c_penalidad", "Penalidad por pago anticipado (%)", "tasa", opcional=True,
          defecto=_num(cond["prepago"].get("penalidad_pct", 0)) if cond["prepago"].get("penalidad_pct") else None,
          ayuda="Normalmente 0: en créditos de consumo el prepago suele ser sin penalidad. Revisa tu contrato."),
        c("c_mora_tasa", "Tasa de mora pactada (% E.A.)", "tasa", opcional=True,
          defecto=_num(cond["mora"]["tasa_ea"]) if cond["mora"].get("tasa_ea") is not None else None,
          ayuda="Vacío = la tasa de usura del periodo (Configuración → Tasas legales). Nunca se supera la usura."),
        c("c_legal", "Modalidad de crédito (para la usura)", "opcion", MODALIDADES_LEGALES,
          defecto=cond.get("modalidad_legal", "consumo")),
        c("c_cob_dias", "Gastos de cobranza desde el día de mora", "entero", opcional=True,
          defecto=cobranza.get("desde_dias")),
        c("c_cob_valor", "Gastos de cobranza: valor fijo ($)", "monto", opcional=True,
          defecto=_pesos(cobranza["valor"]) if cobranza.get("base") == "fijo" else None),
        c("c_cob_pct", "Gastos de cobranza: % de lo vencido", "tasa", opcional=True,
          defecto=_num(cobranza["valor"]) if cobranza.get("base") == "pct_vencido" else None),
        c("c_cob_iva", "IVA de los gastos de cobranza (%)", "tasa", opcional=True,
          defecto=_num(cobranza["iva_pct"]) if cobranza.get("iva_pct") else None),
        c("c_cob_mensual", "La cobranza se cobra cada 30 días de mora (si no, una vez)", "check",
          defecto=cobranza.get("frecuencia") == "mensual"),
        c("c_orden", "Orden en que se aplican los pagos", "opcion", [(k, k) for k in cond_mod.ORDENES_PAGO],
          defecto=orden, ayuda="Según tu contrato. «cargos» = fianza, aval, seguros y otros."),
        c("c_vigente", "Condiciones vigentes desde", "fecha", opcional=True,
          defecto=cond.get("vigente_desde") or date.today().isoformat()),
    ]


def leer(v: dict, base: dict) -> dict:
    """Arma las condiciones a partir de los valores del formulario, conservando cargos no editables aquí."""
    cond = cond_mod.cargar(cond_mod.a_texto(base), base)
    cond["acreedor"] = {"tipo": v["c_acreedor"], "nombre": v["c_nombre"] or "",
                        "identificacion": v["c_identificacion"] or "", "financiador": v["c_financiador"] or ""}
    cond["tasa"] = {"valor": v["c_tasa"], "modalidad": v["c_modalidad"]}
    cond["sistema"] = v["c_sistema"]
    cond["periodicidad"] = v["c_periodicidad"]
    cond["modalidad_legal"] = v["c_legal"]
    otros = [c for c in base.get("cargos", []) if c["nombre"] not in FIJOS and c.get("tipo") not in ("fianza", "aval")]
    cargos = []
    if v["c_fianza_pct"]:
        nombre = v["c_fianza_nombre"] or "Fianza / aval"
        cargos.append({"nombre": nombre, "tipo": "aval" if "aval" in nombre.lower() else "fianza",
                       "base": "pct_capital", "valor": v["c_fianza_pct"], "iva_pct": v["c_fianza_iva"] or 0,
                       "cobro": v["c_fianza_cobro"], "es_interes": bool(v["c_fianza_interes"])})
    for clave, nombre, tipo, base_cargo, cobro in (
            ("c_seguro", "Seguro", "seguro", "fijo", "por_cuota"),
            ("c_seguro_saldo", "Seguro sobre saldo", "seguro", "pct_saldo", "por_cuota"),
            ("c_admin", "Administración", "administracion", "fijo", "por_cuota"),
            ("c_estudio", "Estudio de crédito", "estudio", "fijo", "inicial"),
            ("c_otros_cuota", "Otros cargos por cuota", "otro", "fijo", "por_cuota"),
            ("c_otros_inicial", "Otros cargos iniciales", "otro", "fijo", "inicial")):
        if v[clave]:
            cargos.append({"nombre": nombre, "tipo": tipo, "base": base_cargo, "valor": v[clave], "cobro": cobro})
    cond["cargos"] = cargos + otros
    cond["cargos_prepago"] = "se_mantienen" if v["c_mantener"] else "se_eliminan"
    cond["prepago"] = {"penalidad_pct": v["c_penalidad"] or 0,
                       "interes": "causado" if v["c_prepago_causado"] else "periodo"}
    cobranza = []
    if v["c_cob_valor"] or v["c_cob_pct"]:
        cobranza.append({"desde_dias": v["c_cob_dias"] or 1, "base": "fijo" if v["c_cob_valor"] else "pct_vencido",
                         "valor": v["c_cob_valor"] or v["c_cob_pct"], "iva_pct": v["c_cob_iva"] or 0,
                         "frecuencia": "mensual" if v["c_cob_mensual"] else "unica"})
    cond["mora"] = {"tasa_ea": v["c_mora_tasa"], "cobranza": cobranza}
    cond["orden_pagos"] = list(cond_mod.ORDENES_PAGO[v["c_orden"]])
    cond["vigente_desde"] = v["c_vigente"].isoformat() if v["c_vigente"] else date.today().isoformat()
    return cond_mod.validar(cond)
