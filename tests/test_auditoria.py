"""Pruebas de las correcciones de la auditoría (fechas, mora, extracto, prepago, cargos, cupo, saldos).

Los valores esperados se calculan aquí con las fórmulas (Decimal), no con el código probado.
"""

import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import pytest

from finanzas import credito, db
from finanzas.credito import CUOTA_FIJA
from finanzas.repositorio import CupoInsuficiente, Repositorio


def pesos(valor) -> int:
    return int((Decimal(valor) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)) * 100


@pytest.fixture
def repo():
    return Repositorio(db.conectar(":memory:"))


def cupo(repo, tasa=0.0, cupo_=0):
    return repo.guardar_producto(None, "Cupo", "", "cupo", cupo_, tasa, 1, 1, 0, False)


def credito_id(repo, producto_id):
    return repo.creditos(producto_id, solo_activos=False)[0]["credito"]["id"]


def fechas(repo, cid):
    return [c["fecha"] for c in repo.cronograma_credito(cid) if c["estado"] != "reemplazada"]


def con_usura(repo, usura=27.0):
    repo.guardar_tasa_legal(None, "consumo", date(2026, 1, 1), date(2026, 12, 31), usura)


# ---------------------------------------------------------------- E1: fechas de fin de mes

def test_cupo_comprado_el_31_conserva_fin_de_mes(repo):
    p = cupo(repo)
    repo.registrar_compra(date(2026, 1, 31), "x", None, 30000000, "tarjeta", p, 3)
    assert fechas(repo, credito_id(repo, p)) == ["2026-02-28", "2026-03-31", "2026-04-30"]


def test_tarjeta_y_prestamo_con_dia_de_pago_31_y_30(repo):
    t = repo.guardar_producto(None, "T", "", "tarjeta", 0, 30, 15, 31, 0, False)
    repo.registrar_compra(date(2026, 1, 20), "x", None, 30000000, "tarjeta", t, 3)
    assert fechas(repo, credito_id(repo, t)) == ["2026-02-28", "2026-03-31", "2026-04-30"]
    pr = repo.guardar_producto(None, "P", "", "prestamo", 0, 30, 1, 30, 0, False)
    cid = repo.registrar_deuda_existente(pr, "x", date(2026, 2, 28), 30000000, 3, 0, 30, CUOTA_FIJA)
    assert fechas(repo, cid) == ["2026-02-28", "2026-03-30", "2026-04-30"]


def test_bisiesto_y_abono_conservan_el_dia_ancla(repo):
    p = cupo(repo, 30)
    repo.registrar_compra(date(2028, 1, 31), "x", None, 60000000, "tarjeta", p, 6)
    cid = credito_id(repo, p)
    assert fechas(repo, cid)[:2] == ["2028-02-29", "2028-03-31"]
    q = repo.cronograma_credito(cid)[0]
    repo.registrar_pago(p, date(2028, 2, 29), q["capital"] + q["interes"] + 10000000)
    pendientes = [c["fecha"] for c in repo.cronograma_credito(cid) if c["estado"] == "pendiente"]
    assert pendientes[:2] == ["2028-03-31", "2028-04-30"]


def test_pagar_en_la_fecha_real_no_genera_mora(repo):
    p = cupo(repo, 25)
    con_usura(repo)
    repo.registrar_compra(date(2026, 1, 31), "x", None, 30000000, "tarjeta", p, 3)
    cuotas = repo.cronograma_credito(credito_id(repo, p))
    repo.registrar_pago(p, date(2026, 2, 28), cuotas[0]["capital"] + cuotas[0]["interes"])
    r = repo.registrar_pago(p, date(2026, 3, 31), cuotas[1]["capital"] + cuotas[1]["interes"])
    assert r["mora_liquidada"] == 0 and r["tipo"] == "minimo"


