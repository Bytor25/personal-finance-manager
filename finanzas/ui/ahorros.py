"""Ahorros: cajas por objetivo, cuánto y cuándo ahorrar, saldo a favor y patrimonio."""

from datetime import date

import customtkinter as ctk

from ..ahorro import NOMBRE_PRIORIDAD, TIPOS_META, repartir
from ..dinero import formato, porcentaje
from ..fechas import nombre_periodo, periodo, periodo_siguiente
from .app import Pagina
from .graficas import Grafica
from .widgets import (FONDO_TARJETA, FUENTE_NORMAL, FUENTE_PEQUENA, FUENTE_SUBTITULO, GRIS, MORADO, NARANJA, ROJO,
                      VERDE, Campo, Formulario, SelectorMes, Tabla, TarjetaCifra, confirmar, error, hoy_texto,
                      parsear_fecha, pesos)

ESTADOS = {"activa": "Activa", "pausada": "Pausada", "archivada": "Archivada"}


def barra_texto(progreso: float, ancho: int = 10) -> str:
    llenos = round(progreso * ancho)
    return "█" * llenos + "░" * (ancho - llenos) + f" {porcentaje(progreso, 0)}"


def dialogo_repartir(pagina: Pagina, monto: int, fecha: date, titulo: str = "Repartir un abono entre tus cajas",
                     al_terminar=None) -> None:
    """Pide fecha y valor, muestra cómo se reparte entre las cajas activas y registra los abonos."""
    repo = pagina.repo
    if not repo.metas_para_reparto():
        return error(pagina, "No tienes cajas activas por completar. Crea una en «Ahorros» → «+ Nueva caja».")
    campos = [Campo("fecha", "Fecha", "fecha", defecto=fecha.isoformat()),
              Campo("monto", "Valor a repartir", "monto", defecto=formato(monto, signo=False) if monto else None,
                    ayuda="Se reparte primero a las cajas con fecha (lo que necesitan al mes para llegar a tiempo) "
                          "y el resto según la prioridad.")]

    def guardar(v: dict) -> None:
        metas = repo.metas_para_reparto()
        asignaciones = [a for a in repartir(v["monto"], metas, periodo(v["fecha"])) if a.mensual > 0]
        if not asignaciones:
            raise ValueError("Tus cajas activas ya están completas.")
        total = sum(a.mensual for a in asignaciones)
        detalle = "\n".join(f"• {a.meta.nombre}: {formato(a.mensual)}" for a in asignaciones)
        sobra = v["monto"] - total
        texto = f"Se abonará así:\n\n{detalle}"
        if sobra:
            texto += f"\n\nSobran {formato(sobra)}: tus cajas ya quedan completas con eso."
        disponible = repo.saldo_disponible(v["fecha"])
        if total > disponible:
            texto += (f"\n\n⚠ Tu disponible al {v['fecha'].isoformat()} es {formato(disponible)}: este abono lo deja "
                      "en negativo. ¿Registraste todos tus ingresos?")
        if not confirmar(pagina, texto + "\n\n¿Registrar los abonos?"):
            raise ValueError("No se registró nada.")
        for a in asignaciones:
            repo.abonar_meta(a.meta.id, v["fecha"], a.mensual, notas="Reparto automático")
        if al_terminar:
            al_terminar()
        pagina.app.datos_cambiaron()

    Formulario(pagina, titulo, campos, guardar)


