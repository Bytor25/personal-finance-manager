"""Pruebas del módulo de financiación: condiciones por operación, cargos, mora, pagos y costo total.

Los valores esperados se calculan aquí con las fórmulas (Decimal), no con el código probado.
"""

import sqlite3
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import pytest

from finanzas import credito, db
from finanzas.credito import CUOTA_FIJA, Cargo, Oferta
from finanzas.repositorio import Repositorio


def pesos(valor) -> int:
    """Redondeo comercial a pesos, en centavos."""
    return int((Decimal(valor) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)) * 100


def cuota_fija(capital: int, tasa: Decimal, n: int) -> int:
    return pesos(capital * tasa / (1 - (1 + tasa) ** -n))


@pytest.fixture
def repo():
    return Repositorio(db.conectar(":memory:"))


@pytest.fixture
def cupo(repo):
    return repo.guardar_producto(None, "Plataforma", "", "cupo", 0, 0.0, 1, 1, 0, False)


def cond(repo, producto_id, **cambios) -> dict:
    c = repo.condiciones_producto(producto_id)
    c.update(cambios)
    return c


def credito_de(repo, producto_id):
    return repo.creditos(producto_id)[0]["credito"]


# ---------------------------------------------------------------- cálculos puros

def test_redondeo_comercial():
    assert credito._pesos(250) == 300      # $2,50 -> $3 (round() de Python daría $2)
    assert credito._pesos(249) == 200
    assert credito._pesos(Decimal("12345650")) == 12345700


def test_conversion_de_tasas():
    assert credito.ea_a_mv(28.49) == pytest.approx(float(Decimal("1.2849") ** (Decimal(1) / 12) - 1), abs=1e-12)
    assert credito.a_ea(2.66, "MV") == pytest.approx(float((Decimal("1.0266") ** 12 - 1) * 100), abs=1e-9)
    assert credito.a_ea(24, "NAMV") == pytest.approx(float((Decimal("1.02") ** 12 - 1) * 100), abs=1e-9)
    assert credito.tasa_periodica(26.82418, "quincenal") == pytest.approx(
        float(Decimal("1.2682418") ** (Decimal(1) / 24) - 1), abs=1e-12)


def test_tasa_efectiva_por_flujos():
    # Prestar 100 y recibir 110 un año después: 10 % E.A.
    assert credito.tasa_efectiva_flujos([(date(2026, 1, 1), 10000), (date(2027, 1, 1), -11000)]) == \
        pytest.approx(10, abs=1e-6)
    assert credito.tasa_efectiva_flujos([(date(2026, 1, 1), 100)]) is None


def test_comparar_ofertas():
    precio = 100000000
    contado = Oferta("Contado", precio, cuota_inicial=precio)
    cero = Oferta("0 %", precio, num_cuotas=3, fecha=date(2026, 11, 1))
    fianza = Oferta("Con fianza", precio, num_cuotas=3, fecha=date(2026, 11, 1),
                    cargos=[Cargo("Fianza", "pct_capital", 10, "prorrateado", 19, "fianza")])
    almacen = Oferta("Almacén", precio, cuota_inicial=20000000, precio_financiado=110000000, num_cuotas=6,
                     tasa=2, modalidad_tasa="MV", fecha=date(2026, 11, 1))
    resultados = {o.nombre: costo for o, _, costo in credito.comparar_ofertas([contado, cero, fianza, almacen])}
    assert resultados["Contado"].total_pagado == precio and resultados["Contado"].diferencia == 0
    assert resultados["0 %"].diferencia == 0 and resultados["0 %"].tasa_ea_efectiva == pytest.approx(0, abs=1e-6)
    assert resultados["Con fianza"].total_cargos == pesos(precio * Decimal("0.1") * Decimal("1.19"))
    assert resultados["Con fianza"].tasa_ea_efectiva > 0          # 0 % de interés, pero cuesta.
    a = resultados["Almacén"]
    assert a.costo_comercial == 10000000 and a.capital == 90000000
    assert a.total_cuotas == cuota_fija(90000000, Decimal("0.02"), 6) * 5 + (
        a.total_cuotas - cuota_fija(90000000, Decimal("0.02"), 6) * 5)
    assert a.diferencia == a.total_pagado - precio and a.incremento_pct > 10


