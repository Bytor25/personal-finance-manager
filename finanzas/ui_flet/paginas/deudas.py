"""Tarjetas y deudas: productos, pagos, extractos, deudas existentes, comparar y organizar deuda."""

from datetime import date

import flet as ft

from ... import condiciones as cond_mod
from ...campos import Campo, hoy_texto, parsear_fecha, pesos
from ...credito import ABONO_CONSTANTE, CUOTA_FIJA, Cargo, Oferta, comparar_ofertas
from ...dinero import a_centavos, a_tasa, formato, porcentaje, tasa
from ...repositorio import metodo_producto
from ...ui.condiciones import COBROS, MODALIDADES, PERIODICIDADES, SISTEMAS
from ...ui.condiciones import campos as campos_condiciones
from ...ui.condiciones import leer as leer_condiciones
from .. import graficas
from ..componentes import (Pagina, Pestanas, Tabla, ayuda, barra_botones, boton, cerrar, contenedor, linea_dato,
                           requiere, seccion, tarjeta, texto, titulo_seccion)
from ..tema import GRIS, MORADO, NARANJA, ROJO, VERDE, c

TIPOS_PAGO = {"minimo": "Mínimo", "mas_del_minimo": "Más del mínimo", "total": "Total",
              "menor_al_minimo": "⚠ Menor al mínimo", "abono": "Abono", "refinanciacion": "Refinanciación",
              "cargo_inicial": "Cargo al comprar", "devolucion": "Devolución",
              "saldo_favor": "Saldo a favor aplicado"}
CANALES = ["", "App del banco / plataforma", "PSE", "Transferencia", "Efectivo en punto de pago",
           "Corresponsal bancario", "Débito automático", "Otro"]
TIPOS_PRODUCTO = {"tarjeta": "Tarjeta de crédito", "cupo": "Cupo de crédito (Addi, Sistecrédito, almacén)",
                  "prestamo": "Préstamo"}
AYUDA_FECHA = {
    "tarjeta": "Es la fecha límite de pago del extracto en el que te van a cobrar esa cuota. Si ya pagaste la de "
               "este mes, pon la del mes siguiente.",
    "cupo": "Mírala en la app (Addi, Sistecrédito, almacén): cada compra tiene su propia fecha de pago.",
    "prestamo": "La fecha de pago de la próxima cuota del préstamo.",
}
SUFIJO_TIPO = {"tarjeta": "", "cupo": " (cupo)", "prestamo": " (préstamo)"}
ORIGENES = {"compra": "Compra", "deuda_existente": "Deuda existente", "refinanciacion": "Deuda organizada"}
ICONO_TIPO = {"tarjeta": ft.Icons.CREDIT_CARD, "cupo": ft.Icons.SHOPPING_BAG_OUTLINED,
              "prestamo": ft.Icons.ACCOUNT_BALANCE_OUTLINED}


def ventana_grande(page: ft.Page, titulo: str, contenido: list[ft.Control], ancho: int = 1100,
                   acciones: list[ft.Control] | None = None) -> ft.AlertDialog:
    """Diálogo amplio y desplazable (cronograma, comparar, organizar)."""
    ancho = int(min(ancho, (page.width or 1200) - 60))
    dialogo = ft.AlertDialog(title=ft.Text(titulo), scrollable=True,
                             content=ft.Container(ft.Column(contenido, spacing=12, tight=True), width=ancho),
                             inset_padding=ft.Padding.symmetric(vertical=24, horizontal=24))
    dialogo.actions = (acciones or []) + [ft.TextButton("Cerrar", on_click=lambda _e: cerrar(page, dialogo))]
    page.show_dialog(dialogo)
    return dialogo


