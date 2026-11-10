"""Exportación de solo lectura a Excel (la fuente de verdad es la base SQLite)."""

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .repositorio import Repositorio

FORMATO_PESOS = '"$"#,##0'
ENCABEZADO = PatternFill("solid", fgColor="6D28D9")


def _hoja(wb: Workbook, titulo: str, columnas: list[str], filas: list[list], montos: set[int]) -> None:
    ws = wb.create_sheet(titulo)
    ws.append(columnas)
    for celda in ws[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = ENCABEZADO
    for fila in filas:
        ws.append([v / 100 if i in montos and v is not None else v for i, v in enumerate(fila)])
    for i in montos:
        for celda in ws.iter_cols(min_col=i + 1, max_col=i + 1, min_row=2):
            for c in celda:
                c.number_format = FORMATO_PESOS
    for i, col in enumerate(columnas, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(12, len(col) + 4)
    ws.freeze_panes = "A2"


def exportar_excel(repo: Repositorio, destino: Path) -> Path:
    wb = Workbook()
    info = wb.active
    info.title = "Información"
    info.append(["Exportado el", date.today().isoformat()])
    info.append(["Este archivo es solo de lectura: los cambios aquí no se reflejan en la aplicación."])

    _hoja(wb, "Ingresos", ["Fecha", "Fuente", "Tipo", "Descripción", "Monto"],
          [[i["fecha"], i["fuente"], i["tipo"], i["descripcion"], i["monto"]] for i in repo.ingresos()], {4})
    _hoja(wb, "Compras", ["Fecha", "Descripción", "Categoría", "Cómo pagué", "Tarjeta", "Cuotas", "Monto"],
          [[c["fecha"], c["descripcion"], c["categoria"], c["medio"], c["producto"], c["num_cuotas"], c["monto"]]
           for c in repo.compras()], {6})
    _hoja(wb, "Pagos tarjetas", ["Fecha", "Tarjeta/crédito", "Tipo", "Monto", "A capital", "Intereses y cargos",
                                 "Abono extra", "Saldo a favor", "Desde reserva", "Canal"],
          [[p["fecha"], p["producto"], p["tipo"], p["monto"], p["a_capital"], p["a_costos"], p["abono_extra"],
            p["saldo_favor"], "Sí" if p["desde_reserva"] else "No", p["canal"]] for p in repo.pagos()], {3, 4, 5, 6, 7})

    filas = []
    for d in repo.creditos(solo_activos=False):
        cr = d["credito"]
        for c in repo.cronograma_credito(cr["id"]):
            total = c["capital"] + c["interes"] + c["otros"] + c["mora"] + c["cobranza"]
            filas.append([cr["producto"], cr["descripcion"], cr["estado"], c["numero"], c["fecha"], c["capital"],
                          c["interes"], c["otros"], c["mora"] + c["cobranza"], total, c["pagado"], c["estado"]])
    _hoja(wb, "Cronogramas", ["Tarjeta/crédito", "Deuda", "Estado deuda", "Cuota #", "Fecha", "Capital",
                              "Intereses", "Cargos", "Mora y cobranza", "Total", "Pagado", "Estado cuota"], filas,
          {5, 6, 7, 8, 9, 10})
    _hoja(wb, "Extractos", ["Tarjeta", "Corte", "Fecha límite", "Capital del mes", "Intereses", "Pago mínimo",
                            "Deuda restante", "Pago total"],
          [[e["producto"], e["fecha_corte"], e["fecha_limite"], e["capital_mes"], e["intereses"], e["pago_minimo"],
            e["deuda_restante"], e["pago_total"]] for e in repo.extractos()], {3, 4, 5, 6, 7})
    _hoja(wb, "Mora y cobranza", ["Tarjeta/crédito", "Deuda", "Tipo", "Desde", "Hasta", "Base", "Tasa E.A.", "Monto"],
          [[m["producto"], m["descripcion"], m["tipo"], m["desde"], m["hasta"], m["base"], m["tasa_ea"], m["monto"]]
           for m in repo._todos("SELECT cm.*, p.nombre AS producto, cr.descripcion FROM cargos_mora cm "
                                "JOIN creditos cr ON cr.id = cm.credito_id "
                                "JOIN productos_credito p ON p.id = cr.producto_id ORDER BY cm.desde")], {5, 7})
    _hoja(wb, "Servicios", ["Servicio", "Categoría", "Día de vencimiento", "Monto estimado"],
          [[s["nombre"], s["categoria"], s["dia_vencimiento"], s["monto_estimado"]] for s in repo.servicios()], {3})
    _hoja(wb, "Reserva", ["Fecha", "Tipo", "Monto", "Notas"],
          [[m["fecha"], m["tipo"], m["monto"], m["notas"]] for m in repo.movimientos_reserva()], {2})
    _hoja(wb, "Cajas de ahorro", ["Caja", "Tipo", "Estado", "Meta", "Ahorrado", "Falta", "Fecha objetivo", "Notas"],
          [[m["nombre"], m["tipo"], m["estado"], m["objetivo"], m["ahorrado"], max(0, m["objetivo"] - m["ahorrado"]),
            m["fecha_objetivo"], m["notas"]] for m in repo.metas_ahorro(True)], {3, 4, 5})
    _hoja(wb, "Movimientos ahorro", ["Fecha", "Caja", "Tipo", "Monto", "Ya estaba ahorrado", "Notas"],
          [[m["fecha"], m["meta"], m["tipo"], m["monto"], "Sí" if m["externo"] else "No", m["notas"]]
           for m in repo.movimientos_ahorro()], {3})
    _hoja(wb, "Patrimonio", ["Mes", "Disponible", "Reserva", "Cajas", "Deuda", "Patrimonio"],
          [[p["periodo"], p["disponible"], p["reserva"], p["cajas"], p["deuda"], p["patrimonio"]]
           for p in repo.historial_patrimonio(24)], {1, 2, 3, 4, 5})
    _hoja(wb, "Resumen mensual", ["Mes", "Entró", "Salió", "Compras con tarjeta", "Pagos a deuda",
                                  "Costo de la deuda", "% del ingreso en deuda"],
          [[h["periodo"], h["entro"], h["salio"], h["compras_tarjeta"], h["pagos_credito"], h["costo_deuda"],
            round(h["ratio"] * 100, 1) if h["ratio"] is not None else None] for h in repo.historial(24)],
          {1, 2, 3, 4, 5})

    _hoja(wb, "Historial de cambios", ["Fecha y hora", "Qué", "Id", "Acción", "Antes", "Después"],
          [[h["creado"], h["entidad"], h["entidad_id"], h["accion"], h["antes"], h["despues"]]
           for h in repo.historial_cambios(5000)], set())
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino
