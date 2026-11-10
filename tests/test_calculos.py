from datetime import date

import pytest

from finanzas import credito, dinero, fechas
from finanzas.credito import ABONO_CONSTANTE, CUOTA_FIJA, CuotaPendiente
from finanzas.plan import ALTO, MODERADO, ConfigPlan, EntradaPlan, calcular_plan, nivel_endeudamiento


# ---------------------------------------------------------------- dinero

@pytest.mark.parametrize("texto, esperado", [
    ("1.750.905", 175090500),
    ("469.027,32", 46902732),
    ("$ 1750905", 175090500),
    ("1750905.5", 175090550),
    ("1.750", 175000),
    ("25000", 2500000),
    ("1'750.905", 175090500),
])
def test_a_centavos(texto, esperado):
    assert dinero.a_centavos(texto) == esperado


def test_formato():
    assert dinero.formato(175090500) == "$1.750.905"
    assert dinero.formato(46902732, decimales=True) == "$469.027,32"
    assert dinero.formato(-5000) == "-$50"
    assert dinero.porcentaje(0.447) == "44,7 %"


# ---------------------------------------------------------------- fechas

def test_dias_pago_fin_de_mes():
    dias = fechas.parsear_dias_pago("15,30")
    assert dias == [15, fechas.FIN_DE_MES]
    assert fechas.fechas_pago_en_mes(2026, 2, dias) == [date(2026, 2, 15), date(2026, 2, 28)]
    assert fechas.proxima_fecha_pago(date(2026, 10, 31), dias) == date(2026, 11, 15)
    assert fechas.proxima_fecha_pago(date(2026, 11, 15), dias) == date(2026, 11, 30)


def test_primera_cuota_segun_corte():
    # Corte el 27, pago el 17 del mes siguiente.
    assert fechas.fecha_primera_cuota(date(2026, 10, 20), 27, 17) == date(2026, 11, 17)
    assert fechas.fecha_primera_cuota(date(2026, 10, 27), 27, 17) == date(2026, 11, 17)
    assert fechas.fecha_primera_cuota(date(2026, 10, 28), 27, 17) == date(2026, 12, 17)
    # Corte el 5, pago el 25 del mismo mes.
    assert fechas.fecha_primera_cuota(date(2026, 10, 3), 5, 25) == date(2026, 10, 25)


# ---------------------------------------------------------------- tasas y cronogramas

def test_conversion_tasas():
    mv = credito.ea_a_mv(27)
    assert mv == pytest.approx(0.020118, abs=1e-6)
    assert credito.mv_a_ea(mv) == pytest.approx(27)


def test_abono_constante_ejemplo_readme():
    mv = credito.ea_a_mv(27)
    cr = credito.cronograma_abono_constante(120000000, mv, date(2026, 11, 17), n=12)
    assert len(cr) == 12
    assert all(c.capital == 10000000 for c in cr)
    assert cr[0].interes == pytest.approx(2414000, abs=2000)   # ≈ $24.144
    assert cr[-1].interes == pytest.approx(201200, abs=200)    # ≈ $2.012
    assert sum(c.interes for c in cr) == pytest.approx(15693600, abs=5000)
    assert cr[-1].fecha == date(2027, 10, 17)


def test_abono_constante_cierra_saldo_con_division_inexacta():
    cr = credito.cronograma_abono_constante(100000, 0.02, date(2026, 1, 31), n=3)
    assert sum(c.capital for c in cr) == 100000
    assert cr[1].fecha == date(2026, 2, 28)
    assert cr[2].fecha == date(2026, 3, 31)


def test_cuota_fija_cierra_saldo():
    mv = credito.ea_a_mv(30)
    cr = credito.cronograma_cuota_fija(200000000, mv, date(2026, 11, 17), n=12)
    assert len(cr) == 12
    assert sum(c.capital for c in cr) == 200000000
    assert cr[0].total == pytest.approx(19157600, abs=1000)    # ≈ $191.576
    assert abs(cr[-1].total - cr[0].total) <= 1000            # La última se ajusta por redondeo (≤ $10).
    assert all(c.capital % 100 == 0 and c.interes % 100 == 0 for c in cr)  # Pesos enteros.


