"""Ahorros: cajas por objetivo, cuánto y cuándo ahorrar, saldo a favor y patrimonio."""

from datetime import date

import flet as ft

from ...ahorro import NOMBRE_PRIORIDAD, TIPOS_META, repartir
from ...campos import Campo, hoy_texto, parsear_fecha, pesos
from ...dinero import formato, porcentaje
from ...fechas import nombre_periodo, periodo, periodo_siguiente
from .. import graficas
from ..componentes import (Pagina, SelectorMes, Tabla, TarjetaCifra, ayuda, barra_botones, boton, contenedor,
                           requiere, seccion, texto, titulo_seccion, tarjeta)
from ..tema import GRIS, MORADO, NARANJA, ROJO, VERDE, c

ESTADOS = {"activa": "Activa", "pausada": "Pausada", "archivada": "Archivada"}


def barra_progreso(progreso: float, completa: bool) -> ft.Control:
    return ft.Row([ft.ProgressBar(value=progreso, width=90, bar_height=8, border_radius=4,
                                  color=c(VERDE if completa else MORADO)),
                   ft.Text(porcentaje(progreso, 0), size=12)], spacing=8, tight=True)


def dialogo_repartir(pagina: Pagina, monto: int, fecha: date, titulo: str = "Repartir un abono entre tus cajas",
                     al_terminar=None) -> None:
    """Pide fecha y valor, muestra cómo se reparte entre las cajas activas y registra los abonos."""
    repo = pagina.repo
    if not repo.metas_para_reparto():
        return pagina.error("No tienes cajas activas por completar. Crea una en «Ahorros» → «Nueva caja».")
    campos = [Campo("fecha", "Fecha", "fecha", defecto=fecha.isoformat()),
              Campo("monto", "Valor a repartir", "monto", defecto=formato(monto, signo=False) if monto else None,
                    ayuda="Se reparte primero a las cajas con fecha (lo que necesitan al mes para llegar a tiempo) "
                          "y el resto según la prioridad.")]

    async def guardar(v: dict) -> None:
        metas = repo.metas_para_reparto()
        asignaciones = [a for a in repartir(v["monto"], metas, periodo(v["fecha"])) if a.mensual > 0]
        if not asignaciones:
            raise ValueError("Tus cajas activas ya están completas.")
        total = sum(a.mensual for a in asignaciones)
        detalle = "\n".join(f"• {a.meta.nombre}: {formato(a.mensual)}" for a in asignaciones)
        sobra = v["monto"] - total
        mensaje = f"Se abonará así:\n\n{detalle}"
        if sobra:
            mensaje += f"\n\nSobran {formato(sobra)}: tus cajas ya quedan completas con eso."
        disponible = repo.saldo_disponible(v["fecha"])
        if total > disponible:
            mensaje += (f"\n\n⚠ Tu disponible al {v['fecha'].isoformat()} es {formato(disponible)}: este abono lo "
                        "deja en negativo. ¿Registraste todos tus ingresos?")
        if not await pagina.confirmar(mensaje, titulo="¿Registrar los abonos?", si="Registrar"):
            raise ValueError("No se registró nada.")
        for a in asignaciones:
            repo.abonar_meta(a.meta.id, v["fecha"], a.mensual, notas="Reparto automático")
        if al_terminar:
            al_terminar()
        pagina.cambio()
        pagina.notificar(f"Se abonaron {formato(total)} a tus cajas")

    pagina.formulario(titulo, campos, guardar)