# ---------------------------------------------------------------- escenarios obligatorios

def test_credito_cero_por_ciento(repo, cupo):
    repo.registrar_compra(date(2026, 11, 3), "Promo", None, 30000000, "tarjeta", cupo, 3)
    cuotas = repo.cronograma_credito(credito_de(repo, cupo)["id"])
    assert [c["capital"] for c in cuotas] == [10000000] * 3 and all(c["interes"] == 0 for c in cuotas)


def test_credito_interes_mensual(repo, cupo):
    c = cond(repo, cupo, tasa={"valor": 2.66, "modalidad": "MV"})
    repo.registrar_compra(date(2026, 11, 3), "TV", None, 100000000, "tarjeta", cupo, 6, condiciones=c)
    cuotas = repo.cronograma_credito(credito_de(repo, cupo)["id"])
    esperada = cuota_fija(100000000, Decimal("0.0266"), 6)
    assert all(c["capital"] + c["interes"] == esperada for c in cuotas[:-1])
    assert cuotas[0]["interes"] == pesos(100000000 * Decimal("0.0266"))
    assert sum(c["capital"] for c in cuotas) == 100000000
    snapshot = repo.condiciones_credito(credito_de(repo, cupo)["id"])
    assert snapshot["tasa"] == {"valor": 2.66, "modalidad": "MV"}  # Se conserva la tasa original y su periodicidad.


def test_credito_tasa_efectiva_anual(repo, cupo):
    c = cond(repo, cupo, tasa={"valor": 28.49, "modalidad": "EA"})
    repo.registrar_compra(date(2026, 11, 3), "Nevera", None, 120000000, "tarjeta", cupo, 12, condiciones=c)
    tasa = Decimal("1.2849") ** (Decimal(1) / 12) - 1
    cuotas = repo.cronograma_credito(credito_de(repo, cupo)["id"])
    assert cuotas[0]["capital"] + cuotas[0]["interes"] == cuota_fija(120000000, tasa, 12)


def test_credito_con_aval_e_iva(repo, cupo):
    aval = {"nombre": "Aval", "tipo": "aval", "base": "pct_capital", "valor": 8, "iva_pct": 19, "cobro": "prorrateado"}
    c = cond(repo, cupo, tasa={"valor": 2.66, "modalidad": "MV"}, cargos=[aval])
    repo.registrar_compra(date(2026, 11, 3), "Celular", None, 60000000, "tarjeta", cupo, 4, condiciones=c)
    cuotas = repo.cronograma_credito(credito_de(repo, cupo)["id"])
    total_aval = pesos(60000000 * Decimal("0.08") * Decimal("1.19"))
    assert sum(c["otros"] for c in cuotas) == total_aval
    assert cuotas[0]["interes"] == pesos(60000000 * Decimal("0.0266"))   # El aval no se mezcla con intereses.
    assert '"Aval"' in cuotas[0]["detalle"]


def test_credito_con_fianza_inicial_e_iva(repo, cupo):
    fianza = {"nombre": "Fianza", "tipo": "fianza", "base": "pct_capital", "valor": 10, "iva_pct": 19,
              "cobro": "inicial"}
    repo.registrar_compra(date(2026, 11, 3), "Bici", None, 50000000, "tarjeta", cupo, 2,
                          condiciones=cond(repo, cupo, cargos=[fianza]))
    esperado = pesos(50000000 * Decimal("0.1") * Decimal("1.19"))
    r = repo.resumen_mes("2026-11")
    assert r["costo_deuda"] == esperado and r["salio"] == esperado
    assert credito_de(repo, cupo)["cargos_iniciales"] == esperado
    costo = repo.costo_credito(credito_de(repo, cupo)["id"])
    assert costo.total_pagado == 50000000 + esperado and costo.tasa_ea_efectiva > 0


