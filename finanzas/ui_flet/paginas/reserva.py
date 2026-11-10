"""Reserva del mes adelantado (Cajita) con su rendimiento."""

from datetime import date

import flet as ft

from ...campos import Campo, hoy_texto, pesos
from ...dinero import formato, porcentaje, tasa as _tasa
from ...fechas import nombre_periodo, periodo, periodo_siguiente
from ..componentes import Pagina, Tabla, TarjetaCifra, barra_botones, boton, requiere, seccion, tarjeta
from ..tema import MORADO, NARANJA, VERDE

TIPOS = {"aporte": "Aporte", "uso": "Pago de deuda", "rendimiento": "Rendimiento", "retiro": "Retiro"}
COL = {"xs": 12, "md": 4}


class PaginaReserva(Pagina):
    titulo = "Reserva (Cajita)"

    def construir(self) -> None:
        self.saldo = TarjetaCifra("🏦 Tienes en la reserva", VERDE, COL)
        self.meta = TarjetaCifra("🎯 Deudas y servicios del mes siguiente", MORADO, COL)
        self.rendimiento = TarjetaCifra("📈 Rendimiento estimado al mes", col=COL)
        self.comparacion = ft.Text("", size=13)
        self.tabla = Tabla([("Fecha", "centro"), ("Movimiento", "izq"), ("Valor", "der"), ("Notas", "izq")],
                           vacio="Aún no hay movimientos en la reserva.")
        self.agregar(
            ft.ResponsiveRow([self.saldo.vista, self.meta.vista, self.rendimiento.vista], spacing=14, run_spacing=14),
            tarjeta(ft.Row([ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, color=ft.Colors.PRIMARY), self.comparacion],
                           vertical_alignment=ft.CrossAxisAlignment.START)),
            seccion("Movimientos",
                    barra_botones(boton("Aporte", lambda _e: self._movimiento("aporte"), ft.Icons.ADD),
                                  boton("Retiro", lambda _e: self._movimiento("retiro"), ft.Icons.REMOVE, "tonal"),
                                  boton("Registrar rendimiento", lambda _e: self._movimiento("rendimiento"),
                                        ft.Icons.TRENDING_UP, "tonal"),
                                  boton("Eliminar", self._eliminar, ft.Icons.DELETE_OUTLINE, "borde")),
                    self.tabla.vista),
        )
        self.comparacion.expand = True

    def refrescar(self) -> None:
        repo = self.repo
        sig = periodo_siguiente(periodo(date.today()))
        meta = repo.meta_mes_adelantado(sig)  # Cuotas + servicios del mes siguiente.
        saldo = repo.saldo_reserva()
        self.saldo.mostrar(formato(saldo), f"{porcentaje(min(1, saldo / meta), 0)} del pago de {nombre_periodo(sig)}"
                           if meta else "No hay pagos de deuda el mes siguiente")
        self.meta.mostrar(formato(meta), "Faltan " + formato(meta - saldo) if saldo < meta else "✅ Cubierto",
                          VERDE if saldo >= meta else NARANJA)
        tasa = repo.config_num("tasa_cajita_ea")
        self.rendimiento.mostrar(formato(repo.rendimiento_reserva_estimado()),
                                 f"Con la tasa de tu Cajita: {_tasa(tasa)} % E.A." if tasa else
                                 "Configura la tasa de tu Cajita en Configuración → Parámetros.")
        productos = [p for p in repo.productos() if p["tasa_ea"] > 0]
        if tasa and productos:
            cara = max(productos, key=lambda p: p["tasa_ea"])
            self.comparacion.value = (
                f"Tu Cajita rinde {_tasa(tasa)} % E.A. y {cara['nombre']} cobra {_tasa(cara['tasa_ea'])} % E.A. → "
                "La Cajita debe guardar solo lo del pago del mes siguiente. Lo que sobre por encima de eso rinde más "
                "como abono a la deuda que guardado.")
        else:
            self.comparacion.value = (
                "La reserva es la plata que apartas cada vez que cobras para pagar las deudas del mes siguiente. Así "
                "nunca pagas una cuota con el sueldo que acaba de llegar.")
        self.tabla.cargar([(m["id"], [m["fecha"], TIPOS[m["tipo"]],
                                      (pesos(m["monto"]), VERDE if m["tipo"] in ("aporte", "rendimiento") else None),
                                      m["notas"]]) for m in repo.movimientos_reserva()])

    def _movimiento(self, tipo: str) -> None:
        campos = [Campo("fecha", "Fecha", "fecha", defecto=hoy_texto()), Campo("monto", "Valor", "monto"),
                  Campo("notas", "Notas", opcional=True)]

        def guardar(v: dict) -> None:
            self.repo.movimiento_reserva(v["fecha"], tipo, v["monto"], v["notas"] or "")
            self.cambio()

        self.formulario(TIPOS[tipo], campos, guardar)

    async def _eliminar(self, _e=None) -> None:
        id_ = requiere(self.tabla, self, "Selecciona un movimiento en la tabla.")
        if id_ is not None and await self.confirmar("¿Eliminar este movimiento?", si="Eliminar", peligro=True):
            try:
                self.repo.eliminar_movimiento_reserva(id_)
            except ValueError as e:
                return self.error(str(e))
            self.cambio()