class PaginaAhorros(Pagina):
    titulo = "Ahorros (cajas)"

    def construir(self) -> None:
        self.selector = SelectorMes(lambda _p: self.app.datos_cambiaron(), periodo_siguiente(periodo(date.today())))
        self.acciones.controls += [ft.Text("Planear el mes:", color=GRIS), self.selector.vista]

        self.t_disponible = TarjetaCifra("💰 Disponible hoy", VERDE)
        self.t_cajas = TarjetaCifra("🐷 En tus cajas", VERDE)
        self.t_reserva = TarjetaCifra("🏦 En la reserva")
        self.t_patrimonio = TarjetaCifra("📊 Patrimonio", MORADO)
        self.capacidad = contenedor()
        self.b_repartir = boton("Repartir un abono entre cajas…", self._repartir, ft.Icons.CALL_SPLIT)
        self.b_saldo = boton("Mover saldo a favor a las cajas", self._mover_saldo, ft.Icons.MOVE_DOWN, "tonal")
        self.t_gastos = Tabla([("Gasto", "izq"), ("Valor", "der")], al_doble_clic=self._gasto,
                              vacio="Sin gastos previstos para este mes.")
        self.ver_archivadas = ft.Checkbox(label="Ver archivadas", on_change=lambda _e: self.app.datos_cambiaron())
        self.t_cajas_tabla = Tabla(
            [("Caja", "izq"), ("Tipo", "izq"), ("Prioridad", "centro"), ("Meta", "der"), ("Ahorrado", "der"),
             ("Progreso", "izq"), ("Falta", "der"), ("Fecha objetivo", "centro"), ("Sugerido al mes", "der"),
             ("¿Cuándo?", "izq")], al_doble_clic=self._abonar, vacio="Crea tu primera caja con «Nueva caja».")
        self.t_movimientos = Tabla([("Fecha", "centro"), ("Caja", "izq"), ("Movimiento", "izq"), ("Valor", "der"),
                                    ("Notas", "izq")], vacio="Sin movimientos todavía.")
        self.g_patrimonio = ft.ResponsiveRow()

        self.agregar(
            ft.ResponsiveRow([t.vista for t in (self.t_disponible, self.t_cajas, self.t_reserva, self.t_patrimonio)],
                             spacing=14, run_spacing=14),
            barra_botones(boton("Ajustar mi disponible", self._ajustar, ft.Icons.TUNE, "borde"),
                          ayuda("Úsalo si lo que tienes en tu cuenta no coincide con el disponible de la app.")),
            tarjeta(self.capacidad, barra_botones(self.b_repartir, self.b_saldo), espacio=10),
            seccion("Gastos previstos del mes",
                    barra_botones(boton("Gasto previsto", lambda _e: self._gasto(), ft.Icons.ADD),
                                  boton("Editar", lambda _e: self._gasto(self.t_gastos.seleccionado()),
                                        ft.Icons.EDIT_OUTLINED, "tonal"),
                                  boton("Eliminar", self._eliminar_gasto, ft.Icons.DELETE_OUTLINE, "borde")),
                    self.t_gastos.vista,
                    explicacion="Gastos puntuales que sabes que vienen (regalo, matrícula, SOAT, un viaje corto…). "
                                "Se restan antes de calcular cuánto puedes ahorrar."),
            seccion("Tus cajas",
                    barra_botones(boton("Nueva caja", lambda _e: self._caja(), ft.Icons.ADD),
                                  boton("Abonar", lambda _e: self._abonar(self.t_cajas_tabla.seleccionado()),
                                        ft.Icons.SAVINGS, color=VERDE),
                                  boton("Retirar / usar", self._retirar, ft.Icons.OUTBOX, "tonal"),
                                  boton("Editar", lambda _e: self._caja(self.t_cajas_tabla.seleccionado(), True),
                                        ft.Icons.EDIT_OUTLINED, "tonal"),
                                  boton("Eliminar", self._eliminar_caja, ft.Icons.DELETE_OUTLINE, "borde"),
                                  self.ver_archivadas),
                    self.t_cajas_tabla.vista,
                    explicacion="Una caja por objetivo. Doble clic para abonar. «Sugerido al mes» sale del cálculo "
                                "de arriba; «¿Cuándo?» es el mes en que la completas abonando eso."),
            seccion("Movimientos de las cajas",
                    barra_botones(boton("Eliminar movimiento", self._eliminar_movimiento, ft.Icons.DELETE_OUTLINE,
                                        "borde")),
                    self.t_movimientos.vista),
            self.g_patrimonio,
        )

    # ------------------------------------------------------------ refrescar

    def refrescar(self) -> None:
        repo = self.repo
        hoy = date.today()
        per_hoy = periodo(hoy)
        p = repo.patrimonio(hoy)
        favor = repo.saldo_favor_mes(per_hoy)
        anterior = nombre_periodo(periodo_siguiente(per_hoy, -1))
        self.t_disponible.mostrar(formato(p["disponible"]), f"Saldo a favor que traes de {anterior}: {formato(favor)}",
                                  VERDE if p["disponible"] >= 0 else ROJO)
        metas = repo.metas_ahorro(bool(self.ver_archivadas.value))
        activas = [m for m in metas if m["estado"] == "activa"]
        objetivo = sum(m["objetivo"] for m in activas)
        self.t_cajas.mostrar(formato(p["cajas"]), f"{len(activas)} cajas activas · meta total {formato(objetivo)}")
        self.t_reserva.mostrar(formato(p["reserva"]), "Para el pago de deudas del mes siguiente")
        self.t_patrimonio.mostrar(formato(p["patrimonio"]), f"Tienes {formato(p['activos'])} − debes "
                                                            f"{formato(p['deuda'])}",
                                  MORADO if p["patrimonio"] >= 0 else ROJO)

        per = self.selector.periodo
        cap, asignaciones = repo.plan_ahorro(per, hoy)
        self._cap = cap
        self._mostrar_capacidad(cap, nombre_periodo(per), anterior)
        self.t_gastos.cargar([(g["id"], [g["descripcion"], pesos(g["monto"])]) for g in repo.gastos_previstos(per)])

        por_meta = {a.meta.id: a for a in asignaciones}
        filas = []
        for m in metas:
            a = por_meta.get(m["id"])
            falta = max(0, m["objetivo"] - m["ahorrado"])
            progreso = min(1.0, m["ahorrado"] / m["objetivo"]) if m["objetivo"] else 1.0
            if falta == 0:
                cuando = ("✅ ¡Completa!", VERDE)
            elif m["estado"] != "activa":
                cuando = ESTADOS[m["estado"]]
            elif a and a.periodo_estimado:
                cuando = (nombre_periodo(a.periodo_estimado) + {True: " ✅", False: " ⚠ tarde"}.get(a.a_tiempo, ""),
                          NARANJA if a.a_tiempo is False else None)
            else:
                cuando = "Sin ahorro sugerido"
            sugerido = pesos(a.mensual) if a and a.mensual else "—"
            if a and a.necesaria and a.mensual < a.necesaria:
                sugerido += f" (necesita {formato(a.necesaria)})"
            filas.append((m["id"], [m["nombre"], TIPOS_META.get(m["tipo"], m["tipo"]), NOMBRE_PRIORIDAD[m["prioridad"]],
                                    pesos(m["objetivo"]), pesos(m["ahorrado"]), barra_progreso(progreso, falta == 0),
                                    pesos(falta), m["fecha_objetivo"] or "—", sugerido, cuando]))
        self.t_cajas_tabla.cargar(filas)
        tipos = {"abono": "Abono", "retiro": "Retiro / uso"}
        self.t_movimientos.cargar([
            (mv["id"], [mv["fecha"], mv["meta"], tipos[mv["tipo"]] + (" (ya ahorrado)" if mv["externo"] else ""),
                        (pesos(mv["monto"]), VERDE if mv["tipo"] == "abono" else NARANJA), mv["notas"]])
            for mv in repo.movimientos_ahorro()][:200])
        self.g_patrimonio.controls = [graficas.patrimonio(repo.historial_patrimonio(6, hoy))]

    def _mostrar_capacidad(self, cap, mes: str, anterior: str) -> None:
        e = cap.entrada
        lineas: list[ft.Control] = [titulo_seccion(f"🧮 ¿Cuánto y cuándo puedo ahorrar en {mes}?")]
        if not e.ingreso:
            lineas.append(texto("Configura tus fuentes de ingreso (Configuración → Ingresos) para calcularlo.", 13,
                                color=NARANJA))
            self.capacidad.controls = lineas
            self.b_saldo.disabled = True
            return
        lineas.append(ayuda(f"Ingreso estimado {formato(e.ingreso)}  −  cuotas y tarjetas {formato(e.pagos_deuda)}  −  "
                            f"servicios {formato(e.servicios)}  −  día a día {formato(e.dia_a_dia)}  −  gastos "
                            f"previstos {formato(e.gastos_previstos)}  =  te quedan {formato(cap.capacidad)}"))
        if not e.dia_a_dia:
            lineas.append(texto("⚠ Aún no hay promedio de gastos del día a día (comida, transporte…): ponlo en "
                                "Configuración → Parámetros para no sobrestimar lo que puedes ahorrar.", 13,
                                color=NARANJA))
        if cap.deficit:
            lineas.append(texto(f"⚠ Los gastos de {mes} superan tu ingreso en {formato(cap.deficit)}: ese mes no "
                                "conviene ahorrar. Revisa los gastos previstos o los gastos «deseo».", 13, color=ROJO))
        else:
            lineas.append(texto(f"✅ Ahorro sugerido en {mes}: {formato(cap.sugerido)} ({porcentaje(e.pct_ahorro, 0)} "
                                f"de lo que te queda, según tu nivel de deuda). Como máximo podrías apartar "
                                f"{formato(cap.capacidad)}.", 14, ft.FontWeight.W_600, VERDE))
            if cap.por_fecha:
                cuando = "   ·   ".join(f"el {f.day} de {mes.split()[0]}: {formato(m)}" for f, m in cap.por_fecha)
                lineas.append(ft.Text(f"📅 Cuándo apartarlo (cada vez que te paguen): {cuando}", size=13))
        if e.saldo_favor:
            if cap.extra_saldo_favor:
                nota = (f"💰 Trajiste {formato(e.saldo_favor)} de saldo a favor de {anterior}. "
                        + (f"Después de completar la reserva ({formato(e.falta_reserva)}), " if e.falta_reserva else "")
                        + f"puedes mover {formato(cap.extra_saldo_favor)} a tus cajas.")
                lineas.append(texto(nota, 13, color=VERDE))
            else:
                lineas.append(texto(f"💰 Trajiste {formato(e.saldo_favor)} de saldo a favor de {anterior}, pero la "
                                    f"reserva del mes adelantado aún necesita {formato(e.falta_reserva)}: complétala "
                                    "primero.", 13, color=NARANJA))
        self.capacidad.controls = lineas
        self.b_saldo.disabled = not cap.extra_saldo_favor
        self.b_saldo.content = (f"Mover {formato(cap.extra_saldo_favor)} de saldo a favor a las cajas"
                                if cap.extra_saldo_favor else "Mover saldo a favor a las cajas")

    # ------------------------------------------------------------ acciones

    def _repartir(self, _e=None) -> None:
        cap = getattr(self, "_cap", None)
        monto = cap.por_fecha[0][1] if cap and cap.por_fecha else (cap.sugerido if cap else 0)
        dialogo_repartir(self, monto, date.today())

    def _mover_saldo(self, _e=None) -> None:
        cap = getattr(self, "_cap", None)
        if cap and cap.extra_saldo_favor:
            dialogo_repartir(self, cap.extra_saldo_favor, date.today(), "Mover saldo a favor a las cajas")

    def _ajustar(self, _e=None) -> None:
        campos = [Campo("fecha", "Fecha", "fecha", defecto=hoy_texto()),
                  Campo("saldo", "¿Cuánto tienes de verdad en tu cuenta y bolsillo?", "monto",
                        ayuda="Sin contar la reserva (Cajita) ni lo que está en tus cajas de ahorro. La app guarda "
                              "la diferencia como un ajuste."),
                  Campo("notas", "Notas", opcional=True)]

        def guardar(v: dict) -> None:
            self.repo.ajustar_disponible(v["fecha"], v["saldo"], v["notas"] or "")
            self.cambio()

        self.formulario("Ajustar mi disponible", campos, guardar)

    def _caja(self, id_: int | None = None, editar: bool = False) -> None:
        if editar and id_ is None:
            return self.error("Selecciona una caja en la tabla.")
        m = self.repo.meta_ahorro(id_) if id_ is not None else None
        campos = [
            Campo("nombre", "¿Para qué ahorras?", defecto=m["nombre"] if m else None,
                  ayuda="Ej.: Viaje a Cartagena, PS5, Tenis, Fondo de emergencia."),
            Campo("tipo", "Tipo", "opcion", [(v, k) for k, v in TIPOS_META.items()], defecto=m["tipo"] if m else "otro"),
            Campo("objetivo", "¿Cuánto necesitas?", "monto", defecto=formato(m["objetivo"], signo=False) if m else None),
            Campo("fecha", "¿Para cuándo? (fecha objetivo)", "fecha", opcional=True,
                  defecto=m["fecha_objetivo"] if m else None,
                  ayuda="Con fecha, la app reserva lo que necesitas cada mes para llegar a tiempo."),
            Campo("prioridad", "Prioridad", "opcion", [(v, k) for k, v in NOMBRE_PRIORIDAD.items()],
                  defecto=m["prioridad"] if m else 2),
            Campo("notas", "Notas", opcional=True, defecto=m["notas"] if m else None),
        ]
        if m:
            campos.insert(5, Campo("estado", "Estado", "opcion", [(v, k) for k, v in ESTADOS.items()],
                                   defecto=m["estado"],
                                   ayuda="Pausada: no recibe ahorro sugerido. Archivada: ya cumplida, se oculta."))
        else:
            campos.append(Campo("inicial", "¿Ya tienes algo ahorrado para esto?", "monto", opcional=True,
                                ayuda="Se registra como plata que ya tenías: no se descuenta de tu disponible."))

        def guardar(v: dict) -> None:
            nuevo = self.repo.guardar_meta_ahorro(id_, v["nombre"], v["tipo"], v["objetivo"], v["fecha"],
                                                  v["prioridad"], v.get("estado") or "activa", v["notas"] or "")
            if not m and v.get("inicial"):
                self.repo.abonar_meta(nuevo, date.today(), v["inicial"], externo=True, notas="Ahorro que ya tenía")
            self.cambio()

        self.formulario("Editar caja" if m else "Nueva caja de ahorro", campos, guardar)

    def _abonar(self, id_: int | None) -> None:
        if id_ is None:
            return self.error("Selecciona una caja en la tabla.")
        m = self.repo.meta_ahorro(id_)
        falta = max(0, m["objetivo"] - m["ahorrado"])
        campos = [Campo("fecha", "Fecha", "fecha", defecto=hoy_texto()),
                  Campo("monto", "Valor", "monto", ayuda=f"Le faltan {formato(falta)} para la meta."),
                  Campo("externo", "Esta plata ya la tenía ahorrada (no sale de mi disponible)", "check"),
                  Campo("notas", "Notas", opcional=True)]

        async def guardar(v: dict) -> None:
            if not v["externo"]:
                disponible = self.repo.saldo_disponible(v["fecha"])
                if v["monto"] > disponible and not await self.confirmar(
                        f"Tu disponible al {v['fecha'].isoformat()} es {formato(disponible)}: este abono lo deja en "
                        "negativo. ¿Registraste todos tus ingresos?", titulo="¿Abonar de todas formas?",
                        si="Abonar igual"):
                    raise ValueError("Abono no registrado.")
            self.repo.abonar_meta(id_, v["fecha"], v["monto"], bool(v["externo"]), v["notas"] or "")
            self.cambio()
            self.notificar(f"Abonaste {formato(v['monto'])} a «{m['nombre']}»")

        self.formulario(f"Abonar a «{m['nombre']}»", campos, guardar, texto_boton="Abonar")

    def _retirar(self, _e=None) -> None:
        id_ = requiere(self.t_cajas_tabla, self, "Selecciona una caja en la tabla.")
        if id_ is None:
            return
        m = self.repo.meta_ahorro(id_)
        categorias = [(c_["nombre"], c_["id"]) for c_ in self.repo.categorias()]
        campos = [Campo("fecha", "Fecha", "fecha", defecto=hoy_texto()),
                  Campo("monto", "Valor", "monto", defecto=formato(max(0, m["ahorrado"]), signo=False),
                        ayuda=f"La caja tiene {formato(m['ahorrado'])}."),
                  Campo("compra", "Lo usé para comprar (registrar también la compra en efectivo)", "check",
                        defecto=m["ahorrado"] >= m["objetivo"]),
                  Campo("descripcion", "¿Qué compraste?", defecto=m["nombre"], visible_si=("compra", True)),
                  Campo("categoria", "Categoría", "opcion", categorias, visible_si=("compra", True)),
                  Campo("archivar", "Archivar la caja (ya cumplí la meta)", "check",
                        defecto=m["ahorrado"] >= m["objetivo"]),
                  Campo("notas", "Notas", opcional=True)]

        def guardar(v: dict) -> None:
            compra = (v["descripcion"] or m["nombre"], v["categoria"]) if v["compra"] else None
            self.repo.retirar_meta(id_, v["fecha"], v["monto"], v["notas"] or "", compra)
            if v["archivar"]:
                self.repo.guardar_meta_ahorro(id_, m["nombre"], m["tipo"], m["objetivo"],
                                              parsear_fecha(m["fecha_objetivo"]) if m["fecha_objetivo"] else None,
                                              m["prioridad"], "archivada", m["notas"])
            self.cambio()

        self.formulario(f"Retirar de «{m['nombre']}»", campos, guardar, texto_boton="Retirar")

    async def _eliminar_caja(self, _e=None) -> None:
        id_ = requiere(self.t_cajas_tabla, self, "Selecciona una caja en la tabla.")
        if id_ is not None and await self.confirmar("¿Eliminar esta caja?", si="Eliminar", peligro=True):
            try:
                self.repo.eliminar_meta_ahorro(id_)
            except ValueError as e:
                return self.error(str(e))
            self.cambio()

    async def _eliminar_movimiento(self, _e=None) -> None:
        id_ = requiere(self.t_movimientos, self, "Selecciona un movimiento en la tabla.")
        if id_ is not None and await self.confirmar(
                "¿Eliminar este movimiento? Si fue un retiro con compra, también se elimina la compra.",
                si="Eliminar", peligro=True):
            try:
                self.repo.eliminar_movimiento_ahorro(id_)
            except ValueError as e:
                return self.error(str(e))
            self.cambio()

    def _gasto(self, id_: int | None = None) -> None:
        per = self.selector.periodo
        g = next((x for x in self.repo.gastos_previstos(per) if x["id"] == id_), None) if id_ is not None else None
        campos = [Campo("descripcion", "¿Qué gasto es?", defecto=g["descripcion"] if g else None),
                  Campo("monto", "Valor", "monto", defecto=formato(g["monto"], signo=False) if g else None)]

        def guardar(v: dict) -> None:
            self.repo.guardar_gasto_previsto(id_, per, v["descripcion"], v["monto"])
            self.cambio()

        self.formulario(f"Gasto previsto para {nombre_periodo(per)}", campos, guardar)

    async def _eliminar_gasto(self, _e=None) -> None:
        id_ = requiere(self.t_gastos, self, "Selecciona un gasto en la tabla.")
        if id_ is not None and await self.confirmar("¿Eliminar este gasto previsto?", si="Eliminar", peligro=True):
            self.repo.eliminar_gasto_previsto(id_)
            self.cambio()
