from datetime import date

import pytest

from finanzas import db
from finanzas.ahorro import EntradaAhorro, Meta, capacidad_ahorro, meses_hasta, repartir
from finanzas.repositorio import Repositorio


@pytest.fixture
def repo():
    return Repositorio(db.conectar(":memory:"))


# ---------------------------------------------------------------- cálculo puro

def test_meses_hasta():
    assert meses_hasta("2026-11", date(2027, 4, 30)) == 6  # nov, dic, ene, feb, mar, abr
    assert meses_hasta("2026-11", date(2026, 10, 1)) == 1  # Fecha pasada: al menos un aporte.


def test_repartir_prioriza_metas_con_fecha():
    viaje = Meta(1, "Viaje", 600_000_00, 0, date(2027, 4, 30), prioridad=2)  # 6 meses → 100k/mes
    consola = Meta(2, "Consola", 2_000_000_00, 0, None, prioridad=1)
    a = {x.meta.id: x for x in repartir(150_000_00, [viaje, consola], "2026-11")}
    assert a[1].necesaria == 100_000_00
    # El sobrante (50k) se reparte por prioridad: consola (alta, peso 3) 30k, viaje (media, peso 2) 20k.
    assert a[1].mensual == 120_000_00
    assert a[2].mensual == 30_000_00
    assert a[1].a_tiempo is True
    assert sum(x.mensual for x in a.values()) == 150_000_00


def test_repartir_no_pasa_de_lo_que_falta_y_reparte_por_prioridad():
    casi = Meta(1, "Juego", 100_000_00, 90_000_00, None, prioridad=1)
    alta = Meta(2, "Celular", 1_000_000_00, 0, None, prioridad=1)
    baja = Meta(3, "Ropa", 1_000_000_00, 0, None, prioridad=3)
    a = {x.meta.id: x for x in repartir(400_000_00, [casi, alta, baja], "2026-11")}
    assert a[1].mensual == 10_000_00
    assert sum(x.mensual for x in a.values()) == 400_000_00
    assert a[2].mensual > a[3].mensual * 2  # Alta pesa 3, baja 1.


def test_repartir_ignora_metas_completas_y_avisa_si_no_llega_a_tiempo():
    lista = Meta(1, "Lista", 100, 100)
    viaje = Meta(2, "Viaje", 1_200_000_00, 0, date(2026, 12, 31))  # Necesita 600k/mes.
    a = repartir(100_000_00, [lista, viaje], "2026-11")
    assert [x.meta.id for x in a] == [2]
    assert a[0].mensual == 100_000_00
    assert a[0].periodo_estimado == "2027-10"
    assert a[0].a_tiempo is False


def test_capacidad_ahorro():
    e = EntradaAhorro(periodo="2026-11", ingreso=3_000_000_00, pagos_deuda=600_000_00, servicios=400_000_00,
                      dia_a_dia=800_000_00, gastos_previstos=200_000_00, pct_ahorro=0.30,
                      saldo_favor=500_000_00, falta_reserva=200_000_00,
                      fechas_ingreso=[date(2026, 11, 15), date(2026, 11, 30)])
    c = capacidad_ahorro(e)
    assert c.capacidad == 1_000_000_00
    assert c.sugerido == 300_000_00
    assert c.extra_saldo_favor == 300_000_00
    assert c.por_fecha == [(date(2026, 11, 15), 150_000_00), (date(2026, 11, 30), 150_000_00)]


def test_capacidad_con_deficit_no_sugiere_ahorro():
    e = EntradaAhorro("2026-11", 1_000_00, 2_000_00, 0, 0, 0, 0.3, 0, 0)
    c = capacidad_ahorro(e)
    assert c.sugerido == 0 and c.deficit == 1_000_00


# ---------------------------------------------------------------- repositorio

def test_saldo_a_favor_pasa_al_mes_siguiente(repo):
    repo.registrar_ingreso(date(2026, 10, 15), 2_000_000_00)
    repo.registrar_compra(date(2026, 10, 20), "Mercado", None, 500_000_00, "efectivo")
    repo.movimiento_reserva(date(2026, 10, 20), "aporte", 300_000_00)
    repo.movimiento_reserva(date(2026, 10, 25), "rendimiento", 1_000_00)  # No viene del bolsillo.
    meta = repo.guardar_meta_ahorro(None, "Viaje", "viaje", 1_000_000_00)
    repo.abonar_meta(meta, date(2026, 10, 28), 200_000_00)
    repo.abonar_meta(meta, date(2026, 10, 28), 50_000_00, externo=True)  # Ya estaba ahorrado.

    octubre = repo.flujo_mes("2026-10")
    assert octubre["saldo_favor"] == 0
    assert octubre["disponible"] == 1_000_000_00
    noviembre = repo.flujo_mes("2026-11")
    assert noviembre["entro"] == 0 and noviembre["salio"] == 0  # El mes nuevo arranca en cero…
    assert noviembre["saldo_favor"] == 1_000_000_00             # …pero trae el saldo a favor.

    p = repo.patrimonio(date(2026, 11, 1))
    assert p["cajas"] == 250_000_00
    assert p["reserva"] == 301_000_00
    assert p["patrimonio"] == 1_000_000_00 + 301_000_00 + 250_000_00


