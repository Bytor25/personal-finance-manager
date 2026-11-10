from datetime import date

import pytest

from finanzas import db
from finanzas.credito import ABONO_CONSTANTE, CUOTA_FIJA
from finanzas.plan import calcular_plan
from finanzas.repositorio import Repositorio

HOY = date(2026, 11, 1)


@pytest.fixture
def repo():
    return Repositorio(db.conectar(":memory:"))


@pytest.fixture
def tarjeta(repo):
    # Corte el 27, pago el 17; 30 % E.A.; sin cuota de manejo.
    return repo.guardar_producto(None, "Tarjeta", "Banco", "tarjeta", 300000000, 30.0, 27, 17, 0, False)


def test_categorias_iniciales(repo):
    assert any(c["nombre"] == "Comida" for c in repo.categorias())


def test_compra_con_tarjeta_genera_cronograma(repo, tarjeta):
    repo.registrar_compra(date(2026, 10, 30), "Tenis", None, 30000000, "tarjeta", tarjeta, 6)
    cr = repo.creditos(tarjeta)
    assert len(cr) == 1
    cuotas = repo.cronograma_credito(cr[0]["credito"]["id"])
    assert len(cuotas) == 6
    assert cuotas[0]["fecha"] == "2026-12-17"  # Después del corte del 27 oct.
    assert repo.deuda_total() == 30000000


def test_compra_una_cuota_sin_interes(repo, tarjeta):
    repo.registrar_compra(date(2026, 10, 10), "Almuerzo", None, 5000000, "tarjeta", tarjeta, 1)
    cuotas = repo.cronograma_credito(repo.creditos(tarjeta)[0]["credito"]["id"])
    assert cuotas[0]["interes"] == 0 and cuotas[0]["fecha"] == "2026-11-17"


def test_compra_efectivo_no_es_deuda(repo):
    repo.registrar_compra(date(2026, 11, 2), "Mercado", None, 10000000, "efectivo")
    r = repo.resumen_mes("2026-11")
    assert r["salio"] == 10000000 and repo.deuda_total() == 0


def test_pago_minimo_y_resumen(repo, tarjeta):
    repo.registrar_compra(date(2026, 10, 10), "Laptop", None, 120000000, "tarjeta", tarjeta, 12)
    prox = repo.proximo_pago_producto(tarjeta, HOY)
    assert prox["fecha_limite"] == date(2026, 11, 17)
    r = repo.registrar_pago(tarjeta, date(2026, 11, 15), prox["minimo"])
    assert r["tipo"] == "minimo" and r["abono_extra"] == 0
    assert repo.deuda_total() == 110000000
    resumen = repo.resumen_mes("2026-11")
    assert resumen["pagos_credito"] == prox["minimo"]
    assert resumen["costo_deuda"] == prox["minimo"] - 10000000
    # La compra con tarjeta aparece en "en qué gasté" pero no en "salió".
    assert repo.resumen_mes("2026-10")["compras_tarjeta"] == 120000000
    assert repo.resumen_mes("2026-10")["salio"] == 0


def test_abono_extra_reduce_plazo_y_se_puede_deshacer(repo, tarjeta):
    repo.registrar_compra(date(2026, 10, 10), "Laptop", None, 120000000, "tarjeta", tarjeta, 12)
    credito_id = repo.creditos(tarjeta)[0]["credito"]["id"]
    minimo = repo.proximo_pago_producto(tarjeta, HOY)["minimo"]
    r = repo.registrar_pago(tarjeta, date(2026, 11, 15), minimo + 30000000)
    assert r["tipo"] == "mas_del_minimo" and r["abono_extra"] == 30000000
    assert repo.deuda_total() == 80000000
    assert repo.creditos(tarjeta)[0]["cuotas_restantes"] == 8
    repo.eliminar_pago(r["pago_id"])
    assert repo.deuda_total() == 120000000
    assert len(repo.cronograma_credito(credito_id)) == 12


def test_pago_total_liquida(repo, tarjeta):
    repo.registrar_compra(date(2026, 10, 10), "Laptop", None, 60000000, "tarjeta", tarjeta, 3)
    total = repo.proximo_pago_producto(tarjeta, HOY)["total"]
    r = repo.registrar_pago(tarjeta, date(2026, 11, 15), total)
    assert r["tipo"] == "total"
    assert repo.deuda_total() == 0
    assert repo.creditos(tarjeta) == []


