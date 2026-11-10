"""Reserva del mes adelantado (Cajita) con su rendimiento."""

from datetime import date

import customtkinter as ctk

from ..dinero import formato, porcentaje, tasa as _tasa
from ..fechas import nombre_periodo, periodo, periodo_siguiente
from .app import Pagina
from .widgets import (FONDO_TARJETA, MORADO, NARANJA, VERDE, Campo, Formulario, Tabla, TarjetaCifra,
                      confirmar, error, hoy_texto, pesos)

TIPOS = {"aporte": "Aporte", "uso": "Pago de deuda", "rendimiento": "Rendimiento", "retiro": "Retiro"}


class PaginaReserva(Pagina):
    titulo = "Reserva (Cajita)"

    def construir(self) -> None:
        fila = ctk.CTkFrame(self, fg_color="transparent")
        fila.pack(fill="x", padx=24, pady=4)
        fila.grid_columnconfigure((0, 1, 2), weight=1, uniform="r")
        self.saldo = TarjetaCifra(fila, "🏦 Tienes en la reserva", VERDE)
        self.meta = TarjetaCifra(fila, "🎯 Deudas y servicios del mes siguiente", MORADO)
        self.rendimiento = TarjetaCifra(fila, "📈 Rendimiento estimado al mes")
        for i, t in enumerate((self.saldo, self.meta, self.rendimiento)):
            t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0))
        self.comparacion = ctk.CTkLabel(self, text="", anchor="w", justify="left", wraplength=1000,
                                        fg_color=FONDO_TARJETA, corner_radius=12)
        self.comparacion.pack(fill="x", padx=24, pady=8, ipady=10, ipadx=10)

        botones = self.fila_botones()
        ctk.CTkButton(botones, text="+ Aporte", command=lambda: self._movimiento("aporte")).pack(side="left")
        ctk.CTkButton(botones, text="Retiro", command=lambda: self._movimiento("retiro")).pack(side="left", padx=6)
        ctk.CTkButton(botones, text="Registrar rendimiento", command=lambda: self._movimiento("rendimiento")
                      ).pack(side="left", padx=6)
        ctk.CTkButton(botones, text="Eliminar", fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self._eliminar).pack(side="left", padx=6)
        self.tabla = self.bloque(lambda m: Tabla(m, [("Fecha", 100, "centro"), ("Movimiento", 160, "izq"),
                                                     ("Valor", 140, "der"), ("Notas", 400, "izq")], alto=14))

    def refrescar(self) -> None:
        repo = self.repo
        hoy = date.today()
        sig = periodo_siguiente(periodo(hoy))
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
            texto = (f"Tu Cajita rinde {_tasa(tasa)} % E.A. y {cara['nombre']} cobra {_tasa(cara['tasa_ea'])} % E.A. "
                     "→ La Cajita debe guardar solo lo del pago del mes siguiente. Lo que sobre por encima de eso "
                     "rinde más como abono a la deuda que guardado.")
        else:
            texto = ("La reserva es la plata que apartas cada vez que cobras para pagar las deudas del mes siguiente. "
                     "Así nunca pagas una cuota con el sueldo que acaba de llegar.")
        self.comparacion.configure(text=texto)
        self.tabla.cargar([(m["id"], [m["fecha"], TIPOS[m["tipo"]], pesos(m["monto"]), m["notas"]])
                           for m in repo.movimientos_reserva()])

    def _movimiento(self, tipo: str) -> None:
        campos = [Campo("fecha", "Fecha", "fecha", defecto=hoy_texto()),
                  Campo("monto", "Valor", "monto"),
                  Campo("notas", "Notas", opcional=True)]

        def guardar(v: dict) -> None:
            self.repo.movimiento_reserva(v["fecha"], tipo, v["monto"], v["notas"] or "")
            self.refrescar()

        Formulario(self, TIPOS[tipo], campos, guardar)

    def _eliminar(self) -> None:
        id_ = self.tabla.seleccionado()
        if id_ is None:
            return error(self, "Selecciona un movimiento.")
        if confirmar(self, "¿Eliminar este movimiento?"):
            try:
                self.repo.eliminar_movimiento_reserva(id_)
            except ValueError as e:
                return error(self, str(e))
            self.refrescar()