def test_retiro_con_compra_no_cambia_el_disponible(repo):
    repo.registrar_ingreso(date(2026, 10, 1), 1_000_000_00)
    meta = repo.guardar_meta_ahorro(None, "Consola", "tecnologia", 300_000_00)
    repo.abonar_meta(meta, date(2026, 10, 2), 300_000_00)
    antes = repo.saldo_disponible(date(2026, 10, 31))
    mov = repo.retirar_meta(meta, date(2026, 10, 10), 300_000_00, compra=("Consola", None))
    assert repo.saldo_disponible(date(2026, 10, 31)) == antes
    assert repo.resumen_mes("2026-10")["compras_efectivo"] == 300_000_00
    with pytest.raises(ValueError):
        repo.retirar_meta(meta, date(2026, 10, 11), 1)
    repo.eliminar_movimiento_ahorro(mov)
    assert repo.resumen_mes("2026-10")["compras_efectivo"] == 0
    assert repo.meta_ahorro(meta)["ahorrado"] == 300_000_00


def test_no_elimina_caja_con_plata_ni_abono_ya_retirado(repo):
    meta = repo.guardar_meta_ahorro(None, "Tenis", "personal", 100_000_00)
    abono = repo.abonar_meta(meta, date(2026, 10, 1), 50_000_00)
    repo.retirar_meta(meta, date(2026, 10, 2), 50_000_00)
    with pytest.raises(ValueError):
        repo.eliminar_movimiento_ahorro(abono)
    repo.abonar_meta(meta, date(2026, 10, 3), 10_000_00)
    with pytest.raises(ValueError):
        repo.eliminar_meta_ahorro(meta)


def test_ajustar_disponible(repo):
    repo.registrar_ingreso(date(2026, 10, 1), 100_000_00)
    assert repo.ajustar_disponible(date(2026, 10, 31), 150_000_00) == 50_000_00
    assert repo.saldo_disponible(date(2026, 10, 31)) == 150_000_00


def test_plan_ahorro_usa_gastos_del_mes_siguiente(repo):
    repo.guardar_fuente(None, "Sueldo", 3_000_000_00, "15,30", False, "activa")
    repo.guardar_servicio(None, "Arriendo", None, 1_000_000_00, 5)
    repo.guardar_gasto_previsto(None, "2026-11", "Regalo", 200_000_00)
    repo.guardar_config({"dia_a_dia_estimado": "800000"})
    meta = repo.guardar_meta_ahorro(None, "Viaje", "viaje", 1_200_000_00, date(2027, 4, 30))
    cap, asignaciones = repo.plan_ahorro("2026-11", hoy=date(2026, 10, 31))
    assert cap.gastos == 1_000_000_00 + 800_000_00 + 200_000_00
    assert cap.capacidad == 1_000_000_00
    assert cap.sugerido == round(1_000_000_00 * 0.50)  # Sin deuda: 30 % ahorro + 20 % del abono extra.
    assert len(cap.por_fecha) == 2
    assert asignaciones[0].meta.id == meta and asignaciones[0].necesaria == 200_000_00


def test_montos_sugeridos_en_pesos_enteros():
    e = EntradaAhorro("2026-11", 3_123_457_89, 0, 0, 0, 0, 0.3, 0, 0,
                      fechas_ingreso=[date(2026, 11, 15), date(2026, 11, 30), date(2026, 11, 20)])
    c = capacidad_ahorro(e)
    assert c.sugerido == 937_000_00  # Hacia abajo, a miles.
    assert sum(m for _, m in c.por_fecha) == c.sugerido
    metas = [Meta(1, "A", 999_999_99, 0, date(2027, 2, 1)), Meta(2, "B", 5_000_000_00, 0, prioridad=1),
             Meta(3, "C", 5_000_000_00, 0, prioridad=3)]
    a = repartir(c.sugerido, metas, "2026-11")
    assert sum(x.mensual for x in a) == c.sugerido
    assert all(x.mensual % 100 == 0 for x in a)


def test_exportar_incluye_ahorros(repo, tmp_path):
    from openpyxl import load_workbook
    from finanzas.exportar import exportar_excel
    meta = repo.guardar_meta_ahorro(None, "Viaje", "viaje", 1_000_000_00)
    repo.abonar_meta(meta, date(2026, 10, 1), 100_000_00)
    wb = load_workbook(exportar_excel(repo, tmp_path / "f.xlsx"))
    assert {"Cajas de ahorro", "Movimientos ahorro", "Patrimonio"} <= set(wb.sheetnames)