def test_cuota_fija_no_cubre_intereses():
    with pytest.raises(ValueError):
        credito.cronograma_cuota_fija(100000000, 0.03, date(2026, 1, 1), cuota=2000000)


def test_tasa_implicita():
    mv = credito.ea_a_mv(30)
    cuota = credito.valor_cuota_fija(200000000, 12, mv)
    assert credito.tasa_implicita_mv(200000000, 12, cuota) == pytest.approx(mv, abs=1e-6)
    assert credito.tasa_implicita_mv(1200, 12, 100) == 0.0
    assert credito.tasa_implicita_mv(1200, 12, 90) is None


def test_recalcular_tras_abono():
    mv = credito.ea_a_mv(30)
    original = credito.cronograma_cuota_fija(100000000, mv, date(2026, 1, 15), n=12)
    menos_plazo = credito.recalcular_tras_abono(CUOTA_FIJA, 50000000, mv, date(2026, 1, 15), 12,
                                                original[0].total, 0, "plazo")
    assert len(menos_plazo) < 12
    assert menos_plazo[0].total == original[0].total
    menos_cuota = credito.recalcular_tras_abono(CUOTA_FIJA, 50000000, mv, date(2026, 1, 15), 12,
                                                original[0].total, 0, "cuota")
    assert len(menos_cuota) == 12
    assert menos_cuota[0].total < original[0].total
    tarjeta = credito.recalcular_tras_abono(ABONO_CONSTANTE, 25000, mv, date(2026, 1, 15), 10,
                                            0, 10000, "plazo")
    assert [c.capital for c in tarjeta] == [10000, 10000, 5000]


# ---------------------------------------------------------------- refinanciación

def test_refinanciacion_con_cuota_y_tasa_coherentes():
    mv = credito.ea_a_mv(30)
    cuota = credito.valor_cuota_fija(200000000, 12, mv)
    r = credito.analizar_refinanciacion(204600000, 4600000, 12, date(2026, 12, 17), cuota=cuota, tasa_ea=30)
    assert r.saldo == 200000000
    assert r.advertencias == []
    assert r.ea_implicita == pytest.approx(30, abs=0.01)
    assert sum(c.capital for c in r.cronograma) == r.saldo
    assert r.costo_total == r.valor_pagado + r.intereses_cuotas
    assert r.total_pagar == r.valor_pagado + r.total_cuotas
    assert r.ultima_fecha == date(2027, 11, 17)


def test_refinanciacion_cuota_con_cargos_advierte():
    mv = credito.ea_a_mv(30)
    cuota = credito.valor_cuota_fija(200000000, 12, mv) + 500000
    r = credito.analizar_refinanciacion(200000000, 0, 12, date(2026, 12, 17), cuota=cuota, tasa_ea=30)
    assert len(r.advertencias) == 1
    assert r.ea_implicita > 30
    assert r.cuota == cuota


def test_refinanciacion_solo_tasa():
    r = credito.analizar_refinanciacion(200000000, 0, 12, date(2026, 12, 17), tasa_ea=30)
    assert r.cuota == pytest.approx(19157600, abs=1000)


def test_refinanciacion_cuota_insuficiente():
    r = credito.analizar_refinanciacion(120000000, 0, 12, date(2026, 12, 17), cuota=5000000, tasa_ea=30)
    assert r.advertencias
    assert sum(c.capital for c in r.cronograma) == 120000000


# ---------------------------------------------------------------- pagos y extracto

def test_aplicar_pago_intereses_primero_y_sobrante():
    cuotas = [
        CuotaPendiente(2, date(2026, 12, 17), 10000, 2000, 0, 0),
        CuotaPendiente(1, date(2026, 11, 17), 10000, 3000, 0, 1000),
    ]
    aplicaciones, sobrante = credito.aplicar_pago(cuotas, 30000)
    assert [a.cuota_id for a in aplicaciones] == [1, 2]
    assert aplicaciones[0].a_costos == 2000 and aplicaciones[0].a_capital == 10000
    assert aplicaciones[1].a_costos == 2000 and aplicaciones[1].a_capital == 10000
    assert sobrante == 30000 - 24000