def test_oferta_y_refinanciacion_usan_el_dia_ancla():
    o = credito.Oferta("x", 30000000, num_cuotas=3, fecha=date(2026, 1, 31))
    assert [c.fecha for c in o.simular()[0]] == [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]
    r = credito.analizar_refinanciacion(1000000, 0, 3, date(2026, 2, 28), tasa_ea=20, dia=31)
    assert [c.fecha for c in r.cronograma] == [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


# ---------------------------------------------------------------- E2: cobranza única por episodio

def test_cobranza_unica_no_se_repite_en_el_mismo_atraso(repo):
    p = cupo(repo, 25)
    con_usura(repo)
    c = repo.condiciones_producto(p)
    c["mora"] = {"tasa_ea": None, "cobranza": [{"desde_dias": 1, "base": "fijo", "valor": 1000000, "iva_pct": 0,
                                                "frecuencia": "unica"}]}
    repo.registrar_compra(date(2026, 1, 10), "x", None, 30000000, "tarjeta", p, 3, condiciones=c)
    cid = credito_id(repo, p)
    repo.liquidar_mora(date(2026, 3, 20))
    q = repo.cronograma_credito(cid)[0]
    pendiente = sum(q[k] for k in ("capital", "interes", "otros", "mora", "cobranza")) - q["pagado"]
    repo.registrar_pago(p, date(2026, 3, 20), pendiente)
    repo.liquidar_mora(date(2026, 3, 25))
    assert repo._valor("SELECT SUM(monto) FROM cargos_mora WHERE tipo = 'cobranza'") == 1000000


def test_cobranza_se_cobra_en_un_atraso_nuevo(repo):
    p = cupo(repo, 25)
    con_usura(repo)
    c = repo.condiciones_producto(p)
    c["mora"] = {"tasa_ea": None, "cobranza": [{"desde_dias": 1, "base": "fijo", "valor": 1000000, "iva_pct": 0,
                                                "frecuencia": "unica"}]}
    repo.registrar_compra(date(2026, 1, 10), "x", None, 30000000, "tarjeta", p, 3, condiciones=c)
    cid = credito_id(repo, p)
    repo.liquidar_mora(date(2026, 2, 15))
    q = repo.cronograma_credito(cid)[0]
    repo.registrar_pago(p, date(2026, 2, 15), sum(q[k] for k in ("capital", "interes", "mora", "cobranza")))
    repo.liquidar_mora(date(2026, 3, 15))  # La cuota 2 venció el 10-mar, después de ponerse al día.
    assert repo._valor("SELECT SUM(monto) FROM cargos_mora WHERE tipo = 'cobranza'") == 2000000


# ---------------------------------------------------------------- E3: extracto frente a cronograma

def _tarjeta_con_extracto(repo, menos_interes=1500000):
    t = repo.guardar_producto(None, "Nu", "", "tarjeta", 500000000, 30, 5, 20, 0, False)
    con_usura(repo)
    repo.registrar_compra(date(2026, 1, 3), "x", None, 120000000, "tarjeta", t, 12)
    q = repo.cronograma_credito(credito_id(repo, t))[0]
    ext = repo.registrar_extracto(t, date(2026, 1, 5), date(2026, 1, 20), q["capital"], q["interes"] - menos_interes,
                                  deuda_restante=110000000)
    return t, q, ext


def test_pagar_el_minimo_del_extracto_deja_la_cuota_al_dia(repo):
    t, q, _ = _tarjeta_con_extracto(repo)
    minimo = repo.proximo_pago_producto(t, date(2026, 1, 10))["minimo"]
    assert minimo == q["capital"] + q["interes"] - 1500000
    r = repo.registrar_pago(t, date(2026, 1, 18), minimo)
    assert r["tipo"] == "minimo" and r["segun_extracto"]
    assert repo.estado_mora(date(2026, 2, 10)) == []
    assert repo.cronograma_credito(credito_id(repo, t))[0]["estado"] == "pagada"


def test_eliminar_extracto_restaura_el_interes(repo):
    t, q, ext = _tarjeta_con_extracto(repo)
    assert repo.cronograma_credito(credito_id(repo, t))[0]["interes"] == q["interes"] - 1500000
    repo.eliminar_extracto(ext)
    assert repo.cronograma_credito(credito_id(repo, t))[0]["interes"] == q["interes"]


def test_no_se_elimina_extracto_con_pagos_sobre_su_interes(repo):
    t, q, ext = _tarjeta_con_extracto(repo, menos_interes=-500000)  # El banco cobró más interés.
    repo.registrar_pago(t, date(2026, 1, 18), repo.proximo_pago_producto(t, date(2026, 1, 10))["minimo"])
    with pytest.raises(ValueError):
        repo.eliminar_extracto(ext)


# ---------------------------------------------------------------- E4: interés causado al cancelar

def test_cancelacion_con_interes_causado_por_dias(repo):
    p = cupo(repo, 30)
    c = repo.condiciones_producto(p)
    c["prepago"] = {"penalidad_pct": 0, "interes": "causado"}
    repo.registrar_compra(date(2026, 1, 10), "x", None, 120000000, "tarjeta", p, 12, condiciones=c)
    cid = credito_id(repo, p)
    mv = Decimal(1.3) ** (Decimal(1) / 12) - 1
    causado = pesos(Decimal(120000000) * ((1 + mv) ** (Decimal(10) / 31) - 1))
    total = repo.proximo_pago_producto(p, date(2026, 1, 20))["total"]
    assert total == 120000000 + causado
    pago = repo.registrar_pago(p, date(2026, 1, 20), total)
    assert repo.creditos(p, solo_activos=False)[0]["credito"]["estado"] == "pagado"
    assert pago["sin_aplicar"] == 0
    original = repo.cronograma_credito(cid)[0]["interes"]
    repo.eliminar_pago(pago["pago_id"])
    restaurada = repo.cronograma_credito(cid)[0]
    assert restaurada["interes"] > original and restaurada["estado"] == "pendiente"


def test_sin_la_opcion_se_cobra_el_periodo_completo(repo):
    p = cupo(repo, 30)
    repo.registrar_compra(date(2026, 1, 10), "x", None, 120000000, "tarjeta", p, 12)
    q = repo.cronograma_credito(credito_id(repo, p))[0]
    assert repo.proximo_pago_producto(p, date(2026, 1, 20))["total"] == 120000000 + q["interes"]


def test_interes_causado():
    assert credito.interes_causado(100000000, 0.02, 15, 30) == pesos(Decimal(100000000) * (Decimal("1.02") ** Decimal("0.5") - 1))
    assert credito.interes_causado(100000000, 0.02, 40, 30) == pesos(Decimal(100000000) * Decimal("0.02"))
    assert credito.interes_causado(100000000, 0.02, 0, 30) == 0


# ---------------------------------------------------------------- E5/E6: cargos después de un abono

def test_seguro_sobre_saldo_se_recalcula_tras_abono(repo):
    p = cupo(repo, 30)
    c = repo.condiciones_producto(p)
    c["cargos"] = [{"nombre": "Seguro", "tipo": "seguro", "base": "pct_saldo", "valor": 0.1, "cobro": "por_cuota"}]
    repo.registrar_compra(date(2026, 1, 10), "x", None, 120000000, "tarjeta", p, 12, condiciones=c)
    cid = credito_id(repo, p)
    q = repo.cronograma_credito(cid)[0]
    repo.registrar_pago(p, date(2026, 2, 10), q["capital"] + q["interes"] + q["otros"] + 60000000, reducir="cuota")
    for cu in [x for x in repo.cronograma_credito(cid) if x["estado"] == "pendiente"]:
        saldo = repo._valor("SELECT SUM(capital) FROM cuotas WHERE credito_id = ? AND estado = 'pendiente' "
                            "AND fecha >= ?", (cid, cu["fecha"]))
        assert cu["otros"] == pesos(Decimal(saldo) * Decimal("0.001"))


@pytest.mark.parametrize("reducir", ["cuota", "plazo"])
def test_fianza_repartida_que_se_elimina_baja_en_proporcion_al_capital(repo, reducir):
    p = cupo(repo, 0)
    c = repo.condiciones_producto(p)
    c["cargos"] = [{"nombre": "Fianza", "tipo": "fianza", "base": "pct_capital", "valor": 10, "iva_pct": 0,
                    "cobro": "prorrateado"}]
    c["cargos_prepago"] = "se_eliminan"
    repo.registrar_compra(date(2026, 1, 10), "x", None, 60000000, "tarjeta", p, 6, condiciones=c)
    cid = credito_id(repo, p)
    q = repo.cronograma_credito(cid)[0]
    repo.registrar_pago(p, date(2026, 2, 10), q["capital"] + q["otros"] + 30000000, reducir=reducir)
    vigentes = [x for x in repo.cronograma_credito(cid) if x["estado"] != "reemplazada"]
    # Cuota 1: $10.000 de fianza. Las 5 restantes debían $50.000 sobre $500.000 de capital; quedan $200.000.
    assert sum(x["otros"] for x in vigentes) == 1000000 + pesos(Decimal(5000000) * 20000000 / 50000000)


def test_repartir_nunca_deja_la_ultima_negativa():
    for total in (100, 700, 1500, 2300, 99900):
        for n in (1, 3, 4, 7, 24, 36):
            partes = credito.repartir(total, n)
            assert sum(partes) == total and min(partes) >= 0


# ---------------------------------------------------------------- E8: cupo

def test_compra_que_supera_el_cupo(repo):
    p = cupo(repo, 0, 100000000)
    repo.registrar_compra(date(2026, 1, 3), "a", None, 90000000, "tarjeta", p, 3)
    with pytest.raises(CupoInsuficiente):
        repo.registrar_compra(date(2026, 1, 4), "b", None, 50000000, "tarjeta", p, 3)
    repo.registrar_compra(date(2026, 1, 4), "b", None, 50000000, "tarjeta", p, 3, permitir_sobrecupo=True)
    d = [x for x in repo.deuda_productos(date(2026, 1, 5)) if x["producto"]["id"] == p][0]
    assert d["disponible"] == 0 and d["uso_cupo"] == pytest.approx(1.4)


def test_cuota_inicial_no_consume_cupo(repo):
    p = cupo(repo, 0, 100000000)
    repo.registrar_compra(date(2026, 1, 3), "a", None, 120000000, "tarjeta", p, 3, cuota_inicial=30000000)
    d = [x for x in repo.deuda_productos(date(2026, 1, 5)) if x["producto"]["id"] == p][0]
    assert d["disponible"] == 10000000


# ---------------------------------------------------------------- E9: saldo a favor

def test_pago_sin_deuda_queda_como_saldo_a_favor_y_se_usa(repo):
    p = cupo(repo, 0)
    repo.registrar_compra(date(2026, 1, 10), "x", None, 10000000, "tarjeta", p, 1)
    repo.registrar_pago(p, date(2026, 2, 10), 15000000)
    assert repo.saldo_a_favor(p) == 5000000
    repo.registrar_compra(date(2026, 2, 15), "y", None, 30000000, "tarjeta", p, 3)
    assert repo.saldo_a_favor(p) == 0
    assert repo.deuda_total() == 25000000
    assert repo.resumen_mes("2026-02")["pagos_credito"] == 15000000  # El saldo a favor no sale dos veces.


def test_devolucion_mayor_que_la_deuda(repo):
    p = cupo(repo, 0)
    repo.registrar_compra(date(2026, 1, 10), "x", None, 30000000, "tarjeta", p, 3)
    r = repo.registrar_devolucion(credito_id(repo, p), date(2026, 1, 11), 40000000)
    assert r["saldo_a_favor"] == 10000000 and repo.saldo_a_favor(p) == 10000000
    assert repo.resumen_mes("2026-01")["compras_tarjeta"] == 0


# ---------------------------------------------------------------- E10: costo tras devolución

def test_costo_despues_de_devolucion_parcial(repo):
    p = cupo(repo, 0)
    repo.registrar_compra(date(2026, 1, 10), "x", None, 60000000, "tarjeta", p, 6)
    cid = credito_id(repo, p)
    repo.registrar_devolucion(cid, date(2026, 1, 15), 30000000)
    c = repo.costo_credito(cid)
    assert c.precio_contado == 30000000 and c.diferencia == 0


# ---------------------------------------------------------------- E11: reserva

def test_no_se_paga_desde_una_reserva_sin_saldo(repo):
    p = cupo(repo, 0)
    repo.registrar_compra(date(2026, 1, 10), "x", None, 30000000, "tarjeta", p, 3)
    with pytest.raises(ValueError):
        repo.registrar_pago(p, date(2026, 2, 10), 10000000, desde_reserva=True)
    with pytest.raises(ValueError):
        repo.movimiento_reserva(date(2026, 2, 10), "retiro", 100)
    repo.movimiento_reserva(date(2026, 2, 1), "aporte", 10000000)
    repo.registrar_pago(p, date(2026, 2, 10), 10000000, desde_reserva=True)
    assert repo.saldo_reserva() == 0


# ---------------------------------------------------------------- E12: pago con fecha anterior

def test_pago_con_fecha_anterior_a_mora_liquidada(repo):
    p = cupo(repo, 25)
    con_usura(repo)
    repo.registrar_compra(date(2026, 1, 10), "x", None, 30000000, "tarjeta", p, 3)
    cid = credito_id(repo, p)
    repo.liquidar_mora(date(2026, 3, 1))
    q = repo.cronograma_credito(cid)[0]
    r = repo.registrar_pago(p, date(2026, 2, 12), q["capital"] + q["interes"] + 100000)
    q = repo.cronograma_credito(cid)[0]
    assert q["mora"] == credito.interes_mora(q["capital"], 27, 2) and q["estado"] == "pagada"
    assert r["mora_liquidada"] == q["mora"]


def test_pago_con_fecha_anterior_a_otro_pago_con_mora(repo):
    p = cupo(repo, 25)
    con_usura(repo)
    repo.registrar_compra(date(2026, 1, 10), "x", None, 30000000, "tarjeta", p, 3)
    repo.registrar_pago(p, date(2026, 3, 1), 100000)
    with pytest.raises(ValueError):
        repo.registrar_pago(p, date(2026, 2, 12), 100000)


# ---------------------------------------------------------------- reportes

def test_categoria_separa_cuota_inicial(repo):
    p = cupo(repo, 0)
    repo.registrar_compra(date(2026, 1, 10), "x", 1, 100000000, "tarjeta", p, 4, cuota_inicial=20000000)
    cat = repo.resumen_mes("2026-01")["por_categoria"][0]
    assert cat["efectivo"] == 20000000 and cat["tarjeta"] == 80000000


def test_deuda_a_fecha_reconstruye_el_historial(repo):
    p = cupo(repo, 30)
    repo.registrar_compra(date(2026, 1, 10), "x", None, 120000000, "tarjeta", p, 12)
    cid = credito_id(repo, p)
    q = repo.cronograma_credito(cid)[0]
    repo.registrar_pago(p, date(2026, 2, 10), q["capital"] + q["interes"] + 30000000)
    repo.registrar_devolucion(cid, date(2026, 3, 1), 10000000)
    assert repo.deuda_a_fecha(date(2026, 1, 9)) == 0
    assert repo.deuda_a_fecha(date(2026, 2, 9)) == 120000000
    assert repo.deuda_a_fecha(date(2026, 2, 10)) == 120000000 - q["capital"] - 30000000
    assert repo.deuda_a_fecha(date(2026, 3, 1)) == repo.deuda_total() == 120000000 - q["capital"] - 40000000


def test_deuda_a_fecha_con_refinanciacion(repo):
    t = repo.guardar_producto(None, "T", "", "tarjeta", 0, 30, 5, 20, 0, False)
    repo.registrar_compra(date(2026, 1, 3), "x", None, 120000000, "tarjeta", t, 12)
    r = repo.simular_refinanciacion(t, date(2026, 2, 1), 125000000, 5000000, 24, None, 28)
    repo.registrar_refinanciacion(t, date(2026, 2, 1), r)
    assert repo.deuda_a_fecha(date(2026, 1, 31)) == 120000000
    assert repo.deuda_a_fecha(date(2026, 2, 1)) == r.saldo == repo.deuda_total()


def test_cierres_completan_meses_sin_abrir_la_app(repo):
    p = cupo(repo, 0)
    repo.registrar_compra(date(2026, 1, 10), "x", None, 30000000, "tarjeta", p, 3)
    repo.registrar_pago(p, date(2026, 2, 10), 10000000)
    repo.generar_cierre(date(2026, 5, 2))
    cierres = {c["periodo"]: c["deuda_total"] for c in repo._todos("SELECT * FROM cierres_mensuales")}
    assert cierres == {"2026-01": 30000000, "2026-02": 20000000, "2026-03": 20000000, "2026-04": 20000000}


def test_refinanciar_una_sola_obligacion(repo):
    p = cupo(repo, 30)
    repo.registrar_compra(date(2026, 1, 3), "a", None, 30000000, "tarjeta", p, 3)
    repo.registrar_compra(date(2026, 1, 3), "b", None, 60000000, "tarjeta", p, 6)
    b = next(c["credito"]["id"] for c in repo.creditos(p) if c["credito"]["descripcion"] == "b")
    deuda = repo.deuda_para_refinanciar(p, date(2026, 1, 20), [b])
    r = repo.simular_refinanciacion(p, date(2026, 1, 20), deuda, 0, 12, None, 25)
    repo.registrar_refinanciacion(p, date(2026, 1, 20), r, credito_ids=[b])
    activas = {c["credito"]["descripcion"]: c["saldo"] for c in repo.creditos(p)}
    assert activas["a"] == 30000000 and "b" not in activas and activas["Deuda organizada"] == r.saldo


def test_alerta_de_usura_por_deuda_y_por_cargos(repo):
    con_usura(repo)
    p = cupo(repo, 0)
    repo.registrar_compra(date(2026, 1, 10), "cara", None, 30000000, "tarjeta", p, 3, tasa_ea=45.0)
    c = repo.condiciones_producto(p)
    c["cargos"] = [{"nombre": "Fianza", "tipo": "fianza", "base": "pct_capital", "valor": 10, "iva_pct": 19,
                    "cobro": "prorrateado", "es_interes": True}]
    repo.registrar_compra(date(2026, 1, 10), "fianza", None, 30000000, "tarjeta", p, 3, condiciones=c)
    c["cargos"][0]["es_interes"] = False
    repo.registrar_compra(date(2026, 1, 10), "fianza aparte", None, 30000000, "tarjeta", p, 3, condiciones=c)
    motivos = {a["credito"]["descripcion"]: a["motivo"] for a in repo.alertas_usura()}
    assert set(motivos) == {"cara", "fianza"}
    assert motivos["cara"] == "tasa pactada"


def test_historial_de_cambios(repo):
    p = cupo(repo, 0, 100000000)
    repo.guardar_producto(p, "Cupo", "", "cupo", 150000000, 0.0, 1, 1, 0, False)
    repo.registrar_compra(date(2026, 1, 10), "x", None, 30000000, "tarjeta", p, 3)
    pid = repo.registrar_pago(p, date(2026, 2, 10), 1000000)["pago_id"]
    repo.eliminar_pago(pid)
    h = repo.historial_cambios()
    assert [(x["entidad"], x["accion"]) for x in h] == [("pago", "eliminar"), ("producto", "editar")]
    assert json.loads(h[1]["despues"]) == {"cupo": 150000000}


def test_cuota_de_manejo_una_vez_por_ciclo(repo):
    t = repo.guardar_producto(None, "T", "", "tarjeta", 0, 0, 5, 20, 2000000, False)
    repo.registrar_compra(date(2026, 1, 3), "x", None, 120000000, "tarjeta", t, 12)
    a = repo.registrar_pago(t, date(2026, 1, 10), 6000000)
    b = repo.registrar_pago(t, date(2026, 1, 12), 6000000)
    c = repo.registrar_pago(t, date(2026, 1, 13), 2000000)
    assert (a["manejo"], b["manejo"]) == (0, 2000000)
    assert c["manejo"] == 0  # El ciclo de enero ya tiene la cuota de manejo cubierta.


def test_tasa_con_cargos_que_cuentan_como_interes():
    o = credito.Oferta("x", 100000000, num_cuotas=3, fecha=date(2026, 1, 1),
                       cargos=[credito.Cargo("Fianza", "pct_capital", 10, "prorrateado", 19, "fianza", es_interes=True)])
    _, costo = o.simular()
    assert costo.tasa_ea_interes == pytest.approx(costo.tasa_ea_efectiva, abs=1e-6) and costo.tasa_ea_interes > 90
    _, sin = credito.Oferta("y", 100000000, num_cuotas=3, fecha=date(2026, 1, 1)).simular()
    assert sin.tasa_ea_interes == 0.0