def test_credito_con_cuota_inicial(repo, cupo):
    repo.registrar_compra(date(2026, 11, 3), "Sofá", None, 100000000, "tarjeta", cupo, 4, cuota_inicial=20000000,
                          precio_contado=90000000)
    assert repo.deuda_total() == 80000000
    r = repo.resumen_mes("2026-11")
    assert r["salio"] == 20000000 and r["compras_tarjeta"] == 80000000
    costo = repo.costo_credito(credito_de(repo, cupo)["id"])
    assert costo.costo_comercial == 10000000 and costo.diferencia == 10000000


def test_pago_parcial_respeta_orden(repo, cupo):
    aval = {"nombre": "Aval", "base": "fijo", "valor": 500000, "cobro": "por_cuota"}
    c = cond(repo, cupo, tasa={"valor": 2, "modalidad": "MV"}, cargos=[aval])
    repo.registrar_compra(date(2026, 10, 3), "X", None, 30000000, "tarjeta", cupo, 3, condiciones=c)
    r = repo.registrar_pago(cupo, date(2026, 11, 2), 800000)
    # Orden por defecto: cobranza, mora, cargos, intereses, capital.
    assert r["tipo"] == "menor_al_minimo"
    assert r["por_componente"] == {"otros": 500000, "interes": 300000}


def test_orden_configurable_capital_antes_que_cargos(repo, cupo):
    aval = {"nombre": "Fianza", "base": "fijo", "valor": 500000, "cobro": "por_cuota"}
    c = cond(repo, cupo, cargos=[aval], orden_pagos=["cobranza", "mora", "interes", "capital", "otros"])
    repo.registrar_compra(date(2026, 10, 3), "X", None, 30000000, "tarjeta", cupo, 3, condiciones=c)
    r = repo.registrar_pago(cupo, date(2026, 11, 2), 10000000)
    assert r["por_componente"] == {"capital": 10000000}   # La fianza queda pendiente.


def test_abono_capital_mantiene_fianza(repo, cupo):
    fianza = {"nombre": "Fianza", "base": "pct_capital", "valor": 12, "iva_pct": 19, "cobro": "prorrateado"}
    c = cond(repo, cupo, tasa={"valor": 2, "modalidad": "MV"}, cargos=[fianza], cargos_prepago="se_mantienen")
    repo.registrar_compra(date(2026, 10, 3), "X", None, 60000000, "tarjeta", cupo, 6, condiciones=c)
    cid = credito_de(repo, cupo)["id"]
    total_fianza = sum(c["otros"] for c in repo.cronograma_credito(cid))
    minimo = repo.proximo_pago_producto(cupo, date(2026, 11, 1))["minimo"]
    r = repo.registrar_pago(cupo, date(2026, 11, 2), minimo + 30000000)
    assert r["abono_extra"] == 30000000
    vigentes = repo.cronograma_credito(cid)
    assert sum(c["otros"] for c in vigentes) == total_fianza            # La fianza no se reduce.
    assert len([c for c in vigentes if c["estado"] == "pendiente"]) < 5  # Pero el plazo sí.
    repo.eliminar_pago(r["pago_id"])
    assert sum(c["otros"] for c in repo.cronograma_credito(cid)) == total_fianza
    assert repo.deuda_total() == 60000000


def test_anticipar_cuotas(repo, cupo):
    repo.registrar_compra(date(2026, 10, 3), "X", None, 30000000, "tarjeta", cupo, 3)
    r = repo.registrar_pago(cupo, date(2026, 11, 2), 20000000, reducir="anticipar")
    assert r["anticipado"] == 10000000 and r["abono_extra"] == 0
    assert repo.deuda_total() == 10000000