class PaginaDeudas(Pagina):
    titulo = "Tarjetas y deudas"

    def construir(self) -> None:
        self.tarjetas = ft.ResponsiveRow(spacing=14, run_spacing=14)
        self.t_productos = Tabla(
            [("Tarjeta / crédito", "izq"), ("Tasa E.A.", "der"), ("Debo (capital)", "der"),
             ("Uso del cupo · disponible", "der"), ("Próximo pago", "centro"), ("Mínimo", "der"), ("Total", "der"),
             ("Si pagas solo el mínimo", "der"), ("Según", "centro")],
            al_doble_clic=lambda _id: self._pago(), al_seleccionar=lambda _id: self._marcar_tarjetas(),
            vacio="Registra tu primera tarjeta o crédito con «Tarjeta / crédito».")

        self.t_creditos = Tabla([("Tarjeta / crédito", "izq"), ("Descripción", "izq"), ("Origen", "izq"),
                                 ("Fecha", "centro"), ("Valor", "der"), ("Cuotas restantes", "centro"),
                                 ("Saldo", "der"), ("Próxima cuota", "der")],
                                al_doble_clic=lambda _id: self._ver_cronograma(), vacio="No hay deudas activas.")
        self.t_pagos = Tabla([("Fecha", "centro"), ("Tarjeta / crédito", "izq"), ("Tipo", "izq"), ("Valor", "der"),
                              ("A capital", "der"), ("Intereses y cargos", "der"), ("Abono extra", "der"),
                              ("Desde reserva", "centro"), ("Canal", "izq")], vacio="Aún no hay pagos.")
        self.t_mora = Tabla([("Tarjeta / crédito", "izq"), ("Deuda", "izq"), ("Cuota", "centro"), ("Venció", "centro"),
                             ("Días de mora", "centro"), ("Capital vencido", "der"), ("Pendiente", "der"),
                             ("Mora liquidada", "der"), ("Cobranza liquidada", "der"), ("Por liquidar a hoy", "der")],
                            vacio="Sin cuotas en mora. 👌")
        self.t_extractos = Tabla([("Tarjeta", "izq"), ("Corte", "centro"), ("Fecha límite", "centro"),
                                  ("Capital del mes", "der"), ("Intereses", "der"), ("Pago mínimo", "der"),
                                  ("Deuda restante", "der"), ("Pago total", "der")], vacio="Sin extractos registrados.")
        self.t_refis = Tabla([("Fecha", "centro"), ("Tarjeta", "izq"), ("Deuda antes", "der"), ("Valor pagado", "der"),
                              ("Saldo organizado", "der"), ("Cuotas", "centro"), ("Valor cuota", "der"),
                              ("E.A. declarada", "der"), ("E.A. según cuota", "der")],
                             vacio="No has organizado deudas.")
        self.pestanas = Pestanas([
            ("Deudas activas", ft.Icons.LIST_ALT, ft.Column([
                barra_botones(boton("Ver cronograma y costo", self._ver_cronograma, ft.Icons.TABLE_CHART_OUTLINED),
                              boton("Devolución de compra", self._devolucion, ft.Icons.UNDO, "tonal"),
                              boton("Eliminar cuotas que ya tenía", self._eliminar_credito, ft.Icons.DELETE_OUTLINE,
                                    "borde")),
                self.t_creditos.vista], spacing=10)),
            ("Pagos", ft.Icons.PAYMENTS_OUTLINED, ft.Column([
                barra_botones(boton("Eliminar pago", self._eliminar_pago, ft.Icons.DELETE_OUTLINE, "borde"),
                              ayuda("Solo se puede eliminar el último pago de cada tarjeta.")),
                self.t_pagos.vista], spacing=10)),
            ("Mora y cobranza", ft.Icons.WARNING_AMBER_ROUNDED, ft.Column([
                barra_botones(boton("Liquidar mora a hoy", self._liquidar_mora, ft.Icons.CALCULATE, "tonal"),
                              ayuda("La mora se calcula con la tasa pactada sin superar la usura del periodo "
                                    "(Configuración → Tasas legales). Al registrar un pago se liquida sola.")),
                self.t_mora.vista], spacing=10)),
            ("Extractos", ft.Icons.DESCRIPTION_OUTLINED, ft.Column([
                barra_botones(boton("Eliminar extracto", self._eliminar_extracto, ft.Icons.DELETE_OUTLINE, "borde")),
                self.t_extractos.vista], spacing=10)),
            ("Deudas organizadas", ft.Icons.MERGE_TYPE, ft.Column([
                barra_botones(boton("Eliminar (deshacer)", self._eliminar_refi, ft.Icons.UNDO, "borde")),
                self.t_refis.vista], spacing=10)),
        ])
        self.graficas = ft.ResponsiveRow(spacing=14, run_spacing=14)
        self.agregar(
            self.tarjetas,
            seccion("💳 Mis tarjetas y créditos",
                    barra_botones(
                        boton("Tarjeta / crédito", lambda _e: self._dialogo_producto(None), ft.Icons.ADD),
                        boton("Registrar pago", self._pago, ft.Icons.PAYMENTS, color=VERDE),
                        boton("Registrar extracto", self._extracto, ft.Icons.DESCRIPTION_OUTLINED, "tonal"),
                        boton("Cuotas que ya tenía", self._deuda_existente, ft.Icons.PLAYLIST_ADD, "tonal"),
                        boton("Organizar deuda", self._organizar, ft.Icons.MERGE_TYPE, color=MORADO),
                        boton("Editar", self._editar_producto, ft.Icons.EDIT_OUTLINED, "borde"),
                        boton("Condiciones", self._condiciones, ft.Icons.RULE, "borde"),
                        boton("Comparar financiación", lambda _e: VentanaComparar(self), ft.Icons.COMPARE_ARROWS,
                              "borde")),
                    self.t_productos.vista,
                    ayuda("«Si pagas solo el mínimo» = intereses aproximados que se generan el mes siguiente sobre lo "
                          "que quedas debiendo."),
                    explicacion="Selecciona una tarjeta (en las tarjetas de arriba o en la tabla) para registrar un "
                                "pago, un extracto u organizar su deuda. Doble clic = registrar pago."),
            tarjeta(self.pestanas.vista),
            self.graficas,
        )

    # ------------------------------------------------------------ datos

    def refrescar(self) -> None:
        repo = self.repo
        hoy = date.today()
        self._deudas = {d["producto"]["id"]: d for d in repo.deuda_productos(hoy)}
        filas = []
        for d in self._deudas.values():
            p = d["producto"]
            filas.append((p["id"], [
                p["nombre"] + SUFIJO_TIPO[p["tipo"]], f"{tasa(p['tasa_ea'])} %",
                pesos(d["saldo"]) + (f" · a favor {formato(d['saldo_favor'])}" if d["saldo_favor"] else ""),
                (f"{porcentaje(d['uso_cupo'], 0)} · {formato(d['disponible'])}",
                 ROJO if d["uso_cupo"] >= 0.7 else None) if d["uso_cupo"] is not None else "—",
                d["fecha_limite"].isoformat() if d["fecha_limite"] else "—", pesos(d["minimo"]), pesos(d["total"]),
                (f"+{formato(d['interes_si_minimo'])} de intereses", NARANJA) if d["interes_si_minimo"] else "—",
                "Extracto" if d["fuente"] == "extracto" else "Cronograma"]))
        self.t_productos.cargar(filas)
        self._marcar_tarjetas()

        self._creditos = {c_["credito"]["id"]: c_ for c_ in repo.creditos()}
        self.t_creditos.cargar([(cid, [
            c_["credito"]["producto"], c_["credito"]["descripcion"], ORIGENES[c_["credito"]["origen"]],
            c_["credito"]["fecha"], pesos(c_["credito"]["monto"]),
            f"{c_['cuotas_restantes']} de {c_['credito']['num_cuotas']}", pesos(c_["saldo"]),
            f"{c_['proxima']['fecha']} · {formato(repo._pendiente(c_['proxima']))}" if c_["proxima"] else "—"])
            for cid, c_ in self._creditos.items()])
        self.t_mora.cargar([(m["cuota"]["id"], [
            m["producto"], m["descripcion"], m["cuota"]["numero"], m["cuota"]["fecha"], (m["dias"], ROJO),
            pesos(m["capital"]), pesos(m["pendiente"]), pesos(m["mora_liquidada"]), pesos(m["cobranza_liquidada"]),
            pesos(m["por_liquidar"])]) for m in repo.estado_mora(hoy)])
        self.t_pagos.cargar([(p["id"], [p["fecha"], p["producto"],
                                        (TIPOS_PAGO.get(p["tipo"], p["tipo"]),
                                         ROJO if p["tipo"] == "menor_al_minimo" else None),
                                        pesos(p["monto"]), pesos(p["a_capital"]), pesos(p["a_costos"]),
                                        pesos(p["abono_extra"]), "Sí" if p["desde_reserva"] else "", p["canal"]])
                             for p in repo.pagos()])
        self.t_extractos.cargar([(e["id"], [e["producto"], e["fecha_corte"], e["fecha_limite"],
                                            pesos(e["capital_mes"]), pesos(e["intereses"]),
                                            formato(e["pago_minimo"], decimales=True),
                                            formato(e["deuda_restante"], decimales=True),
                                            formato(e["pago_total"], decimales=True)]) for e in repo.extractos()])
        self.t_refis.cargar([(r["id"], [r["fecha"], r["producto"], pesos(r["deuda_total"]), pesos(r["valor_pagado"]),
                                        pesos(r["saldo"]), r["num_cuotas"], pesos(r["cuota"]),
                                        f"{tasa(r['tasa_ea'])} %" if r["tasa_ea"] is not None else "—",
                                        f"{tasa(r['ea_implicita'])} %" if r["ea_implicita"] is not None else "—"])
                             for r in repo.refinanciaciones()])
        self.graficas.controls = [graficas.proyeccion(repo.proyeccion_pagos(12, hoy), repo.ingreso_mensual_estimado(hoy)),
                                  graficas.historial(repo.historial(12, hoy))]

    def _marcar_tarjetas(self) -> None:
        """Tarjetas visuales por producto (clic = seleccionar)."""
        seleccionado = self.t_productos.seleccionado()
        vistas = []
        for pid, d in self._deudas.items():
            p = d["producto"]
            activo = pid == seleccionado
            uso = d["uso_cupo"]
            cuerpo = [ft.Row([ft.Icon(ICONO_TIPO[p["tipo"]], color=ft.Colors.PRIMARY),
                              ft.Text(p["nombre"], size=16, weight=ft.FontWeight.W_600, expand=True),
                              ft.Text(f"{tasa(p['tasa_ea'])} % E.A.", size=12, color=GRIS)]),
                      ft.Text(formato(d["saldo"]), size=22, weight=ft.FontWeight.BOLD, color=c(MORADO)),
                      ft.Text("Próximo pago: " + (f"{d['fecha_limite'].isoformat()} · mínimo {formato(d['minimo'])}"
                                                  if d["fecha_limite"] else "—"), size=12, color=GRIS)]
            if uso is not None:
                cuerpo.append(ft.ProgressBar(value=min(1, uso), bar_height=6, border_radius=3,
                                             color=c(ROJO if uso >= 0.7 else NARANJA if uso >= 0.4 else VERDE)))
                cuerpo.append(ft.Text(f"Usas el {porcentaje(uso, 0)} del cupo · disponible {formato(d['disponible'])}",
                                      size=11, color=GRIS))
            vistas.append(ft.Container(
                ft.Column(cuerpo, spacing=6, tight=True), col={"xs": 12, "sm": 6, "xl": 4}, padding=16,
                border_radius=16, ink=True, on_click=lambda _e, i=pid: self._elegir_producto(i),
                bgcolor=ft.Colors.SECONDARY_CONTAINER if activo else ft.Colors.SURFACE_CONTAINER_LOW,
                border=ft.Border.all(2, ft.Colors.PRIMARY) if activo else ft.Border.all(2, ft.Colors.TRANSPARENT),
                animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT)))
        self.tarjetas.controls = vistas

    def _elegir_producto(self, pid: int) -> None:
        fila = next((f for f in self.t_productos.tabla.rows if f.data == pid), None)
        if fila is not None:
            self.t_productos._seleccionar(fila)
        self._marcar_tarjetas()
        self.page.update()

    def _producto_seleccionado(self, obligatorio: bool = True):
        id_ = self.t_productos.seleccionado()
        if id_ is None and len(self._deudas) == 1:
            id_ = next(iter(self._deudas))
        if id_ is None:
            if obligatorio:
                self.error("Selecciona una tarjeta o crédito." if self._deudas else
                           "Primero registra una tarjeta o crédito con «Tarjeta / crédito».")
            return None
        return self._deudas[id_]["producto"]

    # ------------------------------------------------------------ productos

    def _dialogo_producto(self, p) -> None:
        campos = [
            Campo("nombre", "Nombre", defecto=p["nombre"] if p else None, ayuda="Ej.: Nu, Visa Bancolombia"),
            Campo("entidad", "Banco / entidad", opcional=True, defecto=p["entidad"] if p else None),
            Campo("tipo", "Tipo", "opcion", [(v, k) for k, v in TIPOS_PRODUCTO.items()],
                  defecto=p["tipo"] if p else "tarjeta",
                  ayuda="Cupo: Addi, Sistecrédito, crédito de almacén. Cada compra tiene sus propias cuotas y fechas; "
                        "la primera vence un mes después de la compra. Si el almacén te da tarjeta con fecha de "
                        "corte (ej. Agaval), regístrala como tarjeta."),
            Campo("cupo", "Cupo total", "monto", defecto=formato(p["cupo"], signo=False) if p else "0",
                  visible_si=("tipo", ("tarjeta", "cupo")),
                  ayuda="Si el cupo cambia (cupo variable), edítalo cuando cambie. 0 = sin cupo fijo."),
            Campo("tasa", "Tasa de interés E.A. (%)", "tasa", defecto=str(p["tasa_ea"]).replace(".", ",") if p else None,
                  ayuda="La que aparece en tu extracto o en la app. Ej.: 28,5. Si las compras son sin intereses, 0. "
                        "Cada compra puede tener su propia tasa."),
            Campo("corte", "Día de corte", "entero", defecto=p["dia_corte"] if p else None,
                  visible_si=("tipo", "tarjeta")),
            Campo("pago", "Día límite de pago", "entero", defecto=p["dia_pago"] if p else None,
                  visible_si=("tipo", ("tarjeta", "prestamo"))),
            Campo("manejo", "Cuota de manejo mensual", "monto",
                  defecto=formato(p["cuota_manejo"], signo=False) if p else "0", visible_si=("tipo", "tarjeta")),
            Campo("una_cuota", "Cobra intereses en compras a 1 cuota", "check",
                  defecto=bool(p["interes_una_cuota"]) if p else False, visible_si=("tipo", "tarjeta")),
        ]

        def guardar(v: dict) -> None:
            es_tarjeta = v["tipo"] == "tarjeta"
            self.repo.guardar_producto(p["id"] if p else None, v["nombre"], v["entidad"] or "", v["tipo"],
                                       v["cupo"] or 0, v["tasa"], v["corte"] if es_tarjeta else 1, v["pago"] or 1,
                                       v["manejo"] or 0 if es_tarjeta else 0, bool(v["una_cuota"]))
            self.cambio()

        self.formulario("Editar tarjeta / crédito" if p else "Nueva tarjeta / crédito", campos, guardar)

    def _editar_producto(self, _e=None) -> None:
        p = self._producto_seleccionado()
        if p:
            self._dialogo_producto(p)

    # ------------------------------------------------------------ pagos

    def _pago(self, _e=None) -> None:
        p = self._producto_seleccionado()
        if not p:
            return
        d = self._deudas[p["id"]]
        texto_ayuda = (f"Mínimo: {formato(d['minimo'])}  ·  Total: {formato(d['total'])}"
                       + (f"  ·  Vence: {d['fecha_limite'].isoformat()}" if d["fecha_limite"] else "")
                       + (" (según el extracto)" if d["fuente"] == "extracto" else ""))
        if d.get("mora_estimada"):
            texto_ayuda += f"\nIncluye {formato(d['mora_estimada'])} de mora y cobranza a hoy."
        reserva = self.repo.saldo_reserva()
        campos = [
            Campo("fecha", "Fecha del pago", "fecha", defecto=hoy_texto()),
            Campo("monto", "Valor pagado", "monto", defecto=formato(d["minimo"], signo=False) if d["minimo"] else None,
                  ayuda=texto_ayuda),
            Campo("reserva", "Lo pagué con la plata de la reserva (Cajita)", "check",
                  defecto=bool(d["minimo"]) and reserva >= d["minimo"],
                  ayuda=f"Saldo de la reserva: {formato(max(0, reserva))}."),
            Campo("reducir", "Si pagas más del mínimo, lo que sobra…", "opcion",
                  [("Abona a capital y reduce el plazo (ahorras más intereses)", "plazo"),
                   ("Abona a capital y reduce la cuota", "cuota"),
                   ("Anticipa las cuotas siguientes completas", "anticipar")]),
            Campo("canal", "Canal de pago", "opcion", [(c_ or "Sin especificar", c_) for c_ in CANALES]),
            Campo("notas", "Notas", opcional=True),
        ]

        async def guardar(v: dict) -> None:
            if self.repo.pago_posible_duplicado(p["id"], v["fecha"], v["monto"]) and not await self.confirmar(
                    "Ya hay un pago por ese mismo valor y fecha en esta tarjeta. ¿Es otro pago distinto?",
                    titulo="¿Pago repetido?", si="Sí, es otro pago"):
                raise ValueError("Pago no registrado.")
            r = self.repo.registrar_pago(p["id"], v["fecha"], v["monto"], v["reserva"], v["reducir"],
                                         v["notas"] or "", v["canal"] or "")
            self.cambio()
            nombres = {"cobranza": "Gastos de cobranza", "mora": "Intereses de mora", "otros": "Cargos",
                       "interes": "Intereses", "capital": "Capital de cuotas"}
            lineas: list[ft.Control] = [
                texto(f"Pago registrado como: {TIPOS_PAGO[r['tipo']]}", 15, ft.FontWeight.W_600,
                      ROJO if r["tipo"] == "menor_al_minimo" else VERDE),
                linea_dato("A intereses y cargos", formato(r["a_costos"])),
                linea_dato("A capital", formato(r["a_capital"]))]
            lineas += [linea_dato(f"   · {nombres[k]}", formato(val), negrita=False)
                       for k, val in r["por_componente"].items()]
            notas = []
            if r["mora_liquidada"]:
                notas.append(f"Se liquidaron {formato(r['mora_liquidada'])} de mora y cobranza hasta la fecha del pago.")
            if r["abono_extra"]:
                notas.append(f"Incluye abono extra a capital de {formato(r['abono_extra'])}.")
            if r["anticipado"]:
                notas.append(f"Cuotas anticipadas: {formato(r['anticipado'])}.")
            if r["penalidad"]:
                notas.append(f"Penalidad por prepago según tus condiciones: {formato(r['penalidad'])}.")
            if r["manejo"]:
                notas.append(f"Cuota de manejo / comisiones del ciclo: {formato(r['manejo'])}.")
            if r["segun_extracto"]:
                notas.append("Clasificado con el mínimo y el total del extracto vigente.")
            if r["sin_aplicar"]:
                notas.append(f"Quedaron {formato(r['sin_aplicar'])} como saldo a favor: se usarán en la próxima deuda "
                             "que registres en esta tarjeta o cupo.")
            if r["tipo"] == "menor_al_minimo":
                notas.append("⚠ El pago es menor al mínimo: puede generar intereses de mora y reporte.")
            lineas += [ayuda(n) for n in notas]
            self.informar("Pago registrado", lineas)

        self.formulario(f"Pago a {p['nombre']}", campos, guardar, texto_boton="Registrar pago")

    async def _eliminar_pago(self, _e=None) -> None:
        id_ = requiere(self.t_pagos, self, "Selecciona un pago en la tabla.")
        if id_ is not None and await self.confirmar(
                "¿Eliminar este pago? Se deshace su efecto en las cuotas y en la reserva.", si="Eliminar",
                peligro=True):
            try:
                self.repo.eliminar_pago(id_)
            except ValueError as e:
                return self.error(str(e))
            self.cambio()

    # ------------------------------------------------------------ extractos

    def _extracto(self, _e=None) -> None:
        p = self._producto_seleccionado()
        if not p:
            return
        if p["tipo"] != "tarjeta":
            return self.error("Los extractos aplican a tarjetas de crédito.")
        campos = [
            Campo("corte", "Fecha de corte", "fecha"),
            Campo("limite", "Fecha límite de pago", "fecha"),
            Campo("capital", "Deuda a pagar este mes (capital)", "monto"),
            Campo("intereses", "Intereses", "monto", defecto="0"),
            Campo("avances", "Comisiones de avances", "monto", defecto="0"),
            Campo("servicio", "Comisiones por servicio / cuota de manejo", "monto", defecto="0"),
            Campo("conversion", "Cargos por conversión (compras en otra moneda)", "monto", defecto="0"),
            Campo("abonos", "Abonos", "monto", defecto="0"),
            Campo("devoluciones", "Devoluciones o ajustes a favor", "monto", defecto="0"),
            Campo("restante", "Deuda restante", "monto", defecto="0"),
        ]

        def guardar(v: dict) -> None:
            self.repo.registrar_extracto(p["id"], v["corte"], v["limite"], v["capital"], v["intereses"], v["avances"],
                                         v["servicio"], v["conversion"], v["abonos"], v["devoluciones"], v["restante"])
            ext = self.repo.ultimo_extracto(p["id"])
            self.cambio()
            self.informar("Extracto registrado", [
                linea_dato("Pago mínimo calculado", formato(ext["pago_minimo"], decimales=True)),
                linea_dato("Pago total calculado", formato(ext["pago_total"], decimales=True)),
                ayuda("Compáralos con tu extracto. Si no coinciden, revisa los valores ingresados. Hasta la fecha "
                      "límite, el plan usa este mínimo en lugar del cronograma.")])

        self.formulario(f"Extracto de {p['nombre']}", campos, guardar, ancho=500,
                        explicacion="Copia los valores del resumen de tu extracto. La app calcula el pago mínimo y el "
                                    "total para que los compares.")

    async def _eliminar_extracto(self, _e=None) -> None:
        id_ = requiere(self.t_extractos, self, "Selecciona un extracto en la tabla.")
        if id_ is not None and await self.confirmar("¿Eliminar este extracto?", si="Eliminar", peligro=True):
            self.repo.eliminar_extracto(id_)
            self.cambio()

    # ------------------------------------------------------------ deudas existentes

    def _deuda_existente(self, _e=None) -> None:
        p = self._producto_seleccionado()
        if not p:
            return
        proxima = self.repo.proxima_fecha_cobro(p["id"], date.today())
        campos = [
            Campo("descripcion", "¿Qué compraste? / descripción", ayuda="Ej.: Celular, Zapatos Chevignon, préstamo"),
            Campo("valor", "Valor original de la compra o del préstamo", "monto"),
            Campo("total", "Número total de cuotas", "entero", ayuda="La N de «cuota n de N»."),
            Campo("pagadas", "Cuotas que ya pagaste", "entero", defecto=0,
                  ayuda="Si la app dice «cuota 5 de 12» y esa aún no la pagas, ya pagaste 4."),
            Campo("proxima", "Fecha de la próxima cuota que vas a pagar", "fecha",
                  defecto=proxima.isoformat() if proxima else None, ayuda=AYUDA_FECHA.get(p["tipo"], "")),
            Campo("tasa", "Tasa E.A. (%)", "tasa", defecto=str(p["tasa_ea"]).replace(".", ","),
                  ayuda="0 si la compra es sin intereses."),
            Campo("metodo", "¿Cómo se paga?", "opcion",
                  [("Capital fijo + intereses (tarjetas: la cuota baja cada mes)", ABONO_CONSTANTE),
                   ("Cuota fija (Addi, Sistecrédito, almacenes, préstamos)", CUOTA_FIJA)],
                  defecto=metodo_producto(p["tipo"])),
            Campo("cuota", "Valor de la cuota", "monto", opcional=True, visible_si=("metodo", CUOTA_FIJA),
                  ayuda="Sin contar cargos. Si la conoces, el cronograma se ajusta a ella."),
            Campo("saldo", "Saldo pendiente que muestra la app", "monto", opcional=True,
                  ayuda="Si no lo sabes, déjalo vacío: se calcula con el valor, la tasa y las cuotas pagadas."),
            Campo("cargo", "Cargo fijo por cuota (aval, fianza, plataforma)", "monto", opcional=True),
        ]

        def guardar(v: dict) -> None:
            cid = self.repo.registrar_deuda_existente(p["id"], v["descripcion"], v["proxima"], v["valor"], v["total"],
                                                      v["pagadas"], v["tasa"], v["metodo"], v["cuota"], v["saldo"],
                                                      v["cargo"] or 0)
            self.cambio()
            cuotas = self.repo.cronograma_credito(cid)
            cond = self.repo.condiciones_credito(cid)
            primera, ultima = cuotas[0], cuotas[-1]
            lineas: list[ft.Control] = [
                linea_dato("Saldo pendiente", formato(sum(c_["capital"] for c_ in cuotas))),
                linea_dato("Cuotas que faltan", f"{len(cuotas)} (de la {primera['numero']} a la {ultima['numero']})"),
                linea_dato("Próxima cuota", f"{primera['fecha']} · "
                                            f"{formato(primera['capital'] + primera['interes'] + primera['otros'])}"),
                linea_dato("Última cuota", ultima["fecha"]),
                ayuda("Compáralo con la app del banco. Si algo no coincide, elimínala y regístrala de nuevo (ej. con "
                      "el saldo o el valor de la cuota que muestra la app).")]
            segun_cuota = cond.get("tasa_segun_cuota_ea")
            if segun_cuota is not None and abs(segun_cuota - v["tasa"]) > 0.5:
                lineas.append(texto(
                    f"⚠ El valor de la cuota equivale a {tasa(segun_cuota)} % E.A., distinto del {tasa(v['tasa'])} % "
                    "E.A. que escribiste. El cronograma usa la tasa de la cuota. Puede incluir seguros u otros cargos "
                    "(regístralos aparte) o el saldo es distinto.", 13, color=NARANJA))
            self.informar("Cuotas registradas", lineas)

        self.formulario(f"Cuotas que ya tenía en {p['nombre']}", campos, guardar, ancho=580)

    async def _eliminar_credito(self, _e=None) -> None:
        id_ = requiere(self.t_creditos, self, "Selecciona una deuda en la tabla.")
        if id_ is not None and await self.confirmar("¿Eliminar esta deuda y su cronograma?", si="Eliminar",
                                                    peligro=True):
            try:
                self.repo.eliminar_credito(id_)
            except ValueError as e:
                return self.error(str(e))
            self.cambio()

    def _ver_cronograma(self, _e=None) -> None:
        id_ = requiere(self.t_creditos, self, "Selecciona una deuda en la tabla.")
        if id_ is not None:
            cr = self._creditos[id_]["credito"]
            ventana_cronograma(self, f"{cr['producto']} · {cr['descripcion'] or ORIGENES[cr['origen']]}", id_)

    def _devolucion(self, _e=None) -> None:
        id_ = requiere(self.t_creditos, self, "Selecciona la deuda de la compra que devolviste.")
        if id_ is None:
            return
        cr = self._creditos[id_]
        campos = [Campo("fecha", "Fecha de la devolución", "fecha", defecto=hoy_texto()),
                  Campo("monto", "Valor devuelto", "monto", defecto=formato(cr["saldo"], signo=False),
                        ayuda=f"Saldo de esta deuda: {formato(cr['saldo'])}. No es plata que sale de tu bolsillo."),
                  Campo("reducir", "La devolución…", "opcion",
                        [("Reduce el valor de las cuotas", "cuota"), ("Reduce el número de cuotas", "plazo")])]

        def guardar(v: dict) -> None:
            res = self.repo.registrar_devolucion(id_, v["fecha"], v["monto"], v["reducir"])
            self.cambio()
            mensaje = f"Se redujo la deuda en {formato(res['a_capital'])}."
            if res["saldo_a_favor"]:
                mensaje += f"\nQuedan {formato(res['saldo_a_favor'])} a tu favor: reclámalos al almacén o entidad."
            self.informar("Devolución registrada", mensaje)

        self.formulario("Devolución de compra", campos, guardar)

    def _liquidar_mora(self, _e=None) -> None:
        total = self.repo.liquidar_mora(date.today())
        self.cambio()
        self.notificar(f"Se liquidaron {formato(total)} de mora y cobranza hasta hoy.")

    def _condiciones(self, _e=None) -> None:
        p = self._producto_seleccionado()
        if not p:
            return
        base = self.repo.condiciones_producto(p["id"])

        def guardar(v: dict) -> None:
            self.repo.guardar_condiciones_producto(p["id"], leer_condiciones(v, base))
            self.cambio()
            self.notificar("Condiciones guardadas")

        self.formulario(f"Condiciones de {p['nombre']}", campos_condiciones(base), guardar, ancho=620,
                        texto_boton="Guardar condiciones")

    # ------------------------------------------------------------ organizar deuda

    def _organizar(self, _e=None) -> None:
        p = self._producto_seleccionado()
        if p:
            VentanaOrganizar(self, p)

    async def _eliminar_refi(self, _e=None) -> None:
        id_ = requiere(self.t_refis, self, "Selecciona una deuda organizada en la tabla.")
        if id_ is not None and await self.confirmar(
                "¿Deshacer esta refinanciación? Las deudas anteriores vuelven a quedar activas.", si="Deshacer",
                peligro=True):
            try:
                self.repo.eliminar_refinanciacion(id_)
            except ValueError as e:
                return self.error(str(e))
            self.cambio()


