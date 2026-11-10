"""Inicio: el flujo del mes, la foto de hoy, medidores, alertas y gráficas."""

from datetime import date, timedelta

import flet as ft

from ...dinero import formato, porcentaje, tasa
from ...fechas import fin_periodo, inicio_periodo, nombre_periodo, periodo, periodo_siguiente
from ...plan import MENSAJE_NIVEL, NOMBRE_NIVEL, nivel_endeudamiento, ratio_endeudamiento
from .. import graficas
from ..componentes import Medidor, Pagina, SelectorMes, TarjetaCifra, contenedor, tarjeta, titulo_seccion
from ..tema import COLOR_NIVEL, ICONO_NIVEL, MORADO, NARANJA, ROJO, VERDE, c

ICONO_ALERTA = {VERDE: ft.Icons.CHECK_CIRCLE_OUTLINE, NARANJA: ft.Icons.WARNING_AMBER_ROUNDED,
                ROJO: ft.Icons.ERROR_OUTLINE}


class PaginaInicio(Pagina):
    titulo = "Inicio"

    def construir(self) -> None:
        self.selector = SelectorMes(lambda _p: self.app.datos_cambiaron())
        self.acciones.controls.append(self.selector.vista)

        self.favor = TarjetaCifra("💰 Saldo a favor (del mes anterior)", VERDE)
        self.entro = TarjetaCifra("💵 ¿Cuánto entró?", VERDE)
        self.salio = TarjetaCifra("👛 ¿Cuánto salió de mi bolsillo?", NARANJA)
        self.disponible = TarjetaCifra("✅ ¿Cuánto me queda?", VERDE)
        self.gaste = TarjetaCifra("🛒 ¿Cuánto gasté?")
        self.debo = TarjetaCifra("💳 ¿Cuánto debo?", MORADO)
        self.ahorros = TarjetaCifra("🐷 ¿Cuánto tengo ahorrado?", VERDE)
        self.patrimonio = TarjetaCifra("📊 Patrimonio (tengo − debo)", MORADO)
        self.medidor = Medidor("💳 Endeudamiento del mes siguiente")
        self.reserva = Medidor("🏦 Mes adelantado (reserva en la Cajita)")
        self.alertas = contenedor()
        self.graficas = ft.ResponsiveRow(spacing=14, run_spacing=14)
        self.agregar(
            ft.ResponsiveRow([t.vista for t in (self.favor, self.entro, self.salio, self.disponible)],
                             spacing=14, run_spacing=14),
            ft.ResponsiveRow([t.vista for t in (self.gaste, self.debo, self.ahorros, self.patrimonio)],
                             spacing=14, run_spacing=14),
            ft.ResponsiveRow([self.medidor.vista, self.reserva.vista], spacing=14, run_spacing=14),
            tarjeta(titulo_seccion("Alertas"), self.alertas, espacio=10),
            self.graficas,
        )

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
        self.debo.mostrar(formato(repo.deuda_total()), f"En {nombre_periodo(sig)} te toca pagar: {formato(pagos_sig)}")
        pat = repo.patrimonio(hoy)
        self.ahorros.mostrar(formato(pat["cajas"] + pat["reserva"]),
                             f"Cajas de ahorro: {formato(pat['cajas'])}\nReserva (Cajita): {formato(pat['reserva'])}")
        self.patrimonio.mostrar(formato(pat["patrimonio"]),
                                f"Tienes {formato(pat['activos'])} (disponible + ahorros)\n"
                                f"Debes {formato(pat['deuda'])}", MORADO if pat["patrimonio"] >= 0 else ROJO)

        ratio = ratio_endeudamiento(pagos_sig, ingreso_mensual)
        nivel = nivel_endeudamiento(ratio, repo.config_plan())
        self.medidor.mostrar(
            f"{ICONO_NIVEL[nivel]} {porcentaje(ratio)} de tu ingreso — {NOMBRE_NIVEL[nivel]}", ratio,
            COLOR_NIVEL[nivel],
            f"Pagos de {nombre_periodo(sig)}: {formato(pagos_sig)} de {formato(ingreso_mensual)} de ingreso. "
            f"{MENSAJE_NIVEL[nivel]}" if ingreso_mensual else
            "Configura tus fuentes de ingreso (Configuración) para calcular el endeudamiento.")

        saldo = repo.saldo_reserva()
        meta = repo.meta_mes_adelantado(sig)  # Cuotas + servicios del mes siguiente.
        progreso = min(1.0, saldo / meta) if meta else 1.0
        self.reserva.mostrar(
            f"{formato(saldo)} de {formato(meta)} ({porcentaje(progreso, 0)})", progreso,
            VERDE if progreso >= 1 else NARANJA,
            "Tienes cubiertas las deudas y servicios del mes siguiente." if progreso >= 1 else
            f"Te faltan {formato(meta - saldo)} para tener las deudas y servicios de {nombre_periodo(sig)} ahorrados. "
            "Usa «Plan del ingreso» para saber cuánto apartar cada vez que cobres.")

        self._alertas(hoy)
        self.graficas.controls = [graficas.en_que_gaste(r["por_categoria"]),
                                  graficas.entro_salio(repo.historial(6, inicio_periodo(per)))]

    def _alertas(self, hoy: date) -> None:
        repo = self.repo
        alertas: list[tuple[str, tuple]] = []
        if not repo.fuentes("activa"):
            alertas.append(("Configura tus fuentes de ingreso en Configuración → Ingresos.", NARANJA))
        nombres = {p["id"]: p["nombre"] for p in repo.productos(False)}
        for v in repo.pagos_programados(None, hoy - timedelta(days=1)):
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
        self.alertas.controls = [
            ft.Container(ft.Row([ft.Icon(ICONO_ALERTA[col], color=c(col), size=20),
                                 ft.Text(t, size=13, expand=True)], spacing=10,
                                vertical_alignment=ft.CrossAxisAlignment.START),
                         bgcolor=ft.Colors.with_opacity(0.08, c(col)), border_radius=10,
                         padding=ft.Padding.symmetric(vertical=8, horizontal=12))
            for t, col in alertas]