def test_no_borrar_compra_con_pagos(repo, tarjeta):
    compra = repo.registrar_compra(date(2026, 10, 10), "Laptop", None, 60000000, "tarjeta", tarjeta, 3)
    repo.registrar_pago(tarjeta, date(2026, 11, 15), 1000000)
    with pytest.raises(ValueError):
        repo.eliminar_compra(compra)


def test_extracto_reemplaza_cronograma(repo, tarjeta):
    repo.registrar_compra(date(2026, 10, 10), "Laptop", None, 60000000, "tarjeta", tarjeta, 3)
    repo.registrar_extracto(tarjeta, date(2026, 10, 27), date(2026, 11, 17), 20000000, 1300000,
                            cargos_conversion=28000, deuda_restante=40000000)
    prox = repo.proximo_pago_producto(tarjeta, HOY)
    assert prox["fuente"] == "extracto"
    assert prox["minimo"] == 21328000 and prox["total"] == 61328000
    programado = repo.pagos_programados(None, date(2026, 11, 30))
    assert programado[0]["monto"] == 21328000
    repo.registrar_pago(tarjeta, date(2026, 11, 10), 10000000)
    assert repo.proximo_pago_producto(tarjeta, HOY)["minimo"] == 11328000


def test_refinanciacion_registrar_y_deshacer(repo, tarjeta):
    repo.registrar_compra(date(2026, 9, 10), "A", None, 100000000, "tarjeta", tarjeta, 6)
    repo.registrar_compra(date(2026, 10, 10), "B", None, 50000000, "tarjeta", tarjeta, 3)
    deuda = repo.deuda_para_refinanciar(tarjeta, HOY)
    r = repo.simular_refinanciacion(tarjeta, HOY, deuda, 3000000, 12, None, 30.0)
    refi = repo.registrar_refinanciacion(tarjeta, HOY, r)
    activos = repo.creditos(tarjeta)
    assert len(activos) == 1 and activos[0]["credito"]["metodo"] == CUOTA_FIJA
    assert repo.deuda_total() == r.saldo
    assert repo.resumen_mes("2026-11")["costo_deuda"] == 3000000
    repo.eliminar_refinanciacion(refi)
    assert len(repo.creditos(tarjeta)) == 2
    assert repo.resumen_mes("2026-11")["costo_deuda"] == 0


def test_extracto_anterior_a_refinanciacion_se_ignora(repo, tarjeta):
    repo.registrar_extracto(tarjeta, date(2026, 10, 27), date(2026, 11, 17), 20000000, 1300000,
                            deuda_restante=40000000)
    r = repo.simular_refinanciacion(tarjeta, HOY, 61300000, 1300000, 12, None, 30.0)
    repo.registrar_refinanciacion(tarjeta, HOY, r)
    assert repo.proximo_pago_producto(tarjeta, HOY)["fuente"] == "cronograma"


def test_deuda_existente_con_cuota(repo):
    prestamo = repo.guardar_producto(None, "Préstamo", "Banco", "prestamo", 0, 20.0, 1, 5, 0, False)
    repo.registrar_deuda_existente(prestamo, "Libre inversión", date(2026, 12, 5), 500000000, 24, 0, 20.0,
                                   CUOTA_FIJA, cuota=25000000)
    cr = repo.creditos(prestamo)[0]
    assert cr["saldo"] == 500000000 and cr["cuotas_restantes"] == 24