def test_aplicar_pago_hasta_fecha():
    cuotas = [CuotaPendiente(1, date(2026, 11, 17), 10000, 0, 0, 0),
              CuotaPendiente(2, date(2026, 12, 17), 10000, 0, 0, 0)]
    aplicaciones, sobrante = credito.aplicar_pago(cuotas, 15000, hasta=date(2026, 11, 30))
    assert len(aplicaciones) == 1 and sobrante == 5000


def test_pago_minimo_extracto():
    # Estructura del resumen de extracto de Nu (valores ficticios).
    assert credito.pago_minimo_extracto(40000000, 3000000, cargos_conversion=25000) == 43025000


# ---------------------------------------------------------------- plan

def _entrada(**cambios):
    base = dict(fecha=date(2026, 11, 30), ingreso=87500000, proximo_ingreso=date(2026, 12, 15),
                ingresos_restantes_mes=1, ingreso_mensual=175000000, ingresos_por_mes=2,
                pagos_credito_antes_proximo=0, pagos_credito_meta=40000000, pagos_mes_siguiente=40000000,
                servicios_antes_proximo=10000000, dia_a_dia_mensual=60000000, saldo_reserva=40000000)
    base.update(cambios)
    return EntradaPlan(**base)


def test_nivel():
    c = ConfigPlan()
    assert nivel_endeudamiento(0.28, c) == MODERADO
    assert nivel_endeudamiento(0.45, c) == ALTO


def test_plan_estado_estable():
    # La reserva ya tiene los servicios antes del 15 (10) y las cuotas del 15 al 31 de diciembre (40).
    p = calcular_plan(_entrada(saldo_reserva=50000000))
    assert p.al_dia
    assert p.desde_reserva == 10000000      # Los servicios antes del próximo ingreso salen de la reserva.
    assert p.monto("servicios") == 0
    assert p.monto("reserva") == 0          # La reserva ya cubre el mes siguiente.
    assert p.monto("dia_a_dia") == 30000000
    excedente = 87500000 - 30000000
    assert p.monto("ahorro") + p.monto("abono") + p.monto("libre") == excedente
    assert p.nivel == MODERADO


def test_plan_construyendo_reserva_y_deficit():
    # Quincena del 15 con el pago de la tarjeta el 17 y sin reserva.
    e = _entrada(fecha=date(2026, 11, 15), proximo_ingreso=date(2026, 11, 30), ingresos_restantes_mes=2,
                 pagos_credito_antes_proximo=80000000, pagos_credito_meta=80000000,
                 pagos_mes_siguiente=80000000, saldo_reserva=0)
    p = calcular_plan(e)
    assert not p.al_dia
    assert p.deficit == 80000000 + 10000000 + 30000000 - 87500000
    assert p.monto("reserva") == 0
    assert p.nivel == ALTO


def test_plan_usa_reserva_y_reparte_aporte():
    e = _entrada(fecha=date(2026, 12, 15), proximo_ingreso=date(2026, 12, 30), ingresos_restantes_mes=2,
                 pagos_credito_antes_proximo=40000000, saldo_reserva=40000000, servicios_antes_proximo=0)
    p = calcular_plan(e)
    assert p.desde_reserva == 40000000
    assert p.monto("credito") == 0
    assert p.monto("reserva") == 20000000   # La mitad del mes siguiente en cada quincena.
    assert p.al_dia


def test_plan_reserva_incluye_servicios_del_mes_siguiente():
    # Sin reserva: hay que apartar las cuotas (40) y los servicios (25) del 15 al 31 de diciembre.
    e = _entrada(saldo_reserva=0, servicios_meta=25000000)
    p = calcular_plan(e)
    assert p.meta_reserva == 65000000
    # Es el último ingreso del mes: se apartaría todo, pero solo quedan 87,5 − 10 − 30 = 47,5.
    assert p.monto("reserva") == 47500000
    assert p.monto("ahorro") == 0
    assert p.monto("servicios") == 10000000  # Los de antes del 15 salen de este ingreso.
    assert not p.al_dia
