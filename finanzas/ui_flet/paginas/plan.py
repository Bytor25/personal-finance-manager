"""Plan del ingreso: cómo repartir cada pago recibido (o uno simulado)."""

from datetime import date

import flet as ft

from ...campos import hoy_texto, parsear_fecha, pesos
from ...dinero import a_centavos, formato, porcentaje
from ...fechas import nombre_periodo, periodo, periodo_siguiente
from ...plan import MENSAJE_NIVEL, NOMBRE_NIVEL, calcular_plan
from ..componentes import Pagina, Tabla, ayuda, barra_botones, boton, contenedor, seccion, tarjeta, texto
from ..tema import COLOR_NIVEL, GRIS, ICONO_NIVEL, NARANJA, ROJO, VERDE, c

SIMULAR = "__simular__"
COLOR_PARTIDA = {"credito": ("#7c3aed", "#a78bfa"), "servicios": ("#0369a1", "#38bdf8"),
                 "dia_a_dia": ("#c2410c", "#fb923c"), "reserva": ("#a16207", "#facc15"),
                 "ahorro": ("#15803d", "#4ade80"), "abono": ("#db2777", "#f472b6"), "libre": ("#6b7280", "#9ca3af")}
PASOS = [
    ("A", "Deudas que vencen antes del próximo pago",
     "Las cuotas de tarjetas y créditos que vencen desde que llega este ingreso hasta el día anterior al próximo "
     "(incluye las vencidas). Lo que vence el mismo día del próximo ingreso se paga con ese ingreso."),
    ("B", "Servicios", "Los servicios que vencen en ese mismo tramo y aún no pagaste (si hiciste un pago parcial, "
                       "solo lo que falta). A y B se pagan primero con la reserva (Cajita); lo que falte sale de "
                       "este ingreso."),
    ("C", "Día a día", "El promedio de lo que gastaste en efectivo los últimos 3 meses (sin servicios), dividido "
                       "entre los pagos que recibes al mes."),
    ("D", "Reserva «mes adelantado»", "La meta es tener ahorradas las cuotas y los servicios que vencen desde tu "
                                      "próximo ingreso hasta el fin del mes siguiente. Lo que falta se reparte entre "
                                      "los pagos que te quedan este mes."),
    ("E", "Lo que sobra (si alcanza)", "Se reparte entre ahorro, abono extra a la deuda y libre según tu nivel de "
                                       "endeudamiento (Configuración → Parámetros)."),
]