class PaginaAhorros(Pagina):
    titulo = "Ahorros (cajas)"

    def construir(self) -> None:
        ctk.CTkLabel(self.encabezado, text="Planear el mes:", text_color=GRIS).pack(side="left", padx=(20, 6))
        self.selector = SelectorMes(self.encabezado, lambda _p: self.refrescar())
        self.selector.pack(side="left")
        # Por defecto se planea el mes siguiente.
        self.selector.periodo = periodo_siguiente(periodo(date.today()))
        self.selector.etiqueta.configure(text=nombre_periodo(self.selector.periodo))

        fila = ctk.CTkFrame(self, fg_color="transparent")
        fila.pack(fill="x", padx=24, pady=4)
        fila.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="a")
        self.t_disponible = TarjetaCifra(fila, "💰 Disponible hoy", VERDE)
        self.t_cajas = TarjetaCifra(fila, "🐷 En tus cajas", VERDE)
        self.t_reserva = TarjetaCifra(fila, "🏦 En la reserva")
        self.t_patrimonio = TarjetaCifra(fila, "📊 Patrimonio", MORADO)
        for i, t in enumerate((self.t_disponible, self.t_cajas, self.t_reserva, self.t_patrimonio)):
            t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0))
        botones = self.fila_botones()
        ctk.CTkButton(botones, text="Ajustar mi disponible", fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self._ajustar).pack(side="left")
        ctk.CTkLabel(botones, text="Úsalo si lo que tienes en tu cuenta no coincide con el disponible de la app.",
                     text_color=GRIS).pack(side="left", padx=10)

        self.capacidad = ctk.CTkFrame(self, fg_color=FONDO_TARJETA, corner_radius=12)
        self.capacidad.pack(fill="x", padx=24, pady=8)
        acciones = self.fila_botones()
        self.b_repartir = ctk.CTkButton(acciones, text="Repartir un abono entre cajas…", command=self._repartir)
        self.b_repartir.pack(side="left")
        self.b_saldo = ctk.CTkButton(acciones, text="Mover saldo a favor a las cajas", command=self._mover_saldo)
        self.b_saldo.pack(side="left", padx=6)

        self.seccion("Gastos previstos del mes",
                     "Gastos puntuales que sabes que vienen (regalo, matrícula, SOAT, un viaje corto…). Se restan "
                     "antes de calcular cuánto puedes ahorrar.")
        b = self.fila_botones()
        ctk.CTkButton(b, text="+ Gasto previsto", command=lambda: self._gasto()).pack(side="left")
        ctk.CTkButton(b, text="Editar", command=lambda: self._gasto(self.t_gastos.seleccionado())
                      ).pack(side="left", padx=6)
        ctk.CTkButton(b, text="Eliminar", fg_color="transparent", border_width=1, text_color=("gray10", "gray90"),
                      command=self._eliminar_gasto).pack(side="left")
        self.t_gastos = self.bloque(lambda m: Tabla(m, [("Gasto", 500, "izq"), ("Valor", 160, "der")], alto=3,
                                                    al_doble_click=self._gasto))

        self.seccion("Tus cajas",
                     "Una caja por objetivo. Doble clic para abonar. «Sugerido al mes» sale del cálculo de arriba; "
                     "«¿Cuándo?» es el mes en que la completas abonando eso.")
        b = self.fila_botones()
        ctk.CTkButton(b, text="+ Nueva caja", command=lambda: self._caja()).pack(side="left")
        ctk.CTkButton(b, text="Abonar", command=lambda: self._abonar(self.t_cajas_tabla.seleccionado())
                      ).pack(side="left", padx=6)
        ctk.CTkButton(b, text="Retirar / usar", command=self._retirar).pack(side="left")
        ctk.CTkButton(b, text="Editar", command=lambda: self._caja(self.t_cajas_tabla.seleccionado())
                      ).pack(side="left", padx=6)
        ctk.CTkButton(b, text="Eliminar", fg_color="transparent", border_width=1, text_color=("gray10", "gray90"),
                      command=self._eliminar_caja).pack(side="left")
        self.ver_archivadas = ctk.CTkCheckBox(b, text="Ver archivadas", command=self.refrescar)
        self.ver_archivadas.pack(side="left", padx=12)
        self.t_cajas_tabla = self.bloque(lambda m: Tabla(
            m, [("Caja", 170, "izq"), ("Tipo", 150, "izq"), ("Prioridad", 70, "centro"), ("Meta", 110, "der"),
                ("Ahorrado", 110, "der"), ("Progreso", 140, "izq"), ("Falta", 110, "der"),
                ("Fecha objetivo", 100, "centro"), ("Sugerido al mes", 120, "der"), ("¿Cuándo?", 150, "izq")],
            alto=7, al_doble_click=self._abonar))

        self.seccion("Movimientos de las cajas")
        b = self.fila_botones()
        ctk.CTkButton(b, text="Eliminar movimiento", fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self._eliminar_movimiento).pack(side="left")
        self.t_movimientos = self.bloque(lambda m: Tabla(
            m, [("Fecha", 100, "centro"), ("Caja", 180, "izq"), ("Movimiento", 160, "izq"), ("Valor", 130, "der"),
                ("Notas", 380, "izq")], alto=6))

        self.g_patrimonio = Grafica(self, alto=3.0)
        self.g_patrimonio.pack(fill="x", padx=24, pady=(12, 20))

    # ------------------------------------------------------------ refrescar

    def refrescar(self) -> None:
        repo = self.repo
        hoy = date.today()
        per_hoy = periodo(hoy)
        p = repo.patrimonio(hoy)
        favor = repo.saldo_favor_mes(per_hoy)
        anterior = nombre_periodo(periodo_siguiente(per_hoy, -1))
        self.t_disponible.mostrar(formato(p["disponible"]),
                                  f"Saldo a favor que traes de {anterior}: {formato(favor)}",
                                  VERDE if p["disponible"] >= 0 else ROJO)
        metas = repo.metas_ahorro(bool(self.ver_archivadas.get()))
        activas = [m for m in metas if m["estado"] == "activa"]
        objetivo = sum(m["objetivo"] for m in activas)
        self.t_cajas.mostrar(formato(p["cajas"]), f"{len(activas)} cajas activas · meta total {formato(objetivo)}")
        self.t_reserva.mostrar(formato(p["reserva"]), "Para el pago de deudas del mes siguiente")
        self.t_patrimonio.mostrar(formato(p["patrimonio"]),
                                  f"Tienes {formato(p['activos'])} − debes {formato(p['deuda'])}",
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
                cuando = "✅ ¡Completa!"
            elif m["estado"] != "activa":
                cuando = ESTADOS[m["estado"]]
            elif a and a.periodo_estimado:
                cuando = nombre_periodo(a.periodo_estimado) + {True: " ✅", False: " ⚠ tarde"}.get(a.a_tiempo, "")
            else:
                cuando = "Sin ahorro sugerido"
            sugerido = pesos(a.mensual) if a and a.mensual else "—"
            if a and a.necesaria and a.mensual < a.necesaria:
                sugerido += f" (necesita {formato(a.necesaria)})"
            filas.append((m["id"], [m["nombre"], TIPOS_META.get(m["tipo"], m["tipo"]),
                                    NOMBRE_PRIORIDAD[m["prioridad"]], pesos(m["objetivo"]), pesos(m["ahorrado"]),
                                    barra_texto(progreso), pesos(falta), m["fecha_objetivo"] or "—", sugerido,
                                    cuando]))
        self.t_cajas_tabla.cargar(filas)
        tipos = {"abono": "Abono", "retiro": "Retiro / uso"}
        self.t_movimientos.cargar([
            (mv["id"], [mv["fecha"], mv["meta"], tipos[mv["tipo"]] + (" (ya ahorrado)" if mv["externo"] else ""),
                        pesos(mv["monto"]), mv["notas"]]) for mv in repo.movimientos_ahorro()][:200])
        self.g_patrimonio.patrimonio(repo.historial_patrimonio(6, hoy))

    def _mostrar_capacidad(self, cap, mes: str, anterior: str) -> None:
        for w in self.capacidad.winfo_children():
            w.destroy()
        e = cap.entrada

        def linea(texto: str, color_texto=None, fuente=FUENTE_NORMAL, pady=0) -> None:
            ctk.CTkLabel(self.capacidad, text=texto, text_color=color_texto, font=fuente, anchor="w",
                         justify="left", wraplength=1000).pack(fill="x", padx=14, pady=pady)

        linea(f"🧮 ¿Cuánto y cuándo puedo ahorrar en {mes}?", fuente=FUENTE_SUBTITULO, pady=(12, 2))
        if not e.ingreso:
            linea("Configura tus fuentes de ingreso (Configuración → Ingresos) para calcularlo.", NARANJA,
                  pady=(0, 12))
            self.b_saldo.configure(state="disabled")
            return
        linea(f"Ingreso estimado {formato(e.ingreso)}  −  cuotas y tarjetas {formato(e.pagos_deuda)}  −  servicios "
              f"{formato(e.servicios)}  −  día a día {formato(e.dia_a_dia)}  −  gastos previstos "
              f"{formato(e.gastos_previstos)}  =  te quedan {formato(cap.capacidad)}", GRIS, FUENTE_PEQUENA)
        if not e.dia_a_dia:
            linea("⚠ Aún no hay promedio de gastos del día a día (comida, transporte…): ponlo en Configuración → "
                  "Parámetros para no sobrestimar lo que puedes ahorrar.", NARANJA, pady=(4, 0))
        if cap.deficit:
            linea(f"⚠ Los gastos de {mes} superan tu ingreso en {formato(cap.deficit)}: ese mes no conviene "
                  "ahorrar. Revisa los gastos previstos o los gastos «deseo».", ROJO, pady=(6, 0))
        else:
            linea(f"✅ Ahorro sugerido en {mes}: {formato(cap.sugerido)} ({porcentaje(e.pct_ahorro, 0)} de lo que "
                  f"te queda, según tu nivel de deuda). Como máximo podrías apartar {formato(cap.capacidad)}.",
                  VERDE, pady=(6, 0))
            if cap.por_fecha:
                cuando = "   ·   ".join(f"el {f.day} de {mes.split()[0]}: {formato(m)}" for f, m in cap.por_fecha)
                linea(f"📅 Cuándo apartarlo (cada vez que te paguen): {cuando}")
        if e.saldo_favor:
            if cap.extra_saldo_favor:
                nota = (f"💰 Trajiste {formato(e.saldo_favor)} de saldo a favor de {anterior}. "
                        + (f"Después de completar la reserva ({formato(e.falta_reserva)}), " if e.falta_reserva
                           else "")
                        + f"puedes mover {formato(cap.extra_saldo_favor)} a tus cajas.")
                linea(nota, VERDE)
            else:
                linea(f"💰 Trajiste {formato(e.saldo_favor)} de saldo a favor de {anterior}, pero la reserva del mes "
                      f"adelantado aún necesita {formato(e.falta_reserva)}: complétala primero.", NARANJA)
        self.b_saldo.configure(state="normal" if cap.extra_saldo_favor else "disabled",
                               text=f"Mover {formato(cap.extra_saldo_favor)} de saldo a favor a las cajas"
                               if cap.extra_saldo_favor else "Mover saldo a favor a las cajas")
        ctk.CTkFrame(self.capacidad, height=8, fg_color="transparent").pack()

    # ------------------------------------------------------------ acciones

    def _repartir(self) -> None:
        cap = getattr(self, "_cap", None)
        monto = cap.por_fecha[0][1] if cap and cap.por_fecha else (cap.sugerido if cap else 0)
        dialogo_repartir(self, monto, date.today())

    def _mover_saldo(self) -> None:
        cap = getattr(self, "_cap", None)
        if cap and cap.extra_saldo_favor:
            dialogo_repartir(self, cap.extra_saldo_favor, date.today(), "Mover saldo a favor a las cajas")

    def _ajustar(self) -> None:
        campos = [Campo("fecha", "Fecha", "fecha", defecto=hoy_texto()),
                  Campo("saldo", "¿Cuánto tienes de verdad en tu cuenta y bolsillo?", "monto",
                        ayuda="Sin contar la reserva (Cajita) ni lo que está en tus cajas de ahorro. La app guarda "
                              "la diferencia como un ajuste."),
                  Campo("notas", "Notas", opcional=True)]

        def guardar(v: dict) -> None:
            self.repo.ajustar_disponible(v["fecha"], v["saldo"], v["notas"] or "")
            self.app.datos_cambiaron()

        Formulario(self, "Ajustar mi disponible", campos, guardar)

    def _caja(self, id_: int | None = None) -> None:
        m = self.repo.meta_ahorro(id_) if id_ is not None else None
        campos = [
            Campo("nombre", "¿Para qué ahorras?", defecto=m["nombre"] if m else None,
                  ayuda="Ej.: Viaje a Cartagena, PS5, Tenis, Fondo de emergencia."),
            Campo("tipo", "Tipo", "opcion", [(v, k) for k, v in TIPOS_META.items()],
                  defecto=m["tipo"] if m else "otro"),
            Campo("objetivo", "¿Cuánto necesitas?", "monto",
                  defecto=formato(m["objetivo"], signo=False) if m else None),
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
            self.app.datos_cambiaron()

        Formulario(self, "Editar caja" if m else "Nueva caja de ahorro", campos, guardar)

    def _abonar(self, id_: int | None) -> None:
        if id_ is None:
            return error(self, "Selecciona una caja.")
        m = self.repo.meta_ahorro(id_)
        falta = max(0, m["objetivo"] - m["ahorrado"])
        campos = [Campo("fecha", "Fecha", "fecha", defecto=hoy_texto()),
                  Campo("monto", "Valor", "monto", ayuda=f"Le faltan {formato(falta)} para la meta."),
                  Campo("externo", "Esta plata ya la tenía ahorrada (no sale de mi disponible)", "check"),
                  Campo("notas", "Notas", opcional=True)]

        def guardar(v: dict) -> None:
            if not v["externo"]:
                disponible = self.repo.saldo_disponible(v["fecha"])
                if v["monto"] > disponible and not confirmar(
                        self, f"Tu disponible al {v['fecha'].isoformat()} es {formato(disponible)}: este abono lo "
                              "deja en negativo. ¿Registraste todos tus ingresos?\n\n¿Abonar de todas formas?"):
                    raise ValueError("Abono no registrado.")
            self.repo.abonar_meta(id_, v["fecha"], v["monto"], bool(v["externo"]), v["notas"] or "")
            self.app.datos_cambiaron()

        Formulario(self, f"Abonar a «{m['nombre']}»", campos, guardar, texto_boton="Abonar")

    def _retirar(self) -> None:
        id_ = self.t_cajas_tabla.seleccionado()
        if id_ is None:
            return error(self, "Selecciona una caja.")
        m = self.repo.meta_ahorro(id_)
        categorias = [(c["nombre"], c["id"]) for c in self.repo.categorias()]
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
            self.app.datos_cambiaron()

        Formulario(self, f"Retirar de «{m['nombre']}»", campos, guardar, texto_boton="Retirar")

    def _eliminar_caja(self) -> None:
        id_ = self.t_cajas_tabla.seleccionado()
        if id_ is None:
            return error(self, "Selecciona una caja.")
        if confirmar(self, "¿Eliminar esta caja?"):
            try:
                self.repo.eliminar_meta_ahorro(id_)
            except ValueError as e:
                return error(self, str(e))
            self.app.datos_cambiaron()

    def _eliminar_movimiento(self) -> None:
        id_ = self.t_movimientos.seleccionado()
        if id_ is None:
            return error(self, "Selecciona un movimiento.")
        if confirmar(self, "¿Eliminar este movimiento? Si fue un retiro con compra, también se elimina la compra."):
            try:
                self.repo.eliminar_movimiento_ahorro(id_)
            except ValueError as e:
                return error(self, str(e))
            self.app.datos_cambiaron()

    def _gasto(self, id_: int | None = None) -> None:
        per = self.selector.periodo
        g = next((x for x in self.repo.gastos_previstos(per) if x["id"] == id_), None) if id_ is not None else None
        campos = [Campo("descripcion", "¿Qué gasto es?", defecto=g["descripcion"] if g else None),
                  Campo("monto", "Valor", "monto", defecto=formato(g["monto"], signo=False) if g else None)]

        def guardar(v: dict) -> None:
            self.repo.guardar_gasto_previsto(id_, per, v["descripcion"], v["monto"])
            self.refrescar()

        Formulario(self, f"Gasto previsto para {nombre_periodo(per)}", campos, guardar)

    def _eliminar_gasto(self) -> None:
        id_ = self.t_gastos.seleccionado()
        if id_ is None:
            return error(self, "Selecciona un gasto.")
        self.repo.eliminar_gasto_previsto(id_)
        self.refrescar()