# ---------------------------------------------------------------- cronograma

def ventana_cronograma(pagina: PaginaDeudas, titulo: str, credito_id: int) -> None:
    repo = pagina.repo
    cond = repo.condiciones_credito(credito_id)
    costo = repo.costo_credito(credito_id)
    cuotas = repo.cronograma_credito(credito_id)
    acreedor = cond["acreedor"]
    chips = [f"Tasa pactada: {tasa(float(cond['tasa']['valor']))} % {cond['tasa']['modalidad']} "
             f"({tasa(costo.tasa_ea_contractual)} % E.A.)",
             f"Sistema: {dict((v, k) for k, v in SISTEMAS)[cond['sistema']]}", f"Periodicidad: {cond['periodicidad']}"]
    if acreedor.get("nombre"):
        chips.append(f"Acreedor: {acreedor['nombre']}" + (f" (financia {acreedor['financiador']})"
                                                          if acreedor.get("financiador") else ""))
    tabla = Tabla([("#", "centro"), ("Fecha", "centro"), ("Saldo inicial", "der"), ("Intereses", "der"),
                   ("Abono a capital", "der"), ("Cargos", "der"), ("Mora y cobranza", "der"), ("Cuota", "der"),
                   ("Saldo final", "der"), ("Pagado", "der"), ("Estado", "centro")])
    saldo = sum(c_["capital"] for c_ in cuotas if c_["estado"] != "refinanciada")
    filas = []
    for q in cuotas:
        detalle = cond_mod.cargar(q["detalle"], {}) if q["detalle"] else {}
        cargos = pesos(q["otros"]) + (f" ({', '.join(detalle)})" if detalle else "")
        estado = q["estado"].capitalize()
        filas.append((q["id"], [q["numero"], q["fecha"], pesos(saldo), pesos(q["interes"]), pesos(q["capital"]),
                                cargos, pesos(q["mora"] + q["cobranza"]),
                                pesos(q["capital"] + q["interes"] + q["otros"] + q["mora"] + q["cobranza"]),
                                pesos(saldo - q["capital"]), pesos(q["pagado"]),
                                (estado, VERDE if q["estado"] == "pagada" else None)]))
        if q["estado"] != "refinanciada":
            saldo -= q["capital"]
    tabla.cargar(filas)
    datos = [("Precio de contado", formato(costo.precio_contado)), ("Cuota inicial", formato(costo.cuota_inicial)),
             ("Capital financiado", formato(costo.capital)), ("Intereses", formato(costo.intereses)),
             ("Cargos (fianza, aval, seguros, mora…)", formato(costo.total_cargos)),
             ("Total de cuotas", formato(costo.total_cuotas)), ("Total pagado", formato(costo.total_pagado)),
             ("Diferencia vs. contado", f"{formato(costo.diferencia)} ({tasa(costo.incremento_pct, 1)} %)"),
             ("Costo financiero (intereses + cargos)", formato(costo.costo_financiero)),
             ("Costo comercial (sobreprecio)", formato(costo.costo_comercial)),
             ("Tasa efectiva real (flujos)", f"{tasa(costo.tasa_ea_efectiva)} % E.A."
              if costo.tasa_ea_efectiva is not None else "—")]
    if cond.get("tasa_segun_cuota_ea") is not None:
        datos.append(("Tasa según el valor de la cuota", f"{tasa(cond['tasa_segun_cuota_ea'])} % E.A."))
    if costo.cargos_como_interes and costo.tasa_ea_interes is not None:
        datos.append(("Intereses + cargos que cuentan como interés", f"{tasa(costo.tasa_ea_interes)} % E.A."))
    nota = "La tasa efectiva real incluye intereses y cargos según las fechas de cada pago; no reemplaza la tasa " \
           "contractual. "
    if cuotas and cuotas[0]["numero"] > 1:
        nota += "Esta deuda se registró a mitad de camino: el costo solo cuenta las cuotas registradas."
    ventana_grande(pagina.page, titulo, [
        ft.Row([_chip(t) for t in chips], wrap=True, spacing=8, run_spacing=8),
        tabla.vista,
        tarjeta(titulo_seccion("Costo de la financiación"),
                ft.ResponsiveRow([ft.Container(linea_dato(k, v), col={"xs": 12, "md": 6, "lg": 4}) for k, v in datos],
                                 spacing=24, run_spacing=6),
                ayuda(nota), color=ft.Colors.SURFACE_CONTAINER_HIGH)])