def test_cuotas_existentes_de_tarjeta(repo, tarjeta):
    # Compra de $1.200.000 a 12 cuotas; la app del banco muestra "cuota 5 de 12" → 4 pagadas.
    cid = repo.registrar_deuda_existente(tarjeta, "Celular", date(2026, 11, 17), 120000000, 12, 4, 30.0,
                                         ABONO_CONSTANTE)
    cuotas = repo.cronograma_credito(cid)
    assert [c["numero"] for c in cuotas] == list(range(5, 13))
    assert cuotas[0]["fecha"] == "2026-11-17" and cuotas[-1]["fecha"] == "2027-06-17"
    assert repo.creditos(tarjeta)[0]["saldo"] == 80000000
    assert repo.creditos(tarjeta)[0]["credito"]["num_cuotas"] == 12
    # Con el saldo que muestra el banco, manda ese saldo.
    cid = repo.registrar_deuda_existente(tarjeta, "Ropa", date(2026, 11, 17), 30000000, 3, 1, 30.0,
                                         ABONO_CONSTANTE, saldo=20000500)
    assert sum(c["capital"] for c in repo.cronograma_credito(cid)) == 20000500
    with pytest.raises(ValueError):
        repo.registrar_deuda_existente(tarjeta, "X", date(2026, 11, 17), 30000000, 3, 3, 30.0, ABONO_CONSTANTE)


@pytest.fixture
def addi(repo):
    return repo.guardar_producto(None, "Addi", "", "cupo", 150000000, 0.0, 1, 1, 0, False)


def test_cupo_sin_intereses_con_cargo(repo, addi):
    repo.registrar_compra(date(2026, 11, 3), "Zapatos", None, 30000000, "tarjeta", addi, 3, cargo_por_cuota=500000)
    cr = repo.creditos(addi)[0]
    assert cr["credito"]["metodo"] == CUOTA_FIJA
    cuotas = repo.cronograma_credito(cr["credito"]["id"])
    assert [c["fecha"] for c in cuotas] == ["2026-12-03", "2027-01-03", "2027-02-03"]
    assert all(c["interes"] == 0 and c["capital"] == 10000000 and c["otros"] == 500000 for c in cuotas)
    assert repo.proximo_pago_producto(addi, HOY)["minimo"] == 10500000


def test_cupo_agrupa_cuotas_del_mes(repo, addi):
    # Dos compras que vencen en días distintos del mismo mes: el próximo pago las reúne.
    repo.registrar_compra(date(2026, 10, 5), "A", None, 30000000, "tarjeta", addi, 3)
    repo.registrar_compra(date(2026, 10, 20), "B", None, 60000000, "tarjeta", addi, 3)
    prox = repo.proximo_pago_producto(addi, HOY)
    assert prox["fecha_limite"] == date(2026, 11, 20) and prox["minimo"] == 30000000
    r = repo.registrar_pago(addi, date(2026, 11, 4), 30000000)
    assert r["tipo"] == "minimo" and r["abono_extra"] == 0
    assert repo.deuda_total() == 60000000


def test_compra_con_tasa_y_fecha_propias(repo, tarjeta):
    repo.registrar_compra(date(2026, 11, 3), "Promo", None, 60000000, "tarjeta", tarjeta, 6, tasa_ea=0.0,
                          primera_cuota=date(2027, 1, 17))
    cuotas = repo.cronograma_credito(repo.creditos(tarjeta)[0]["credito"]["id"])
    assert cuotas[0]["fecha"] == "2027-01-17" and all(c["interes"] == 0 for c in cuotas)


def test_migracion_tipo_cupo(tmp_path):
    import sqlite3
    ruta = tmp_path / "vieja.db"
    vieja = sqlite3.connect(ruta)
    esquema_viejo = db.ESQUEMA + db.TABLA_PRODUCTOS.format(nombre="productos_credito").replace(
        "'tarjeta', 'cupo', 'prestamo'", "'tarjeta', 'prestamo'")
    vieja.executescript(esquema_viejo)
    vieja.execute("INSERT INTO productos_credito (nombre, tipo, tasa_ea) VALUES ('Vieja', 'tarjeta', 25)")
    vieja.commit()
    vieja.close()
    repo = Repositorio(db.conectar(ruta))
    assert repo.productos()[0]["nombre"] == "Vieja"
    repo.guardar_producto(None, "Addi", "", "cupo", 0, 0.0, 1, 1, 0, False)
    assert repo.con.execute("PRAGMA foreign_key_check").fetchall() == []


def test_servicios_pendientes_y_pago(repo):
    repo.guardar_servicio(None, "Internet", None, 9000000, 10)
    assert len(repo.servicios_pendientes(date(2026, 11, 1), date(2026, 11, 30))) == 1
    servicio_id = repo.servicios()[0]["id"]
    repo.pagar_servicio(servicio_id, date(2026, 11, 8), 9000000)
    assert repo.servicios_pendientes(date(2026, 11, 1), date(2026, 11, 30)) == []
    # Los servicios no cuentan en el promedio del día a día.
    assert repo.dia_a_dia_mensual(date(2026, 12, 5)) == 0


