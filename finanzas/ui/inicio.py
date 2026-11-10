"""Inicio: saldo a favor, las preguntas del mes, ahorros y patrimonio, el medidor de endeudamiento, la reserva y alertas."""

from datetime import date, timedelta

import customtkinter as ctk

from ..dinero import formato, porcentaje, tasa
from ..fechas import fin_periodo, inicio_periodo, nombre_periodo, periodo, periodo_siguiente
from ..plan import MENSAJE_NIVEL, NOMBRE_NIVEL, nivel_endeudamiento, ratio_endeudamiento
from .app import Pagina
from .graficas import Grafica
from .widgets import (COLOR_NIVEL, FONDO_TARJETA, FUENTE_NORMAL, FUENTE_SUBTITULO, GRIS, ICONO_NIVEL, MORADO,
                      NARANJA, ROJO, VERDE, SelectorMes, TarjetaCifra, color)


class PaginaInicio(Pagina):
    titulo = "Inicio"

    def construir(self) -> None:
        self.selector = SelectorMes(self.encabezado, lambda _p: self.refrescar())
        self.selector.pack(side="right")

        # Fila 1: el flujo del mes (arranca en cero cada mes, salvo el saldo a favor que se trae).
        # Fila 2: la foto de hoy (gasto del mes, deuda, ahorros y patrimonio).
        filas = []
        for _ in range(2):
            fila = ctk.CTkFrame(self, fg_color="transparent")
            fila.pack(fill="x", padx=24, pady=4)
            for i in range(4):
                fila.grid_columnconfigure(i, weight=1, uniform="cifras")
            filas.append(fila)
        self.favor = TarjetaCifra(filas[0], "💰 Saldo a favor (del mes anterior)", VERDE)
        self.entro = TarjetaCifra(filas[0], "💵 ¿Cuánto entró?", VERDE)
        self.salio = TarjetaCifra(filas[0], "👛 ¿Cuánto salió de mi bolsillo?", NARANJA)
        self.disponible = TarjetaCifra(filas[0], "✅ ¿Cuánto me queda?", VERDE)
        self.gaste = TarjetaCifra(filas[1], "🛒 ¿En qué gasté?")
        self.debo = TarjetaCifra(filas[1], "💳 ¿Cuánto debo?", MORADO)
        self.ahorros = TarjetaCifra(filas[1], "🐷 ¿Cuánto tengo ahorrado?", VERDE)
        self.patrimonio = TarjetaCifra(filas[1], "📊 Patrimonio (tengo − debo)", MORADO)
        for f, tarjetas in ((0, (self.favor, self.entro, self.salio, self.disponible)),
                            (1, (self.gaste, self.debo, self.ahorros, self.patrimonio))):
            for i, t in enumerate(tarjetas):
                t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0))

        medidores = ctk.CTkFrame(self, fg_color="transparent")
        medidores.pack(fill="x", padx=24, pady=8)
        medidores.grid_columnconfigure((0, 1), weight=1, uniform="medidores")
        self.medidor = self._medidor(medidores, "💳 Endeudamiento del mes siguiente", 0)
        self.reserva = self._medidor(medidores, "🏦 Mes adelantado (reserva en la Cajita)", 1)

        self.alertas = ctk.CTkFrame(self, fg_color=FONDO_TARJETA, corner_radius=12)
        self.alertas.pack(fill="x", padx=24, pady=4)

        graficas = ctk.CTkFrame(self, fg_color="transparent")
        graficas.pack(fill="x", padx=24, pady=8)
        graficas.grid_columnconfigure((0, 1), weight=1, uniform="graficas")
        self.g_categorias = Grafica(graficas, alto=3.4)
        self.g_categorias.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.g_flujo = Grafica(graficas, alto=3.4)
        self.g_flujo.grid(row=0, column=1, sticky="nsew")

    def _medidor(self, master, titulo: str, columna: int) -> dict:
        marco = ctk.CTkFrame(master, fg_color=FONDO_TARJETA, corner_radius=12)
        marco.grid(row=0, column=columna, sticky="nsew", padx=(0 if columna == 0 else 6, 0))
        ctk.CTkLabel(marco, text=titulo, font=FUENTE_NORMAL, anchor="w").pack(fill="x", padx=14, pady=(12, 2))
        cifra = ctk.CTkLabel(marco, text="", font=FUENTE_SUBTITULO, anchor="w")
        cifra.pack(fill="x", padx=14)
        barra = ctk.CTkProgressBar(marco, height=14)
        barra.pack(fill="x", padx=14, pady=6)
        nota = ctk.CTkLabel(marco, text="", text_color=GRIS, anchor="w", justify="left", wraplength=430)
        nota.pack(fill="x", padx=14, pady=(0, 12))
        return {"cifra": cifra, "barra": barra, "nota": nota}

    def refrescar(self) -> None:
        repo = self.repo
        per = self.selector.periodo
        r = repo.resumen_mes(per)
        hoy = date.today()
        ingreso_mensual = repo.ingreso_mensual_estimado(hoy)

        f = repo.flujo_mes(per)
        anterior = nombre_periodo(periodo_siguiente(per, -1))
        self.favor.mostrar(formato(f["saldo_favor"]),
                           f"Lo que te sobró en {anterior}. Se suma a lo que entre este mes."
                           if f["saldo_favor"] >= 0 else f"En {anterior} saliste más de lo que tenías.",
                           VERDE if f["saldo_favor"] >= 0 else ROJO)
        apartado = f["a_reserva"] + f["a_cajas"]
        nota = (f"Apartado este mes: reserva {formato(f['a_reserva'])}, cajas {formato(f['a_cajas'])}"
                + (f"\nAjustes: {formato(f['ajustes'])}" if f["ajustes"] else ""))
        if per < periodo(hoy):
            nota += f"\nPasó como saldo a favor a {nombre_periodo(periodo_siguiente(per))}."
        self.disponible.mostrar(formato(f["disponible"]), nota if apartado or f["ajustes"] or per < periodo(hoy)
                                else "Saldo a favor + entró − salió − lo que ahorraste",
                                VERDE if f["disponible"] >= 0 else ROJO)
        self.entro.mostrar(formato(r["entro"]), f"Ingreso estimado al mes: {formato(ingreso_mensual)}")
        self.salio.mostrar(formato(r["salio"]), f"Compras en efectivo/débito: {formato(r['compras_efectivo'])}\n"
                                                f"Pagos a tarjetas y créditos: {formato(r['pagos_credito'])}")
        self.gaste.mostrar(formato(r["compras_efectivo"] + r["compras_tarjeta"]),
                           f"Con tarjeta: {formato(r['compras_tarjeta'])}\n"
                           f"Costo de la deuda (intereses y cargos): {formato(r['costo_deuda'])}")
        sig = periodo_siguiente(periodo(hoy))
        pagos_sig = repo.total_programado(inicio_periodo(sig), fin_periodo(sig))
        self.debo.mostrar(formato(repo.deuda_total()),
                          f"En {nombre_periodo(sig)} te toca pagar: {formato(pagos_sig)}")
        pat = repo.patrimonio(hoy)
        self.ahorros.mostrar(formato(pat["cajas"] + pat["reserva"]),
                             f"Cajas de ahorro: {formato(pat['cajas'])}\nReserva (Cajita): {formato(pat['reserva'])}")
        self.patrimonio.mostrar(formato(pat["patrimonio"]),
                                f"Tienes {formato(pat['activos'])} (disponible + ahorros)\n"
                                f"Debes {formato(pat['deuda'])}", MORADO if pat["patrimonio"] >= 0 else ROJO)

        ratio = ratio_endeudamiento(pagos_sig, ingreso_mensual)
        nivel = nivel_endeudamiento(ratio, repo.config_plan())
        self.medidor["cifra"].configure(
            text=f"{ICONO_NIVEL[nivel]} {porcentaje(ratio)} de tu ingreso — {NOMBRE_NIVEL[nivel]}",
            text_color=COLOR_NIVEL[nivel])
        self.medidor["barra"].set(min(1.0, ratio))
        self.medidor["barra"].configure(progress_color=color(COLOR_NIVEL[nivel]))
        self.medidor["nota"].configure(
            text=f"Pagos de {nombre_periodo(sig)}: {formato(pagos_sig)} de {formato(ingreso_mensual)} de ingreso. "
                 f"{MENSAJE_NIVEL[nivel]}" if ingreso_mensual else
                 "Configura tus fuentes de ingreso (Configuración) para calcular el endeudamiento.")

        saldo = repo.saldo_reserva()
        meta = repo.meta_mes_adelantado(sig)  # Cuotas + servicios del mes siguiente.
        progreso = min(1.0, saldo / meta) if meta else 1.0
        self.reserva["cifra"].configure(text=f"{formato(saldo)} de {formato(meta)} ({porcentaje(progreso, 0)})",
                                        text_color=VERDE if progreso >= 1 else NARANJA)
        self.reserva["barra"].set(progreso)
        self.reserva["barra"].configure(progress_color=color(VERDE if progreso >= 1 else NARANJA))
        self.reserva["nota"].configure(
            text="Tienes cubiertas las deudas y servicios del mes siguiente." if progreso >= 1 else
            f"Te faltan {formato(meta - saldo)} para tener las deudas y servicios de {nombre_periodo(sig)} ahorrados. "
            "Usa «Plan del ingreso» para saber cuánto apartar cada vez que cobres.")

        self._alertas(hoy)
        self.g_categorias.en_que_gaste(r["por_categoria"])
        self.g_flujo.entro_salio(repo.historial(6, inicio_periodo(per)))

    def _alertas(self, hoy: date) -> None:
        for w in self.alertas.winfo_children():
            w.destroy()
        repo = self.repo
        alertas: list[tuple[str, tuple[str, str]]] = []
        if not repo.fuentes("activa"):
            alertas.append(("Configura tus fuentes de ingreso en Configuración → Ingresos.", NARANJA))
        vencido = repo.pagos_programados(None, hoy - timedelta(days=1))
        nombres = {p["id"]: p["nombre"] for p in repo.productos(False)}
        for v in vencido:
            if v["monto"] > 0:
                alertas.append((f"Tienes {formato(v['monto'])} vencidos en {nombres[v['producto_id']]} "
                                f"(desde el {v['fecha'].isoformat()}). Si ya pagaste, regístralo en Tarjetas y deudas.",
                                ROJO))
        usura = repo.usura_vigente(hoy)
        dias_alerta = int(repo.config_num("dias_alerta", 7))
        for d in repo.deuda_productos(hoy):
            p = d["producto"]
            if d["fecha_limite"] and d["minimo"] > 0 and (d["fecha_limite"] - hoy).days <= dias_alerta:
                alertas.append((f"El pago de {p['nombre']} vence el {d['fecha_limite'].isoformat()}: mínimo "
                                f"{formato(d['minimo'])}.", NARANJA))
            if d["uso_cupo"] is not None and d["uso_cupo"] >= 0.7:
                alertas.append((f"Usas el {porcentaje(d['uso_cupo'], 0)} del cupo de {p['nombre']}. "
                                "Por encima del 70 % no tienes margen para emergencias.", ROJO))
            if usura and p["tasa_ea"] >= usura * 0.95:
                alertas.append((f"La tasa de {p['nombre']} ({tasa(p['tasa_ea'])} % E.A.) está cerca o por encima de "
                                f"la usura registrada para este mes ({tasa(usura)} % E.A.): revisa tus condiciones.",
                                NARANJA))
            if d["saldo_favor"]:
                alertas.append((f"Tienes {formato(d['saldo_favor'])} a favor en {p['nombre']}: se usarán en la "
                                "próxima deuda que registres ahí (o reclámalos a la entidad).", VERDE))
        for a in repo.alertas_usura():
            alertas.append((f"«{a['credito']['descripcion'] or a['producto']}» ({a['producto']}): la {a['motivo']} "
                            f"es {tasa(a['tasa'])} % E.A., por encima de la usura registrada para su fecha "
                            f"({tasa(a['usura'])} % E.A.). Revisa tu contrato.", ROJO))
        if repo.saldo_reserva() < 0:
            alertas.append(("La reserva quedó con saldo negativo: revisa sus movimientos.", ROJO))
        if repo.saldo_disponible(hoy) < 0:
            alertas.append(("Tu disponible está en negativo: falta registrar algún ingreso, o ajústalo en "
                            "Ahorros → «Ajustar mi disponible».", NARANJA))
        for m in repo.metas_ahorro():
            if m["estado"] == "activa" and m["ahorrado"] >= m["objetivo"]:
                alertas.append((f"🎯 ¡Completaste la caja «{m['nombre']}» ({formato(m['objetivo'])})!", VERDE))
        for t in repo.creditos_terminados(periodo(hoy)):
            alertas.append((f"🎉 Terminaste de pagar «{t['descripcion'] or 'deuda'}» en {t['producto']}.", VERDE))
        for pago in repo.pagos(periodo(hoy)):
            if pago["tipo"] == "menor_al_minimo":
                alertas.append((f"El pago del {pago['fecha']} a {pago['producto']} fue menor al mínimo: "
                                "puede generar intereses de mora y reporte.", ROJO))
        if not alertas:
            alertas.append(("Sin alertas por ahora. 👌", VERDE))
        ctk.CTkLabel(self.alertas, text="Alertas", font=FUENTE_SUBTITULO, anchor="w").pack(fill="x", padx=14,
                                                                                         pady=(10, 2))
        for texto, c in alertas:
            ctk.CTkLabel(self.alertas, text="• " + texto, text_color=c, anchor="w", justify="left",
                         wraplength=1000).pack(fill="x", padx=14, pady=1)
        ctk.CTkFrame(self.alertas, height=8, fg_color="transparent").pack()
