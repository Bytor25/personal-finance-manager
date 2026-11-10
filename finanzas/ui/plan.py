"""Plan del ingreso: cómo repartir cada pago recibido."""

from datetime import date

import customtkinter as ctk

from ..dinero import a_centavos, formato, porcentaje
from ..fechas import nombre_periodo, periodo, periodo_siguiente
from ..plan import MENSAJE_NIVEL, NOMBRE_NIVEL, calcular_plan
from .app import Pagina
from .widgets import (COLOR_NIVEL, FONDO_TARJETA, FUENTE_NORMAL, FUENTE_PEQUENA, FUENTE_SUBTITULO, GRIS,
                      ICONO_NIVEL, NARANJA, ROJO, VERDE, Tabla, color, confirmar, error, hoy_texto, parsear_fecha,
                      pesos)

SIMULAR = "Simular un ingreso…"


class PaginaPlan(Pagina):
    titulo = "Plan del ingreso"

    def construir(self) -> None:
        self.seccion("¿Qué ingreso quieres repartir?",
                     "Elige un ingreso registrado o simula uno. El plan aparta primero lo que vence antes de tu "
                     "próximo ingreso, luego el día a día, luego la reserva para el pago del mes siguiente, y el "
                     "resto lo reparte según tu nivel de deuda.")
        fila = self.fila_botones()
        self.combo = ctk.CTkComboBox(fila, width=380, state="readonly", command=lambda _v: self._modo())
        self.combo.pack(side="left")
        self.fecha = ctk.CTkEntry(fila, width=120, placeholder_text="Fecha")
        self.monto = ctk.CTkEntry(fila, width=140, placeholder_text="Valor")
        self.esperadas = ctk.CTkCheckBox(fila, text="Incluir ingresos esperados (aún no confirmados)")
        self.esperadas.pack(side="left", padx=12)
        ctk.CTkButton(fila, text="Calcular plan", command=self._calcular).pack(side="left")

        self.cabecera = ctk.CTkFrame(self, fg_color=FONDO_TARJETA, corner_radius=12)
        self.cabecera.pack(fill="x", padx=24, pady=8)

        self.seccion("Reparto sugerido")
        self.tabla = self.bloque(lambda m: Tabla(m, [("Concepto", 420, "izq"), ("Valor", 140, "der"),
                                                     ("Nota", 380, "izq")], alto=8))
        acciones = self.fila_botones()
        self.boton_reserva = ctk.CTkButton(acciones, text="Apartar en la reserva", state="disabled",
                                           command=self._apartar)
        self.boton_reserva.pack(side="left")
        self.boton_cajas = ctk.CTkButton(acciones, text="Abonar el ahorro a mis cajas", state="disabled",
                                         command=self._abonar_cajas)
        self.boton_cajas.pack(side="left", padx=6)
        ctk.CTkLabel(acciones, text="Regístralo cuando hagas la transferencia.",
                     text_color=GRIS).pack(side="left", padx=10)

        self.seccion("¿Cuánto pagar a cada tarjeta?",
                     "Mínimo = lo obligatorio. Recomendado = mínimo + el abono extra del plan (va primero a la deuda "
                     "más cara, o a la más pequeña si elegiste «bola de nieve» en Configuración).")
        self.t_tarjetas = self.bloque(lambda m: Tabla(
            m, [("Tarjeta / crédito", 180, "izq"), ("Fecha límite", 110, "centro"), ("Mínimo", 120, "der"),
                ("Recomendado", 120, "der"), ("Total", 120, "der"), ("Si pagas solo el mínimo", 200, "der")], alto=4))
        self.plan = None

    def refrescar(self) -> None:
        self._ingresos = {f"{i['fecha']} · {formato(i['monto'])} · {i['fuente'] or 'Sin fuente'}": i
                          for i in self.repo.ingresos()[:15]}
        valores = list(self._ingresos) + [SIMULAR]
        self.combo.configure(values=valores)
        if self.combo.get() not in valores:
            self.combo.set(valores[0])
        self._modo()
        self._calcular(silencioso=True)

    def _modo(self) -> None:
        if self.combo.get() == SIMULAR:
            if not self.fecha.winfo_manager():
                self.fecha.pack(side="left", padx=(8, 0), after=self.combo)
                self.monto.pack(side="left", padx=(8, 0), after=self.fecha)
                if not self.fecha.get():
                    self.fecha.insert(0, hoy_texto())
        else:
            self.fecha.pack_forget()
            self.monto.pack_forget()

    def _calcular(self, silencioso: bool = False) -> None:
        try:
            if self.combo.get() == SIMULAR:
                fecha = parsear_fecha(self.fecha.get())
                monto = a_centavos(self.monto.get())
            else:
                ingreso = self._ingresos.get(self.combo.get())
                if ingreso is None:
                    self._limpiar("Registra un ingreso en «Ingresos y compras» o elige «Simular un ingreso…».")
                    return
                fecha, monto = date.fromisoformat(ingreso["fecha"]), ingreso["monto"]
        except ValueError as e:
            if not silencioso:
                error(self, str(e))
            return
        entrada = self.repo.entrada_plan(fecha, monto, bool(self.esperadas.get()))
        self.plan = calcular_plan(entrada, self.repo.config_plan())
        self._mostrar()

    def _limpiar(self, mensaje: str) -> None:
        for w in self.cabecera.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.cabecera, text=mensaje, text_color=GRIS).pack(padx=14, pady=14)
        self.tabla.cargar([])
        self.t_tarjetas.cargar([])
        self.boton_reserva.configure(state="disabled")
        self.boton_cajas.configure(state="disabled")

    def _mostrar(self) -> None:
        p, e = self.plan, self.plan.entrada
        for w in self.cabecera.winfo_children():
            w.destroy()
        sig = periodo_siguiente(periodo(e.fecha))
        ctk.CTkLabel(self.cabecera, text=f"{ICONO_NIVEL[p.nivel]} Endeudamiento {NOMBRE_NIVEL[p.nivel]}: "
                                         f"{porcentaje(p.ratio)} de tu ingreso se va en pagos de deuda",
                     font=FUENTE_SUBTITULO, text_color=COLOR_NIVEL[p.nivel], anchor="w").pack(fill="x", padx=14,
                                                                                         pady=(12, 0))
        ctk.CTkLabel(self.cabecera, text=MENSAJE_NIVEL[p.nivel], anchor="w").pack(fill="x", padx=14)
        datos = (f"Ingreso: {formato(e.ingreso)} el {e.fecha.isoformat()}   ·   Próximo ingreso: "
                 f"{e.proximo_ingreso.isoformat()}   ·   Ingreso mensual estimado: {formato(e.ingreso_mensual)}   ·   "
                 f"Pagos de deuda en {nombre_periodo(sig)}: {formato(e.pagos_mes_siguiente)}")
        ctk.CTkLabel(self.cabecera, text=datos, text_color=GRIS, font=FUENTE_PEQUENA, anchor="w", justify="left",
                     wraplength=1000).pack(fill="x", padx=14, pady=(4, 0))

        estado = ("✅ Mes adelantado al día" if p.al_dia else "🔨 Construyendo la reserva del mes adelantado")
        ctk.CTkLabel(self.cabecera, text=f"{estado}: tendrás {formato(p.reserva_despues)} de "
                                         f"{formato(p.meta_reserva)} para los pagos hasta fin de {nombre_periodo(sig)}",
                     font=FUENTE_NORMAL, text_color=VERDE if p.al_dia else NARANJA, anchor="w"
                     ).pack(fill="x", padx=14, pady=(8, 0))
        barra = ctk.CTkProgressBar(self.cabecera, height=12, progress_color=color(VERDE if p.al_dia else NARANJA))
        barra.set(p.progreso_reserva)
        barra.pack(fill="x", padx=14, pady=4)
        if p.desde_reserva:
            ctk.CTkLabel(self.cabecera, text=f"Paga {formato(p.desde_reserva)} de deudas con la plata que ya tienes "
                                             "en la reserva.", anchor="w").pack(fill="x", padx=14)
        if p.deficit:
            ctk.CTkLabel(self.cabecera, text=f"⚠ Este ingreso no alcanza: faltan {formato(p.deficit)} para cubrir lo "
                                             "que vence antes del próximo ingreso y el día a día. Recorta gastos "
                                             "«deseo», usa ahorro, o paga el mínimo.",
                         text_color=ROJO, anchor="w", justify="left", wraplength=1000
                         ).pack(fill="x", padx=14, pady=(4, 0))
        ctk.CTkFrame(self.cabecera, height=10, fg_color="transparent").pack()

        self.tabla.cargar([(i, [pa.concepto, pesos(pa.monto), pa.nota]) for i, pa in enumerate(p.partidas)])
        aporte = p.monto("reserva")
        self.boton_reserva.configure(state="normal" if aporte > 0 else "disabled",
                                     text=f"Apartar {formato(aporte)} en la reserva" if aporte else
                                     "Apartar en la reserva")

        ahorro = p.monto("ahorro")
        hay_cajas = bool(self.repo.metas_para_reparto())
        self.boton_cajas.configure(state="normal" if ahorro > 0 and hay_cajas else "disabled",
                                   text=f"Abonar {formato(ahorro)} a mis cajas" if ahorro and hay_cajas else
                                   "Abonar el ahorro a mis cajas")

        filas = []
        for d in self.repo.recomendacion_pagos(p.monto("abono"), e.fecha):
            filas.append((d["producto"]["id"], [
                d["producto"]["nombre"], d["fecha_limite"].isoformat() if d["fecha_limite"] else "Vencido",
                pesos(d["minimo"]), pesos(d["recomendado"]), pesos(d["total"]),
                f"+{formato(d['interes_si_minimo'])} de intereses" if d["interes_si_minimo"] else "—"]))
        self.t_tarjetas.cargar(filas)

    def _apartar(self) -> None:
        if not self.plan:
            return
        aporte = self.plan.monto("reserva")
        if aporte <= 0:
            return
        if confirmar(self, f"¿Registrar un aporte de {formato(aporte)} a la reserva (Cajita)?"):
            self.repo.movimiento_reserva(self.plan.entrada.fecha, "aporte", aporte, "Aporte del plan del ingreso")
            self._calcular()

    def _abonar_cajas(self) -> None:
        if not self.plan:
            return
        from .ahorros import dialogo_repartir
        dialogo_repartir(self, self.plan.monto("ahorro"), self.plan.entrada.fecha, "Abonar el ahorro a mis cajas")