class PaginaPlan(Pagina):
    titulo = "Plan del ingreso"

    def construir(self) -> None:
        self.combo = ft.Dropdown(label="Ingreso a repartir", width=420, on_select=self._al_elegir, menu_width=420)
        self.fecha = ft.TextField(label="Fecha", width=150, value=hoy_texto(), visible=False,
                                  on_submit=lambda _e: self._calcular())
        self.monto = ft.TextField(label="Valor", prefix="$ ", width=170, visible=False,
                                  keyboard_type=ft.KeyboardType.NUMBER, on_submit=lambda _e: self._calcular())
        self.esperadas = ft.Checkbox(label="Incluir ingresos esperados (aún no confirmados)",
                                     on_change=lambda _e: self._calcular())
        self.boton_calcular = boton("Calcular plan", lambda _e: self._calcular(), ft.Icons.CALCULATE)
        self.aviso_simulacion = ft.Container(
            ft.Row([ft.Icon(ft.Icons.SCIENCE_OUTLINED, color=c(NARANJA), size=18),
                    ft.Text("Estás simulando: nada se guarda. Ojo: los botones «Apartar en la reserva» y «Abonar a "
                            "mis cajas» sí registran movimientos reales.", size=12, expand=True)], spacing=8),
            bgcolor=ft.Colors.with_opacity(0.10, c(NARANJA)), border_radius=10, padding=10, visible=False)

        self.cabecera = contenedor()
        self.cubre = contenedor()
        self.barra_reparto = ft.Row(spacing=0, height=14)
        self.leyenda = ft.Row(wrap=True, spacing=14, run_spacing=4)
        self.tabla = Tabla([("Concepto", "izq"), ("Valor", "der"), ("Nota", "izq")])
        self.boton_reserva = boton("Apartar en la reserva", self._apartar, ft.Icons.ACCOUNT_BALANCE,
                                   deshabilitado=True)
        self.boton_cajas = boton("Abonar el ahorro a mis cajas", self._abonar_cajas, ft.Icons.SAVINGS, "tonal",
                                 deshabilitado=True)
        self.t_tarjetas = Tabla([("Tarjeta / crédito", "izq"), ("Fecha límite", "centro"), ("Mínimo", "der"),
                                 ("Recomendado", "der"), ("Total", "der"), ("Si pagas solo el mínimo", "der")],
                                vacio="No hay pagos de tarjetas o créditos pendientes.")

        explicacion = ft.ExpansionTile(
            title=ft.Text("¿Cómo funciona el plan y la simulación?", weight=ft.FontWeight.W_600),
            leading=ft.Icon(ft.Icons.HELP_OUTLINE),
            controls=[ft.Container(ft.Column([
                ft.Text("«Simular un ingreso…» responde: si me llegara esta plata este día, ¿cómo la reparto? Usa "
                        "tus deudas, servicios y reserva reales; solo el ingreso es imaginario.", size=13),
                ft.Text("Ejemplo: cobras el 15 y el 30, y tienes servicios el 5, 7, 10 y 15. El sueldo del 30 paga "
                        "los del 5, 7 y 10 (el del 15 lo paga el sueldo del 15), tus gastos del día a día y aparta "
                        "en la reserva lo del mes siguiente. Si el sueldo del 30 llega antes (ej. el 28 por fin de "
                        "semana), se toma igual como el del 30.", size=13),
                *[ft.Row([ft.Container(ft.Text(letra, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_PRIMARY),
                                       bgcolor=ft.Colors.PRIMARY, border_radius=14, width=28, height=28,
                                       alignment=ft.Alignment.CENTER),
                          ft.Column([ft.Text(nombre, weight=ft.FontWeight.W_600, size=13), ayuda(detalle)],
                                    spacing=2, expand=True, tight=True)], vertical_alignment=ft.CrossAxisAlignment.START)
                  for letra, nombre, detalle in PASOS],
                ayuda("Si A + B + C suman más que el ingreso, verás un aviso rojo con lo que falta y no se aparta "
                      "reserva ni ahorro. «Incluir ingresos esperados» solo cambia el ingreso mensual estimado (el % "
                      "de endeudamiento), no el valor que repartes."),
            ], spacing=10, tight=True), padding=ft.Padding.only(left=16, right=16, bottom=14))])

        self.agregar(
            seccion("¿Qué ingreso quieres repartir?",
                    ft.Row([self.combo, self.fecha, self.monto, self.boton_calcular], wrap=True, spacing=10,
                           run_spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    self.esperadas, self.aviso_simulacion,
                    explicacion="Elige un ingreso registrado o simula uno."),
            ft.Container(explicacion, bgcolor=ft.Colors.SURFACE_CONTAINER_LOW, border_radius=16),
            tarjeta(self.cabecera, espacio=8),
            tarjeta(self.cubre, espacio=8),
            seccion("Reparto sugerido",
                    ft.Container(self.barra_reparto, border_radius=7, clip_behavior=ft.ClipBehavior.HARD_EDGE),
                    self.leyenda, self.tabla.vista,
                    barra_botones(self.boton_reserva, self.boton_cajas,
                                  ayuda("Regístralo cuando hagas la transferencia."))),
            seccion("¿Cuánto pagar a cada tarjeta?", self.t_tarjetas.vista,
                    explicacion="Mínimo = lo obligatorio. Recomendado = mínimo + el abono extra del plan (va primero a "
                                "la deuda más cara, o a la más pequeña si elegiste «bola de nieve» en Configuración)."),
        )
        self.plan = None

    def refrescar(self) -> None:
        ingresos = self.repo.ingresos()[:15]
        self._ingresos = {str(i["id"]): i for i in ingresos}
        anterior = self.combo.value
        self.combo.options = [ft.DropdownOption(key=str(i["id"]), text=f"{i['fecha']} · {formato(i['monto'])} · "
                                                                       f"{i['fuente'] or 'Sin fuente'}")
                              for i in ingresos] + [ft.DropdownOption(key=SIMULAR, text="🧪 Simular un ingreso…")]
        claves = [o.key for o in self.combo.options]
        self.combo.value = anterior if anterior in claves else claves[0]
        self._modo()
        self._calcular(silencioso=True)

    def _al_elegir(self, _e=None) -> None:
        self._modo()
        self._calcular(silencioso=True)
        self.page.update()

    def _modo(self) -> None:
        simular = self.combo.value == SIMULAR
        self.fecha.visible = self.monto.visible = self.aviso_simulacion.visible = simular

    def _calcular(self, silencioso: bool = False) -> None:
        try:
            if self.combo.value == SIMULAR:
                if not (self.monto.value or "").strip():
                    self._limpiar("Escribe la fecha y el valor del ingreso que quieres simular y presiona "
                                  "«Calcular plan».")
                    return
                fecha = parsear_fecha(self.fecha.value or "")
                monto = a_centavos(self.monto.value or "")
                tipo = "ordinario"
            else:
                ingreso = self._ingresos.get(self.combo.value or "")
                if ingreso is None:
                    self._limpiar("Registra un ingreso en «Ingresos y compras» o elige «Simular un ingreso…».")
                    return
                fecha, monto = date.fromisoformat(ingreso["fecha"]), ingreso["monto"]
                tipo = ingreso["tipo"]
        except ValueError as e:
            if not silencioso:
                self.error(str(e))
            return
        entrada = self.repo.entrada_plan(fecha, monto, bool(self.esperadas.value), tipo)
        self.plan = calcular_plan(entrada, self.repo.config_plan())
        self._mostrar()
        if not silencioso:
            self.page.update()

    def _limpiar(self, mensaje: str) -> None:
        self.cabecera.controls = [ft.Text(mensaje, color=GRIS)]
        self.cubre.controls = []
        self.tabla.cargar([])
        self.t_tarjetas.cargar([])
        self.barra_reparto.controls = []
        self.leyenda.controls = []
        self.boton_reserva.disabled = self.boton_cajas.disabled = True
        self.plan = None

    def _mostrar(self) -> None:
        p, e = self.plan, self.plan.entrada
        sig = periodo_siguiente(periodo(e.fecha))
        color_nivel = COLOR_NIVEL[p.nivel]
        cab = [
            texto(f"{ICONO_NIVEL[p.nivel]} Endeudamiento {NOMBRE_NIVEL[p.nivel]}: {porcentaje(p.ratio)} de tu ingreso "
                  "se va en pagos de deuda", 17, ft.FontWeight.W_600, color_nivel),
            ft.Text(MENSAJE_NIVEL[p.nivel], size=13),
            ft.Row([self._chip(ft.Icons.PAYMENTS, f"Ingreso {formato(e.ingreso)} · {e.fecha.isoformat()}"),
                    self._chip(ft.Icons.EVENT, f"Próximo ingreso {e.proximo_ingreso.isoformat()}"),
                    self._chip(ft.Icons.DATE_RANGE, f"Cubre del {e.fecha.isoformat()} al {e.cubre_hasta.isoformat()}"),
                    self._chip(ft.Icons.CALENDAR_MONTH, f"Ingreso mensual {formato(e.ingreso_mensual)}"),
                    self._chip(ft.Icons.CREDIT_CARD, f"Deuda en {nombre_periodo(sig)}: {formato(e.pagos_mes_siguiente)}")],
                   wrap=True, spacing=8, run_spacing=8),
            ft.Divider(height=10),
            texto(("✅ Mes adelantado al día" if p.al_dia else "🔨 Construyendo la reserva del mes adelantado")
                  + f": tendrás {formato(p.reserva_despues)} de {formato(p.meta_reserva)} para los pagos hasta fin de "
                    f"{nombre_periodo(sig)}", 14, color=VERDE if p.al_dia else NARANJA),
            ft.ProgressBar(value=p.progreso_reserva, bar_height=10, border_radius=5,
                           color=c(VERDE if p.al_dia else NARANJA)),
        ]
        if e.fecha_efectiva:
            cab.append(ft.Text(f"ℹ Llegó el {e.fecha.isoformat()}, unos días antes de tu fecha de pago: se toma como "
                               f"el pago del {e.fecha_efectiva.isoformat()}.", size=13))
        if p.desde_reserva:
            cab.append(ft.Text(f"Paga {formato(p.desde_reserva)} de deudas y servicios con la plata que ya tienes en "
                               "la reserva.", size=13))
        del_ingreso = p.monto("credito") + p.monto("servicios")
        if del_ingreso:
            cab.append(ft.Text(f"{formato(del_ingreso)} de lo que vence antes del próximo ingreso sale de este ingreso "
                               "porque aún no estaba ahorrado en la reserva. Cuando la reserva esté completa, esos "
                               "pagos saldrán de ahí.", size=13, color=GRIS))
        if p.deficit:
            cab.append(ft.Container(texto(
                f"⚠ Este ingreso no alcanza: faltan {formato(p.deficit)} para cubrir lo que vence antes del próximo "
                "ingreso y el día a día. Recorta gastos «deseo», usa ahorro, o paga el mínimo.", 13, color=ROJO),
                bgcolor=ft.Colors.with_opacity(0.10, c(ROJO)), border_radius=10, padding=10))
        self.cabecera.controls = cab
        self._mostrar_cubre(p)

        total = sum(pa.monto for pa in p.partidas) or 1
        self.barra_reparto.controls = [ft.Container(expand=pa.monto, bgcolor=c(COLOR_PARTIDA.get(pa.clave, GRIS)),
                                                    tooltip=f"{pa.concepto}: {formato(pa.monto)}")
                                       for pa in p.partidas if pa.monto > 0]
        self.leyenda.controls = [ft.Row([ft.Container(width=10, height=10, border_radius=3,
                                                      bgcolor=c(COLOR_PARTIDA.get(pa.clave, GRIS))),
                                         ft.Text(f"{pa.concepto.split(' (')[0]} · {porcentaje(pa.monto / total, 0)}",
                                                 size=11, color=GRIS)], spacing=4, tight=True)
                                 for pa in p.partidas if pa.monto > 0]
        self.tabla.cargar([(i, [pa.concepto, pesos(pa.monto), pa.nota]) for i, pa in enumerate(p.partidas)])

        aporte = p.monto("reserva")
        self.boton_reserva.disabled = aporte <= 0
        self.boton_reserva.content = f"Apartar {formato(aporte)} en la reserva" if aporte else "Apartar en la reserva"
        ahorro = p.monto("ahorro")
        hay_cajas = bool(self.repo.metas_para_reparto())
        self.boton_cajas.disabled = not (ahorro > 0 and hay_cajas)
        self.boton_cajas.content = f"Abonar {formato(ahorro)} a mis cajas" if ahorro and hay_cajas else \
            "Abonar el ahorro a mis cajas"

        self.t_tarjetas.cargar([(d["producto"]["id"], [
            d["producto"]["nombre"], d["fecha_limite"].isoformat() if d["fecha_limite"] else ("Vencido", ROJO),
            pesos(d["minimo"]), (pesos(d["recomendado"]), VERDE), pesos(d["total"]),
            (f"+{formato(d['interes_si_minimo'])} de intereses", NARANJA) if d["interes_si_minimo"] else "—"])
            for d in self.repo.recomendacion_pagos(p.monto("abono"), e.fecha)])

    def _mostrar_cubre(self, p) -> None:
        """Lista de lo que vence antes del próximo ingreso, con lo que sale de la reserva."""
        e = p.entrada
        titulo = ft.Text(f"📅 Lo que paga este ingreso (del {e.fecha.isoformat()} al {e.cubre_hasta.isoformat()})",
                         size=17, weight=ft.FontWeight.W_600)
        if not e.detalle:
            self.cubre.controls = [titulo, ayuda("No vence nada antes de tu próximo ingreso.")]
            return
        # Igual que el cálculo del plan: la reserva paga primero las deudas y luego los servicios.
        reserva = e.saldo_reserva
        usado: dict[int, int] = {}
        for i, v in sorted(enumerate(e.detalle), key=lambda x: (x[1].tipo != "credito", x[1].fecha)):
            usado[i] = min(reserva, v.monto)
            reserva -= usado[i]
        filas = []
        for i, v in enumerate(e.detalle):
            de_reserva = usado[i]
            origen = ("De la reserva" if de_reserva == v.monto else
                      f"{formato(de_reserva)} de la reserva" if de_reserva else "De este ingreso")
            filas.append((len(filas), [v.fecha.isoformat(), ("💳 " if v.tipo == "credito" else "🧾 ") + v.concepto,
                                       pesos(v.monto), (origen, VERDE if de_reserva else None)]))
        tabla = Tabla([("Vence", "centro"), ("Pago", "izq"), ("Valor", "der"), ("Se paga con", "izq")])
        tabla.cargar(filas)
        total = sum(v.monto for v in e.detalle)
        self.cubre.controls = [titulo, tabla.vista,
                               ayuda(f"Total {formato(total)}. Lo que vence el {e.proximo_ingreso.isoformat()} o "
                                     "después lo cubre tu próximo ingreso (o la reserva, si ya está ahorrado).")]

    @staticmethod
    def _chip(icono, valor: str) -> ft.Control:
        return ft.Container(ft.Row([ft.Icon(icono, size=16, color=GRIS), ft.Text(valor, size=12)], spacing=6,
                                   tight=True),
                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH, border_radius=20,
                            padding=ft.Padding.symmetric(vertical=6, horizontal=12))

    async def _apartar(self, _e=None) -> None:
        if not self.plan:
            return
        aporte = self.plan.monto("reserva")
        if aporte > 0 and await self.confirmar(f"¿Registrar un aporte de {formato(aporte)} a la reserva (Cajita)?",
                                               si="Registrar aporte"):
            self.repo.movimiento_reserva(self.plan.entrada.fecha, "aporte", aporte, "Aporte del plan del ingreso")
            self.cambio()
            self.notificar(f"Aporte de {formato(aporte)} registrado en la reserva")

    def _abonar_cajas(self, _e=None) -> None:
        if not self.plan:
            return
        from .ahorros import dialogo_repartir
        dialogo_repartir(self, self.plan.monto("ahorro"), self.plan.entrada.fecha, "Abonar el ahorro a mis cajas")