def test_reserva_y_pago_desde_reserva(repo, tarjeta):
    repo.registrar_compra(date(2026, 10, 10), "Laptop", None, 60000000, "tarjeta", tarjeta, 3)
    repo.movimiento_reserva(date(2026, 11, 1), "aporte", 30000000)
    r = repo.registrar_pago(tarjeta, date(2026, 11, 15), 20000000, desde_reserva=True)
    assert repo.saldo_reserva() == 10000000
    repo.eliminar_pago(r["pago_id"])
    assert repo.saldo_reserva() == 30000000


def test_entrada_plan_quincenal(repo, tarjeta):
    repo.guardar_fuente(None, "Sueldo", 200000000, "15,30", False, "activa")
    repo.guardar_fuente(None, "Freelance", 50000000, "30", False, "esperada")
    repo.registrar_compra(date(2026, 10, 10), "Laptop", None, 120000000, "tarjeta", tarjeta, 12)
    e = repo.entrada_plan(date(2026, 11, 15), 100000000)
    assert e.proximo_ingreso == date(2026, 11, 30)
    assert e.ingresos_restantes_mes == 2 and e.ingresos_por_mes == 2
    assert e.ingreso_mensual == 200000000
    assert e.pagos_credito_antes_proximo > 0       # La cuota del 17 de noviembre.
    assert e.pagos_credito_meta == e.pagos_mes_siguiente > 0
    assert repo.entrada_plan(date(2026, 11, 15), 100000000, incluir_esperadas=True).ingreso_mensual == 250000000
    plan = calcular_plan(e, repo.config_plan())
    assert sum(p.monto for p in plan.partidas) + plan.deficit >= 0
    recomendacion = repo.recomendacion_pagos(plan.monto("abono"), HOY)
    assert recomendacion[0]["recomendado"] >= recomendacion[0]["minimo"]


def test_respaldo_y_rotacion(tmp_path):
    con = db.conectar(tmp_path / "f.db")
    carpeta = tmp_path / "respaldos"
    for dia in range(1, 21):
        db.respaldar(con, carpeta, date(2026, 10, dia))
    for mes in range(1, 10):
        db.respaldar(con, carpeta, date(2025, mes, 3))
    nombres = sorted(p.name for p in carpeta.glob("*.zip"))
    assert "finanzas_2026-10-20.zip" in nombres and "finanzas_2026-10-14.zip" in nombres
    assert "finanzas_2026-10-13.zip" not in nombres
    assert "finanzas_2026-10-01.zip" in nombres          # Primero del mes.
    assert len(nombres) == 7 + 1 + 9                     # 7 diarios + 1 de oct + 9 meses de 2025.


def test_respaldo_antes_de_migrar(tmp_path):
    import sqlite3
    import zipfile
    ruta = tmp_path / "vieja.db"
    vieja = sqlite3.connect(ruta)
    vieja.executescript(db.ESQUEMA + db.TABLA_PRODUCTOS.format(nombre="productos_credito").replace(
        "'tarjeta', 'cupo', 'prestamo'", "'tarjeta', 'prestamo'"))
    vieja.close()
    db.respaldar_archivo(ruta, tmp_path / "respaldos")
    db.conectar(ruta).close()
    respaldo = next((tmp_path / "respaldos").glob("*.zip"))
    zipfile.ZipFile(respaldo).extract("finanzas.db", tmp_path / "x")
    sql = sqlite3.connect(tmp_path / "x" / "finanzas.db").execute(
        "SELECT sql FROM sqlite_master WHERE name = 'productos_credito'").fetchone()[0]
    assert "'cupo'" not in sql  # El respaldo conserva la estructura anterior.
    db.respaldar_archivo(tmp_path / "no_existe.db", tmp_path / "respaldos")