def test_prepago_total_con_cargos_que_se_mantienen(repo, cupo):
    fianza = {"nombre": "Fianza", "base": "fijo", "valor": 1000000, "cobro": "por_cuota"}
    c = cond(repo, cupo, cargos=[fianza], cargos_prepago="se_mantienen")
    repo.registrar_compra(date(2026, 10, 3), "X", None, 30000000, "tarjeta", cupo, 3, condiciones=c)
    total = repo.proximo_pago_producto(cupo, date(2026, 11, 1))["total"]
    assert total == 30000000 + 3 * 1000000
    r = repo.registrar_pago(cupo, date(2026, 11, 2), total)
    assert r["tipo"] == "total" and repo.deuda_total() == 0 and repo.creditos(cupo) == []


def test_mora_con_usura_historica_y_cobranza(repo, cupo):
    repo.guardar_tasa_legal(None, "consumo", date(2026, 11, 1), date(2026, 11, 30), 27.0, 18.0)
    cobranza = {"desde_dias": 1, "base": "fijo", "valor": 2000000, "iva_pct": 19, "frecuencia": "unica"}
    c = cond(repo, cupo)
    c["mora"] = {"tasa_ea": 40.0, "cobranza": [cobranza]}    # Pactada por encima de la usura: se limita.
    repo.registrar_compra(date(2026, 10, 2), "X", None, 30000000, "tarjeta", cupo, 3, condiciones=c)
    # La primera cuota venció el 2 de noviembre; pago el 20 (18 días de mora).
    mora = pesos(10000000 * ((1 + Decimal("0.27")) ** (Decimal(18) / 365) - 1))
    gasto = pesos(2000000 * Decimal("1.19"))
    estado = repo.estado_mora(date(2026, 11, 20))
    assert estado[0]["dias"] == 18 and estado[0]["por_liquidar"] == mora + gasto
    r = repo.registrar_pago(cupo, date(2026, 11, 20), 10000000 + mora + gasto)
    assert r["mora_liquidada"] == mora + gasto
    assert r["por_componente"] == {"cobranza": gasto, "mora": mora, "capital": 10000000}
    # Volver a liquidar no duplica la cobranza.
    assert repo.liquidar_mora(date(2026, 11, 25), cupo) == 0
    repo.eliminar_pago(r["pago_id"])
    assert repo.estado_mora(date(2026, 11, 20))[0]["por_liquidar"] == mora + gasto


def test_mora_sin_tasa_legal_registrada_no_inventa(repo, cupo):
    repo.registrar_compra(date(2026, 10, 2), "X", None, 30000000, "tarjeta", cupo, 3)
    assert repo.estado_mora(date(2026, 11, 20))[0]["por_liquidar"] == 0


def test_devolucion_de_compra(repo, cupo):
    repo.registrar_compra(date(2026, 11, 3), "Zapatos", None, 60000000, "tarjeta", cupo, 3)
    cid = credito_de(repo, cupo)["id"]
    r = repo.registrar_devolucion(cid, date(2026, 11, 10), 30000000)
    assert r["a_capital"] == 30000000 and r["saldo_a_favor"] == 0
    assert repo.deuda_total() == 30000000
    resumen = repo.resumen_mes("2026-11")
    assert resumen["salio"] == 0 and resumen["pagos_credito"] == 0 and resumen["compras_tarjeta"] == 30000000
    repo.eliminar_pago(r["pago_id"])
    assert repo.deuda_total() == 60000000


def test_acuerdo_de_pago(repo, cupo):
    repo.registrar_compra(date(2026, 10, 2), "X", None, 30000000, "tarjeta", cupo, 3)
    r = repo.simular_refinanciacion(cupo, date(2026, 11, 20), 30000000, 0, 6, None, 20.0)
    refi = repo.registrar_refinanciacion(cupo, date(2026, 11, 20), r, tipo="acuerdo_pago")
    assert repo.refinanciaciones(cupo)[0]["tipo"] == "acuerdo_pago"
    repo.eliminar_refinanciacion(refi)
    assert len(repo.creditos(cupo)) == 1