def _chip(valor: str) -> ft.Control:
    return ft.Container(ft.Text(valor, size=12), bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH, border_radius=20,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=12))


# ---------------------------------------------------------------- comparar financiación

class VentanaComparar:
    """Compara una misma compra con distintas ofertas reales de financiación."""

    CAMPOS = [("nombre", "Alternativa", "texto"), ("inicial", "Cuota inicial ($)", "monto"),
              ("financiado", "Precio financiado ($)", "monto"), ("cuotas", "Número de cuotas", "entero"),
              ("tasa", "Tasa (%)", "tasa"), ("modalidad", "Modalidad de la tasa", MODALIDADES),
              ("periodicidad", "Periodicidad", PERIODICIDADES), ("sistema", "Sistema", SISTEMAS),
              ("fianza", "Fianza / aval (% capital)", "tasa"), ("iva", "IVA fianza / aval (%)", "tasa"),
              ("cobro", "Cobro de la fianza / aval", COBROS), ("seguro", "Seguro por cuota ($)", "monto"),
              ("otros_cuota", "Otros cargos por cuota ($)", "monto"),
              ("otros_inicial", "Otros cargos iniciales ($)", "monto")]
    DEFECTOS = [{"nombre": "Contado", "cuotas": "1"}, {"nombre": "Addi", "cuotas": "3"},
                {"nombre": "Sistecrédito", "cuotas": "6"}, {"nombre": "Crédito del almacén", "cuotas": "12"}]

    def __init__(self, pagina: PaginaDeudas):
        self.pagina = pagina
        self.precio = ft.TextField(label="Precio de contado del producto", prefix="$ ", width=260,
                                   keyboard_type=ft.KeyboardType.NUMBER, on_submit=self._comparar)
        self.entradas: list[dict] = []
        columnas = []
        for defecto in self.DEFECTOS:
            entradas, controles = {}, []
            for clave, etiqueta, tipo in self.CAMPOS:
                if isinstance(tipo, list):
                    w = ft.Dropdown(label=etiqueta, value="0", dense=True, expanded_insets=ft.Padding.all(0),
                                    options=[ft.DropdownOption(key=str(i), text=e) for i, (e, _) in enumerate(tipo)])
                else:
                    w = ft.TextField(label=etiqueta, value=defecto.get(clave, ""), dense=True,
                                     text_style=ft.TextStyle(weight=ft.FontWeight.W_600) if clave == "nombre" else None)
                entradas[clave] = (w, tipo)
                controles.append(w)
            self.entradas.append(entradas)
            columnas.append(ft.Container(ft.Column(controles, spacing=8, tight=True,
                                                   horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                                         col={"xs": 12, "sm": 6, "lg": 3}, padding=12, border_radius=14,
                                         bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH))
        self.mensaje = ft.Text("", color=c(ROJO), size=13)
        self.tabla = Tabla([("Concepto", "izq")] + [(d["nombre"], "der") for d in self.DEFECTOS],
                           vacio="Escribe el precio de contado y presiona «Comparar».")
        ventana_grande(pagina.page, "Comparar financiación", [
            ayuda("Usa las condiciones reales de cada oferta. La alternativa «Contado» se paga toda como cuota "
                  "inicial. Deja el nombre vacío para no usar una columna."),
            ft.Row([self.precio, boton("Comparar", self._comparar, ft.Icons.COMPARE_ARROWS)], wrap=True, spacing=12),
            ft.ResponsiveRow(columnas, spacing=12, run_spacing=12),
            self.mensaje, titulo_seccion("Resultado"), self.tabla.vista], ancho=1200)

    def _oferta(self, col: int, precio: int) -> Oferta | None:
        v = {}
        for clave, (w, tipo) in self.entradas[col].items():
            valor = (w.value or "").strip()
            if isinstance(tipo, list):
                v[clave] = tipo[int(valor or 0)][1]
            elif not valor:
                v[clave] = None
            elif tipo == "monto":
                v[clave] = a_centavos(valor)
            elif tipo == "tasa":
                v[clave] = a_tasa(valor)
            elif tipo == "entero":
                v[clave] = int(valor)
            else:
                v[clave] = valor
        if not v["nombre"]:
            return None
        contado = v["nombre"].strip().lower() == "contado"
        cargos = []
        if v["fianza"]:
            cargos.append(Cargo("Fianza / aval", "pct_capital", v["fianza"], v["cobro"], v["iva"] or 0, "fianza"))
        if v["seguro"]:
            cargos.append(Cargo("Seguro", "fijo", v["seguro"], "por_cuota", 0, "seguro"))
        if v["otros_cuota"]:
            cargos.append(Cargo("Otros cargos por cuota", "fijo", v["otros_cuota"], "por_cuota"))
        if v["otros_inicial"]:
            cargos.append(Cargo("Otros cargos iniciales", "fijo", v["otros_inicial"], "inicial"))
        return Oferta(v["nombre"], precio, cuota_inicial=precio if contado else v["inicial"] or 0,
                      precio_financiado=None if contado else v["financiado"], num_cuotas=v["cuotas"] or 1,
                      tasa=v["tasa"] or 0, modalidad_tasa=v["modalidad"], periodicidad=v["periodicidad"],
                      sistema=v["sistema"], cargos=cargos)

    def _comparar(self, _e=None) -> None:
        self.mensaje.value = ""
        try:
            precio = a_centavos(self.precio.value or "")
            if precio <= 0:
                raise ValueError("Indica el precio de contado")
            ofertas = [o for o in (self._oferta(i, precio) for i in range(len(self.DEFECTOS))) if o]
            resultados = comparar_ofertas(ofertas)
        except ValueError as e:
            self.mensaje.value = str(e)
            self.pagina.page.update()
            return
        self.tabla.cambiar_columnas([("Concepto", "izq")] + [(o.nombre, "der") for o, _, _ in resultados])
        mejor = min(resultados, key=lambda r: r[2].total_pagado)[0].nombre if resultados else None
        filas = [
            ("Cuota inicial", lambda o, cr, c_: formato(c_.cuota_inicial)),
            ("Número de cuotas", lambda o, cr, c_: str(c_.num_cuotas)),
            ("Valor de la cuota", lambda o, cr, c_: formato(cr[0].total) if cr else "—"),
            ("Intereses", lambda o, cr, c_: formato(c_.intereses)),
            ("Fianza / aval, seguros y otros cargos", lambda o, cr, c_: formato(c_.total_cargos)),
            ("Total pagado", lambda o, cr, c_: (formato(c_.total_pagado), VERDE if o.nombre == mejor else None)),
            ("Diferencia vs. contado", lambda o, cr, c_: formato(c_.diferencia)),
            ("Incremento del costo", lambda o, cr, c_: f"{tasa(c_.incremento_pct, 1)} %"),
            ("Costo comercial (sobreprecio)", lambda o, cr, c_: formato(c_.costo_comercial)),
            ("Tasa contractual", lambda o, cr, c_: f"{tasa(c_.tasa_ea_contractual)} % E.A."),
            ("Costo efectivo (tasa real por flujos)", lambda o, cr, c_: f"{tasa(c_.tasa_ea_efectiva)} % E.A."
             if c_.tasa_ea_efectiva is not None else "—"),
        ]
        self.tabla.cargar([(k, [k] + [f(o, cr, c_) for o, cr, c_ in resultados]) for k, f in filas])
        self.pagina.page.update()


# ---------------------------------------------------------------- organizar deuda

class VentanaOrganizar:
    """Registrar o simular la refinanciación ("organizar deuda") de una tarjeta."""

    def __init__(self, pagina: PaginaDeudas, producto):
        self.pagina = pagina
        self.repo = pagina.repo
        self.producto = producto
        self.resultado = None
        hoy = date.today()
        self.entradas: dict[str, ft.TextField] = {}
        controles: list[ft.Control] = [ayuda(
            "Registra la refinanciación que hiciste o simula una antes de aceptarla. Basta con el valor de la cuota o "
            "la tasa; con ambos la app verifica que coincidan.")]
        for clave, etiqueta, defecto, texto_ayuda in [
            ("fecha", "Fecha de la refinanciación", hoy.isoformat(), ""),
            ("deuda", "Deuda total antes de organizarla",
             formato(self.repo.deuda_para_refinanciar(producto["id"], hoy), signo=False),
             "Sugerido: pago total del último extracto o lo calculado por la app."),
            ("pagado", "Valor que pagaste para refinanciar", "0", "Cubre intereses y comisiones de la deuda actual."),
            ("cuotas", "Número de cuotas elegidas", "", ""),
            ("cuota", "Valor de la cuota (según la app)", "", "Opcional si indicas la tasa."),
            ("tasa", "Tasa E.A. (según la app) %", "", "Opcional si indicas la cuota."),
            ("saldo", "Saldo a refinanciar", "", "Opcional. Por defecto: deuda total − valor pagado."),
            ("primera", "Fecha de la primera cuota", self.repo.primera_fecha_pago(producto["id"], hoy).isoformat(), ""),
        ]:
            e = ft.TextField(label=etiqueta, value=defecto, dense=True, helper=texto_ayuda or None,
                             helper_max_lines=3, on_submit=self._calcular)
            self.entradas[clave] = e
            controles.append(e)
        self._deudas_opciones: list[tuple[str, list[int] | None]] = [("Todas las deudas de esta tarjeta / cupo", None)]
        for c_ in self.repo.creditos(producto["id"]):
            cr = c_["credito"]
            self._deudas_opciones.append((f"{cr['descripcion'] or ORIGENES[cr['origen']]} · {cr['fecha']} · saldo "
                                          f"{formato(c_['saldo'])}", [cr["id"]]))
        self.deudas = ft.Dropdown(label="Deudas que se organizan", value="0", on_select=self._cambiar_deudas,
                                  expanded_insets=ft.Padding.all(0),
                                  options=[ft.DropdownOption(key=str(i), text=t)
                                           for i, (t, _) in enumerate(self._deudas_opciones)])
        self.acuerdo = ft.Checkbox(label="Es un acuerdo de pago (por mora)")
        self.mensaje = ft.Text("", color=c(ROJO), size=13)
        self.boton_registrar = boton("Registrar refinanciación", self._registrar, ft.Icons.SAVE, color=MORADO,
                                     deshabilitado=True)
        controles += [self.deudas, ayuda("Elige una compra si solo refinanciaste esa (ej. una compra de Addi)."),
                      self.acuerdo, self.mensaje,
                      ft.Row([boton("Calcular", self._calcular, ft.Icons.CALCULATE, "tonal"), self.boton_registrar],
                             wrap=True, spacing=8)]
        self.resumen = contenedor(ft.Text("Completa los datos y presiona «Calcular».", color=GRIS))
        self.tabla = Tabla([("#", "centro"), ("Fecha", "centro"), ("Capital", "der"), ("Intereses", "der"),
                            ("Cuota", "der")], vacio="")
        self.dialogo = ventana_grande(pagina.page, f"Organizar deuda · {producto['nombre']}", [
            ft.ResponsiveRow([
                ft.Container(ft.Column(controles, spacing=10, tight=True,
                                       horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                             col={"xs": 12, "md": 5}),
                ft.Container(ft.Column([tarjeta(self.resumen, color=ft.Colors.SURFACE_CONTAINER_HIGH),
                                        self.tabla.vista], spacing=12, tight=True), col={"xs": 12, "md": 7}),
            ], spacing=20, run_spacing=16)], ancho=1150)

    def _ids(self) -> list[int] | None:
        return self._deudas_opciones[int(self.deudas.value or 0)][1]

    def _cambiar_deudas(self, _e=None) -> None:
        deuda = self.repo.deuda_para_refinanciar(self.producto["id"], date.today(), self._ids())
        self.entradas["deuda"].value = formato(deuda, signo=False)
        self.resultado = None
        self.boton_registrar.disabled = True
        self.pagina.page.update()

    def _leer(self) -> dict:
        e = {k: (w.value or "").strip() for k, w in self.entradas.items()}
        if not e["cuotas"]:
            raise ValueError("Indica el número de cuotas.")
        if not e["cuota"] and not e["tasa"]:
            raise ValueError("Indica el valor de la cuota o la tasa E.A.")
        return {
            "fecha": parsear_fecha(e["fecha"]), "deuda": a_centavos(e["deuda"]),
            "pagado": a_centavos(e["pagado"] or "0"), "cuotas": int(e["cuotas"]),
            "cuota": a_centavos(e["cuota"]) if e["cuota"] else None, "tasa": a_tasa(e["tasa"]) if e["tasa"] else None,
            "saldo": a_centavos(e["saldo"]) if e["saldo"] else None, "primera": parsear_fecha(e["primera"]),
        }

    def _calcular(self, _e=None) -> None:
        self.mensaje.value = ""
        try:
            v = self._leer()
            r = self.repo.simular_refinanciacion(self.producto["id"], v["fecha"], v["deuda"], v["pagado"], v["cuotas"],
                                                 v["cuota"], v["tasa"], v["saldo"], v["primera"])
        except ValueError as e:
            self.mensaje.value = str(e)
            self.boton_registrar.disabled = True
            self.pagina.page.update()
            return
        self.resultado = (v["fecha"], r)
        self.boton_registrar.disabled = False
        self._mostrar(r)
        self.pagina.page.update()

    def _mostrar(self, r) -> None:
        actual = self.repo.situacion_actual(self.producto["id"], self._ids())
        lineas: list[ft.Control] = [
            titulo_seccion("Resultado"),
            linea_dato("Saldo refinanciado", formato(r.saldo)),
            linea_dato("Cuota mensual", formato(r.cuota)),
            linea_dato("Tasa según la cuota", f"{tasa(r.ea_implicita)} % E.A." if r.ea_implicita is not None
                       else f"{tasa(r.tasa_ea_declarada)} % E.A. (declarada)"),
            linea_dato("Intereses de las cuotas", formato(r.intereses_cuotas)),
            linea_dato("Total a pagar (valor pagado + cuotas)", formato(r.total_pagar)),
            linea_dato("Costo de organizar la deuda", formato(r.costo_total)),
            linea_dato("Última cuota", r.ultima_fecha.isoformat() if r.ultima_fecha else "—"),
        ]
        lineas += [texto("⚠ " + adv, 13, color=NARANJA) for adv in r.advertencias]
        if actual["total"]:
            tabla = Tabla([("", "izq"), ("Como estoy", "der"), ("Organizada", "der")], vacio="")
            tabla.cargar([(1, ["Próximo pago", formato(actual["proximo_pago"]), formato(r.cuota)]),
                          (2, ["Meses que faltan", str(actual["meses"]), str(r.n)]),
                          (3, ["Intereses y cargos que faltan", formato(actual["costos"]), formato(r.costo_total)])])
            diferencia_pago = actual["proximo_pago"] - r.cuota
            diferencia_costo = r.costo_total - actual["costos"]
            lineas += [ft.Divider(height=12), titulo_seccion("Comparación con seguir como estás"), tabla.vista,
                       texto(f"Tu pago {'baja' if diferencia_pago >= 0 else 'sube'} {formato(abs(diferencia_pago))} al "
                             f"mes, pero pagas {formato(abs(diferencia_costo))} "
                             f"{'más' if diferencia_costo >= 0 else 'menos'} en intereses y cargos.", 14,
                             ft.FontWeight.W_600, NARANJA if diferencia_costo > 0 else VERDE),
                       ayuda("«Como estoy» usa las compras y deudas registradas en la app para esta tarjeta; si no las "
                             "registraste todas, la comparación es parcial.")]
        self.resumen.controls = lineas
        self.tabla.cargar([(q.numero, [q.numero, q.fecha.isoformat(), pesos(q.capital), pesos(q.interes),
                                       pesos(q.total)]) for q in r.cronograma])

    async def _registrar(self, _e=None) -> None:
        if not self.resultado:
            return
        fecha, r = self.resultado
        alcance = "Las compras y deudas activas de esta tarjeta" if self._ids() is None else "La deuda elegida"
        if not await self.pagina.confirmar(f"{alcance} quedarán reemplazadas por la deuda organizada. ¿Registrar?",
                                           si="Registrar"):
            return
        try:
            self.repo.registrar_refinanciacion(self.producto["id"], fecha, r,
                                               "acuerdo_pago" if self.acuerdo.value else "refinanciacion",
                                               credito_ids=self._ids())
        except ValueError as e:
            self.mensaje.value = str(e)
            self.pagina.page.update()
            return
        cerrar(self.pagina.page, self.dialogo)
        self.pagina.cambio()
        self.pagina.notificar("Refinanciación registrada")