def test_pago_servicio_parcial_distinto_y_a_credito(repo):
    repo.guardar_servicio(None, "Luz", None, 10000000, 10)
    sid = repo.servicios()[0]["id"]
    nov = (date(2026, 11, 1), date(2026, 11, 30))
    # Pago menor marcado como parcial: sigue pendiente lo que falta.
    repo.pagar_servicio(sid, date(2026, 11, 5), 4000000, parcial=True)
    assert [p["monto"] for p in repo.servicios_pendientes(*nov)] == [6000000]
    # El resto completa el mes.
    repo.pagar_servicio(sid, date(2026, 11, 8), 6000000, parcial=True)
    assert repo.servicios_pendientes(*nov) == []
    # Diciembre: la factura llegó más barata; un pago no parcial lo salda y actualiza el estimado.
    repo.pagar_servicio(sid, date(2026, 12, 9), 8000000, actualizar_estimado=True)
    assert repo.servicios_pendientes(date(2026, 12, 1), date(2026, 12, 31)) == []
    assert repo.servicios()[0]["monto_estimado"] == 8000000


def test_pago_servicio_con_tarjeta(repo, tarjeta):
    repo.guardar_servicio(None, "Internet", None, 9000000, 10)
    sid = repo.servicios()[0]["id"]
    repo.pagar_servicio(sid, date(2026, 11, 8), 9500000, medio="tarjeta", producto_id=tarjeta, num_cuotas=1)
    assert repo.servicios_pendientes(date(2026, 11, 1), date(2026, 11, 30)) == []
    assert repo.deuda_total() == 9500000


def _ejemplo_quincenal(repo):
    """Sueldo 15 y 30; servicios el 5, 7, 10 y 15 (el caso que describió el usuario)."""
    repo.guardar_fuente(None, "Sueldo", 400000000, "15,30", False, "activa")
    for nombre, dia, monto in [("Arriendo", 5, 120000000), ("Luz", 7, 15000000), ("Internet", 10, 9000000),
                               ("Celular", 15, 6000000)]:
        repo.guardar_servicio(None, nombre, None, monto, dia)


def test_plan_sueldo_del_30_cubre_hasta_el_14(repo):
    _ejemplo_quincenal(repo)
    e = repo.entrada_plan(date(2026, 11, 30), 200000000)
    assert e.proximo_ingreso == date(2026, 12, 15)
    assert [v.concepto for v in e.detalle] == ["Arriendo", "Luz", "Internet"]  # El del 15 va con el sueldo del 15.
    assert e.servicios_antes_proximo == 144000000
    assert e.servicios_meta == 6000000  # El celular del 15 de diciembre va a la reserva.


def test_plan_sueldo_que_llega_antes_cuenta_como_el_del_30(repo):
    _ejemplo_quincenal(repo)
    e = repo.entrada_plan(date(2026, 11, 28), 200000000)  # El 30 cae domingo: pagan el viernes 28.
    assert e.fecha_efectiva == date(2026, 11, 30)
    assert e.proximo_ingreso == date(2026, 12, 15)
    assert e.servicios_antes_proximo == 144000000
    # Una prima no se toma como sueldo adelantado.
    assert repo.entrada_plan(date(2026, 11, 28), 50000000, tipo="extraordinario").proximo_ingreso == \
        date(2026, 11, 30)


def test_servicio_pagado_con_la_reserva(repo):
    _ejemplo_quincenal(repo)
    repo.movimiento_reserva(date(2026, 11, 30), "aporte", 20000000)
    disponible = repo.saldo_disponible(date(2026, 12, 7))
    sid = next(s["id"] for s in repo.servicios() if s["nombre"] == "Luz")
    compra = repo.pagar_servicio(sid, date(2026, 12, 7), 15000000, desde_reserva=True)
    assert repo.saldo_reserva() == 5000000
    assert repo.saldo_disponible(date(2026, 12, 7)) == disponible  # No sale del bolsillo: salió de la reserva.
    with pytest.raises(ValueError):
        repo.pagar_servicio(sid, date(2026, 12, 8), 15000000, desde_reserva=True)  # Ya no alcanza.
    mov = repo.movimientos_reserva()[0]
    with pytest.raises(ValueError):
        repo.eliminar_movimiento_reserva(mov["id"])
    repo.eliminar_compra(compra)
    assert repo.saldo_reserva() == 20000000  # Al borrar el pago, la plata vuelve a la reserva.