def test_quincenal(repo, cupo):
    c = cond(repo, cupo, tasa={"valor": 24, "modalidad": "EA"}, periodicidad="quincenal")
    repo.registrar_compra(date(2026, 11, 1), "X", None, 24000000, "tarjeta", cupo, 4, condiciones=c)
    cuotas = repo.cronograma_credito(credito_de(repo, cupo)["id"])
    assert [c["fecha"] for c in cuotas] == ["2026-11-16", "2026-12-01", "2026-12-16", "2026-12-31"]
    tasa = Decimal("1.24") ** (Decimal(1) / 24) - 1
    assert cuotas[0]["interes"] == pesos(24000000 * tasa)


def test_plantilla_no_cambia_creditos_existentes(repo, cupo):
    repo.registrar_compra(date(2026, 11, 3), "Antes", None, 30000000, "tarjeta", cupo, 3)
    nueva = cond(repo, cupo, tasa={"valor": 30, "modalidad": "EA"})
    repo.guardar_condiciones_producto(cupo, nueva)
    viejo = credito_de(repo, cupo)
    assert repo.condiciones_credito(viejo["id"])["tasa"]["valor"] == 0.0
    repo.registrar_compra(date(2026, 11, 4), "Después", None, 30000000, "tarjeta", cupo, 3)
    assert repo.condiciones_credito(credito_de(repo, cupo)["id"])["tasa"]["valor"] == 30


def test_condiciones_invalidas(repo, cupo):
    with pytest.raises(ValueError):
        repo.guardar_condiciones_producto(cupo, cond(repo, cupo, orden_pagos=["capital"]))
    with pytest.raises(ValueError):
        repo.guardar_condiciones_producto(cupo, cond(repo, cupo, cargos=[
            {"nombre": "Seguro", "base": "pct_saldo", "valor": 1, "cobro": "prorrateado"}]))


def test_seguro_sobre_saldo(repo, cupo):
    seguro = {"nombre": "Seguro", "tipo": "seguro", "base": "pct_saldo", "valor": 0.1, "cobro": "por_cuota"}
    c = cond(repo, cupo, tasa={"valor": 2, "modalidad": "MV"}, cargos=[seguro])
    repo.registrar_compra(date(2026, 11, 3), "X", None, 60000000, "tarjeta", cupo, 3, condiciones=c)
    cuotas = repo.cronograma_credito(credito_de(repo, cupo)["id"])
    saldo = 60000000
    for cu in cuotas:
        assert cu["otros"] == pesos(saldo * Decimal("0.001"))
        saldo -= cu["capital"]


def test_pago_duplicado(repo, cupo):
    repo.registrar_compra(date(2026, 10, 3), "X", None, 30000000, "tarjeta", cupo, 3)
    repo.registrar_pago(cupo, date(2026, 11, 2), 10000000, canal="PSE")
    assert repo.pago_posible_duplicado(cupo, date(2026, 11, 2), 10000000)
    assert repo.pagos(producto_id=cupo)[0]["canal"] == "PSE"


def test_migracion_pagado_por_componente(tmp_path):
    ruta = tmp_path / "vieja.db"
    vieja = sqlite3.connect(ruta)
    vieja.executescript(db.ESQUEMA + db.TABLA_PRODUCTOS.format(nombre="productos_credito"))
    vieja.executescript("""
        INSERT INTO productos_credito (id, nombre) VALUES (1, 'T');
        INSERT INTO creditos (id, producto_id, origen, fecha, monto, num_cuotas, tasa_ea, metodo)
            VALUES (1, 1, 'deuda_existente', '2026-10-01', 100000, 1, 20, 'abono_constante');
        INSERT INTO cuotas (credito_id, numero, fecha, capital, interes, otros, pagado)
            VALUES (1, 1, '2026-11-17', 100000, 3000, 1000, 6000);
    """)
    vieja.commit()
    vieja.close()
    repo = Repositorio(db.conectar(ruta))
    c = repo.con.execute("SELECT * FROM cuotas").fetchone()
    assert (c["pagado_interes"], c["pagado_otros"], c["pagado_capital"]) == (3000, 1000, 2000)
    assert repo.deuda_total() == 98000
