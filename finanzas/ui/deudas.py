"""Tarjetas y deudas: productos, pagos, extractos, deudas existentes y organizar deuda."""

from datetime import date
from tkinter import messagebox

import customtkinter as ctk

from .. import condiciones as cond_mod
from ..credito import ABONO_CONSTANTE, CUOTA_FIJA, Cargo, Oferta, comparar_ofertas
from ..dinero import a_centavos, a_tasa, formato, porcentaje, tasa
from ..repositorio import metodo_producto
from .app import Pagina
from .condiciones import COBROS, MODALIDADES, PERIODICIDADES, SISTEMAS
from .condiciones import campos as campos_condiciones
from .condiciones import leer as leer_condiciones
from .graficas import Grafica
from .widgets import (FONDO_TARJETA, FUENTE_PEQUENA, FUENTE_SUBTITULO, GRIS, MORADO, NARANJA,
                      ROJO, VERDE, Campo, Formulario, Tabla, confirmar, error, hoy_texto, parsear_fecha, pesos,
                      tamano_ventana)

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
               "este mes, pon la del mes siguiente. Formato AAAA-MM-DD o DD/MM/AAAA.",
    "cupo": "Mírala en la app (Addi, Sistecrédito, almacén): cada compra tiene su propia fecha de pago. "
            "Formato AAAA-MM-DD o DD/MM/AAAA.",
    "prestamo": "La fecha de pago de la próxima cuota del préstamo. Formato AAAA-MM-DD o DD/MM/AAAA.",
}
SUFIJO_TIPO = {"tarjeta": "", "cupo": " (cupo)", "prestamo": " (préstamo)"}
ORIGENES = {"compra": "Compra", "deuda_existente": "Deuda existente", "refinanciacion": "Deuda organizada"}


class PaginaDeudas(Pagina):
    titulo = "Tarjetas y deudas"

    def construir(self) -> None:
        self.seccion("💳 Mis tarjetas y créditos",
                     "Selecciona una fila para registrar un pago, un extracto u organizar su deuda.")
        botones = self.fila_botones()
        ctk.CTkButton(botones, text="+ Tarjeta / crédito", command=lambda: self._dialogo_producto(None)
                      ).pack(side="left")
        ctk.CTkButton(botones, text="Editar", command=self._editar_producto).pack(side="left", padx=6)
        ctk.CTkButton(botones, text="💸 Registrar pago", fg_color=VERDE, command=self._pago).pack(side="left", padx=6)
        ctk.CTkButton(botones, text="📄 Registrar extracto", command=self._extracto).pack(side="left", padx=6)
        ctk.CTkButton(botones, text="🧩 Organizar deuda", fg_color=MORADO, command=self._organizar
                      ).pack(side="left", padx=6)
        ctk.CTkButton(botones, text="+ Cuotas que ya tenía", command=self._deuda_existente).pack(side="left", padx=6)
        botones = self.fila_botones()
        ctk.CTkButton(botones, text="⚙ Condiciones de la tarjeta / cupo", command=self._condiciones
                      ).pack(side="left")
        ctk.CTkButton(botones, text="⚖ Comparar financiación", command=lambda: VentanaComparar(self)
                      ).pack(side="left", padx=6)
        self.t_productos = self.bloque(lambda m: Tabla(
            m, [("Tarjeta / crédito", 170, "izq"), ("Tasa E.A.", 80, "der"), ("Debo (capital)", 120, "der"),
                ("Uso del cupo · disponible", 190, "der"), ("Próximo pago", 100, "centro"), ("Mínimo", 110, "der"),
                ("Total", 110, "der"), ("Si pagas solo el mínimo", 170, "der"), ("Según", 90, "centro")], alto=4))
        ctk.CTkLabel(self, text="«Si pagas solo el mínimo» = intereses aproximados que se generan el mes siguiente "
                                "sobre lo que quedas debiendo.", text_color=GRIS, anchor="w",
                     font=FUENTE_PEQUENA).pack(fill="x", padx=24)

        self.tabs = ctk.CTkTabview(self, height=330)
        self.tabs.pack(fill="x", padx=24, pady=8)
        for nombre in ("Deudas activas", "Pagos", "Mora y cobranza", "Extractos", "Deudas organizadas"):
            self.tabs.add(nombre)

        t = self.tabs.tab("Deudas activas")
        b = ctk.CTkFrame(t, fg_color="transparent")
        b.pack(fill="x")
        ctk.CTkButton(b, text="Ver cronograma y costo", command=self._ver_cronograma).pack(side="left")
        ctk.CTkButton(b, text="↩ Devolución de compra", command=self._devolucion).pack(side="left", padx=8)
        ctk.CTkButton(b, text="Eliminar cuotas que ya tenía", fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self._eliminar_credito).pack(side="left", padx=8)
        self.t_creditos = Tabla(t, [("Tarjeta / crédito", 140, "izq"), ("Descripción", 200, "izq"),
                                    ("Origen", 120, "izq"), ("Fecha", 90, "centro"), ("Valor", 110, "der"),
                                    ("Cuotas restantes", 110, "centro"), ("Saldo", 110, "der"),
                                    ("Próxima cuota", 160, "der")], alto=8,
                                al_doble_click=lambda _id: self._ver_cronograma())
        self.t_creditos.pack(fill="both", expand=True, pady=4)

        t = self.tabs.tab("Pagos")
        b = ctk.CTkFrame(t, fg_color="transparent")
        b.pack(fill="x")
        ctk.CTkButton(b, text="Eliminar pago", fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self._eliminar_pago).pack(side="left")
        ctk.CTkLabel(b, text="Solo se puede eliminar el último pago de cada tarjeta.", text_color=GRIS
                     ).pack(side="left", padx=8)
        self.t_pagos = Tabla(t, [("Fecha", 90, "centro"), ("Tarjeta / crédito", 150, "izq"), ("Tipo", 130, "izq"),
                                 ("Valor", 110, "der"), ("A capital", 110, "der"), ("Intereses y cargos", 130, "der"),
                                 ("Abono extra", 110, "der"), ("Desde reserva", 100, "centro"),
                                 ("Canal", 150, "izq")], alto=8)
        self.t_pagos.pack(fill="both", expand=True, pady=4)

        t = self.tabs.tab("Mora y cobranza")
        b = ctk.CTkFrame(t, fg_color="transparent")
        b.pack(fill="x")
        ctk.CTkButton(b, text="Liquidar mora a hoy", command=self._liquidar_mora).pack(side="left")
        ctk.CTkLabel(b, text="La mora se calcula con la tasa pactada sin superar la usura del periodo "
                             "(Configuración → Tasas legales). Al registrar un pago se liquida sola.",
                     text_color=GRIS).pack(side="left", padx=8)
        self.t_mora = Tabla(t, [("Tarjeta / crédito", 140, "izq"), ("Deuda", 170, "izq"), ("Cuota", 60, "centro"),
                                ("Venció", 90, "centro"), ("Días de mora", 90, "centro"),
                                ("Capital vencido", 120, "der"), ("Pendiente", 110, "der"),
                                ("Mora liquidada", 110, "der"), ("Cobranza liquidada", 120, "der"),
                                ("Por liquidar a hoy", 120, "der")], alto=8)
        self.t_mora.pack(fill="both", expand=True, pady=4)

        t = self.tabs.tab("Extractos")
        b = ctk.CTkFrame(t, fg_color="transparent")
        b.pack(fill="x")
        ctk.CTkButton(b, text="Eliminar extracto", fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self._eliminar_extracto).pack(side="left")
        self.t_extractos = Tabla(t, [("Tarjeta", 140, "izq"), ("Corte", 90, "centro"), ("Fecha límite", 100, "centro"),
                                     ("Capital del mes", 120, "der"), ("Intereses", 110, "der"),
                                     ("Pago mínimo", 120, "der"), ("Deuda restante", 120, "der"),
                                     ("Pago total", 120, "der")], alto=8)
        self.t_extractos.pack(fill="both", expand=True, pady=4)

        t = self.tabs.tab("Deudas organizadas")
        b = ctk.CTkFrame(t, fg_color="transparent")
        b.pack(fill="x")
        ctk.CTkButton(b, text="Eliminar (deshacer)", fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self._eliminar_refi).pack(side="left")
        self.t_refis = Tabla(t, [("Fecha", 90, "centro"), ("Tarjeta", 140, "izq"), ("Deuda antes", 120, "der"),
                                 ("Valor pagado", 110, "der"), ("Saldo organizado", 120, "der"),
                                 ("Cuotas", 70, "centro"), ("Valor cuota", 110, "der"), ("E.A. declarada", 110, "der"),
                                 ("E.A. según cuota", 120, "der")], alto=8)
        self.t_refis.pack(fill="both", expand=True, pady=4)

        self.g_proyeccion = self.bloque(lambda m: Grafica(m, alto=3.4))
        self.g_historial = self.bloque(lambda m: Grafica(m, alto=3.4))

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
                f"{porcentaje(d['uso_cupo'], 0)} · {formato(d['disponible'])}" if d["uso_cupo"] is not None else "—",
                d["fecha_limite"].isoformat() if d["fecha_limite"] else "—", pesos(d["minimo"]), pesos(d["total"]),
                f"+{formato(d['interes_si_minimo'])} de intereses" if d["interes_si_minimo"] else "—",
                "Extracto" if d["fuente"] == "extracto" else "Cronograma"]))
        self.t_productos.cargar(filas)

        self._creditos = {c["credito"]["id"]: c for c in repo.creditos()}
        self.t_creditos.cargar([(cid, [
            c["credito"]["producto"], c["credito"]["descripcion"], ORIGENES[c["credito"]["origen"]],
            c["credito"]["fecha"], pesos(c["credito"]["monto"]),
            f"{c['cuotas_restantes']} de {c['credito']['num_cuotas']}", pesos(c["saldo"]),
            f"{c['proxima']['fecha']} · {formato(repo._pendiente(c['proxima']))}"
            if c["proxima"] else "—"]) for cid, c in self._creditos.items()])
        self.t_mora.cargar([(m["cuota"]["id"], [
            m["producto"], m["descripcion"], m["cuota"]["numero"], m["cuota"]["fecha"], m["dias"], pesos(m["capital"]),
            pesos(m["pendiente"]), pesos(m["mora_liquidada"]), pesos(m["cobranza_liquidada"]),
            pesos(m["por_liquidar"])]) for m in repo.estado_mora(hoy)])

        self.t_pagos.cargar([(p["id"], [p["fecha"], p["producto"], TIPOS_PAGO.get(p["tipo"], p["tipo"]),
                                        pesos(p["monto"]), pesos(p["a_capital"]), pesos(p["a_costos"]),
                                        pesos(p["abono_extra"]), "Sí" if p["desde_reserva"] else "", p["canal"]])
                             for p in repo.pagos()])
        self.t_extractos.cargar([(e["id"], [e["producto"], e["fecha_corte"], e["fecha_limite"], pesos(e["capital_mes"]),
                                            pesos(e["intereses"]), formato(e["pago_minimo"], decimales=True),
                                            formato(e["deuda_restante"], decimales=True),
                                            formato(e["pago_total"], decimales=True)]) for e in repo.extractos()])
        self.t_refis.cargar([(r["id"], [r["fecha"], r["producto"], pesos(r["deuda_total"]), pesos(r["valor_pagado"]),
                                        pesos(r["saldo"]), r["num_cuotas"], pesos(r["cuota"]),
                                        f"{tasa(r['tasa_ea'])} %" if r["tasa_ea"] is not None else "—",
                                        f"{tasa(r['ea_implicita'])} %" if r["ea_implicita"] is not None else "—"])
                             for r in repo.refinanciaciones()])

        self.g_proyeccion.proyeccion(repo.proyeccion_pagos(12, hoy), repo.ingreso_mensual_estimado(hoy))
        self.g_historial.historial(repo.historial(12, hoy))

    def _producto_seleccionado(self, obligatorio: bool = True):
        id_ = self.t_productos.seleccionado()
        if id_ is None and len(self._deudas) == 1:
            id_ = next(iter(self._deudas))
        if id_ is None:
            if obligatorio:
                error(self, "Selecciona una tarjeta o crédito en la tabla de arriba." if self._deudas else
                      "Primero registra una tarjeta o crédito con «+ Tarjeta / crédito».")
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
            tarjeta = v["tipo"] == "tarjeta"
            self.repo.guardar_producto(p["id"] if p else None, v["nombre"], v["entidad"] or "", v["tipo"],
                                       v["cupo"] or 0, v["tasa"], v["corte"] if tarjeta else 1, v["pago"] or 1,
                                       v["manejo"] or 0 if tarjeta else 0, bool(v["una_cuota"]))
            self.refrescar()

        Formulario(self, "Editar tarjeta / crédito" if p else "Nueva tarjeta / crédito", campos, guardar)

    def _editar_producto(self) -> None:
        p = self._producto_seleccionado()
        if p:
            self._dialogo_producto(p)

    # ------------------------------------------------------------ pagos

    def _pago(self) -> None:
        p = self._producto_seleccionado()
        if not p:
            return
        d = self._deudas[p["id"]]
        ayuda = (f"Mínimo: {formato(d['minimo'])}   ·   Total: {formato(d['total'])}"
                 + (f"   ·   Vence: {d['fecha_limite'].isoformat()}" if d["fecha_limite"] else "")
                 + (" (según el extracto)" if d["fuente"] == "extracto" else ""))
        reserva = self.repo.saldo_reserva()
        campos = [
            Campo("fecha", "Fecha del pago", "fecha", defecto=hoy_texto()),
            Campo("monto", "Valor pagado", "monto", defecto=formato(d["minimo"], signo=False) if d["minimo"] else None,
                  ayuda=ayuda),
            Campo("reserva", "Lo pagué con la plata de la reserva (Cajita)", "check",
                  defecto=bool(d["minimo"]) and reserva >= d["minimo"],
                  ayuda=f"Saldo de la reserva: {formato(max(0, reserva))}."),
            Campo("reducir", "Si pagas más del mínimo, lo que sobra…", "opcion",
                  [("Abona a capital y reduce el plazo (ahorras más intereses)", "plazo"),
                   ("Abona a capital y reduce la cuota", "cuota"),
                   ("Anticipa las cuotas siguientes completas", "anticipar")]),
            Campo("canal", "Canal de pago", "opcion", [(c or "Sin especificar", c) for c in CANALES]),
            Campo("notas", "Notas", opcional=True),
        ]
        if d.get("mora_estimada"):
            campos[1].ayuda += f"\nIncluye {formato(d['mora_estimada'])} de mora y cobranza a hoy."

        def guardar(v: dict) -> None:
            if self.repo.pago_posible_duplicado(p["id"], v["fecha"], v["monto"]) and not confirmar(
                    self, "Ya hay un pago por ese mismo valor y fecha en esta tarjeta. ¿Es otro pago distinto?"):
                return
            r = self.repo.registrar_pago(p["id"], v["fecha"], v["monto"], v["reserva"], v["reducir"],
                                         v["notas"] or "", v["canal"] or "")
            self.app.datos_cambiaron()
            texto = (f"Pago registrado como: {TIPOS_PAGO[r['tipo']]}\n\n"
                     f"A intereses y cargos: {formato(r['a_costos'])}\n"
                     f"A capital: {formato(r['a_capital'])}")
            nombres = {"cobranza": "Gastos de cobranza", "mora": "Intereses de mora", "otros": "Cargos",
                       "interes": "Intereses", "capital": "Capital de cuotas"}
            for comp, valor in r["por_componente"].items():
                texto += f"\n   · {nombres[comp]}: {formato(valor)}"
            if r["mora_liquidada"]:
                texto += f"\nSe liquidaron {formato(r['mora_liquidada'])} de mora y cobranza hasta la fecha del pago."
            if r["abono_extra"]:
                texto += f"\n(incluye abono extra a capital de {formato(r['abono_extra'])})"
            if r["anticipado"]:
                texto += f"\nCuotas anticipadas: {formato(r['anticipado'])}"
            if r["penalidad"]:
                texto += f"\nPenalidad por prepago según tus condiciones: {formato(r['penalidad'])}"
            if r["manejo"]:
                texto += f"\nCuota de manejo / comisiones del ciclo: {formato(r['manejo'])}"
            if r["segun_extracto"]:
                texto += "\n(Clasificado con el mínimo y el total del extracto vigente.)"
            if r["sin_aplicar"]:
                texto += (f"\n\nQuedaron {formato(r['sin_aplicar'])} como saldo a favor: se usarán en la próxima "
                          "deuda que registres en esta tarjeta o cupo.")
            if r["tipo"] == "menor_al_minimo":
                texto += "\n\n⚠ El pago es menor al mínimo: puede generar intereses de mora y reporte."
            self.after(200, lambda: messagebox.showinfo("Pago registrado", texto, parent=self))

        Formulario(self, f"Pago a {p['nombre']}", campos, guardar, texto_boton="Registrar pago")

    def _eliminar_pago(self) -> None:
        id_ = self.t_pagos.seleccionado()
        if id_ is None:
            return error(self, "Selecciona un pago.")
        if confirmar(self, "¿Eliminar este pago? Se deshace su efecto en las cuotas y en la reserva."):
            try:
                self.repo.eliminar_pago(id_)
            except ValueError as e:
                return error(self, str(e))
            self.refrescar()

    # ------------------------------------------------------------ extractos

    def _extracto(self) -> None:
        p = self._producto_seleccionado()
        if not p:
            return
        if p["tipo"] != "tarjeta":
            return error(self, "Los extractos aplican a tarjetas de crédito.")
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
            Campo("restante", "Deuda restante", "monto", defecto="0",
                  ayuda="Copia los valores del resumen de tu extracto. La app calcula el pago mínimo y el total "
                        "para que los compares."),
        ]

        def guardar(v: dict) -> None:
            self.repo.registrar_extracto(p["id"], v["corte"], v["limite"], v["capital"], v["intereses"], v["avances"],
                                         v["servicio"], v["conversion"], v["abonos"], v["devoluciones"], v["restante"])
            ext = self.repo.ultimo_extracto(p["id"])
            self.app.datos_cambiaron()
            self.after(200, lambda: messagebox.showinfo(
                "Extracto registrado",
                f"Pago mínimo calculado: {formato(ext['pago_minimo'], decimales=True)}\n"
                f"Pago total calculado: {formato(ext['pago_total'], decimales=True)}\n\n"
                "Compáralos con tu extracto. Si no coinciden, revisa los valores ingresados.\n"
                "Hasta la fecha límite, el plan usa este mínimo en lugar del cronograma.", parent=self))

        Formulario(self, f"Extracto de {p['nombre']}", campos, guardar, ancho=480)

    def _eliminar_extracto(self) -> None:
        id_ = self.t_extractos.seleccionado()
        if id_ is None:
            return error(self, "Selecciona un extracto.")
        if confirmar(self, "¿Eliminar este extracto?"):
            self.repo.eliminar_extracto(id_)
            self.refrescar()

    # ------------------------------------------------------------ deudas existentes

    def _deuda_existente(self) -> None:
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
                  defecto=proxima.isoformat() if proxima else None,
                  ayuda=AYUDA_FECHA.get(p["tipo"], "")),
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
            self.app.datos_cambiaron()
            cuotas = self.repo.cronograma_credito(cid)
            cond = self.repo.condiciones_credito(cid)
            primera, ultima = cuotas[0], cuotas[-1]
            texto = (f"Saldo pendiente: {formato(sum(c['capital'] for c in cuotas))}\n"
                     f"Cuotas que faltan: {len(cuotas)} (de la {primera['numero']} a la {ultima['numero']})\n"
                     f"Próxima cuota: {primera['fecha']} · "
                     f"{formato(primera['capital'] + primera['interes'] + primera['otros'])}\n"
                     f"Última cuota: {ultima['fecha']}\n\n"
                     "Compáralo con la app del banco. Si algo no coincide, elimínala y regístrala de nuevo "
                     "(ej. con el saldo o el valor de la cuota que muestra la app).")
            segun_cuota = cond.get("tasa_segun_cuota_ea")
            if segun_cuota is not None and abs(segun_cuota - v["tasa"]) > 0.5:
                texto += (f"\n\n⚠ El valor de la cuota equivale a {tasa(segun_cuota)} % E.A., distinto del "
                          f"{tasa(v['tasa'])} % E.A. que escribiste. El cronograma usa la tasa de la cuota. Puede "
                          "incluir seguros u otros cargos (regístralos aparte) o el saldo es distinto.")
            self.after(200, lambda: messagebox.showinfo("Cuotas registradas", texto, parent=self))

        Formulario(self, f"Cuotas que ya tenía en {p['nombre']}", campos, guardar, ancho=560)

    def _eliminar_credito(self) -> None:
        id_ = self.t_creditos.seleccionado()
        if id_ is None:
            return error(self, "Selecciona una deuda.")
        if confirmar(self, "¿Eliminar esta deuda y su cronograma?"):
            try:
                self.repo.eliminar_credito(id_)
            except ValueError as e:
                return error(self, str(e))
            self.refrescar()

    def _ver_cronograma(self) -> None:
        id_ = self.t_creditos.seleccionado()
        if id_ is None:
            return error(self, "Selecciona una deuda.")
        c = self._creditos[id_]["credito"]
        VentanaCronograma(self, f"{c['producto']} · {c['descripcion'] or ORIGENES[c['origen']]}", id_)

    def _devolucion(self) -> None:
        id_ = self.t_creditos.seleccionado()
        if id_ is None:
            return error(self, "Selecciona la deuda de la compra que devolviste.")
        c = self._creditos[id_]
        campos = [Campo("fecha", "Fecha de la devolución", "fecha", defecto=hoy_texto()),
                  Campo("monto", "Valor devuelto", "monto", defecto=formato(c["saldo"], signo=False),
                        ayuda=f"Saldo de esta deuda: {formato(c['saldo'])}. No es plata que sale de tu bolsillo."),
                  Campo("reducir", "La devolución…", "opcion",
                        [("Reduce el valor de las cuotas", "cuota"), ("Reduce el número de cuotas", "plazo")])]

        def guardar(v: dict) -> None:
            res = self.repo.registrar_devolucion(id_, v["fecha"], v["monto"], v["reducir"])
            self.app.datos_cambiaron()
            texto = f"Se redujo la deuda en {formato(res['a_capital'])}."
            if res["saldo_a_favor"]:
                texto += f"\nQuedan {formato(res['saldo_a_favor'])} a tu favor: reclámalos al almacén o entidad."
            self.after(200, lambda: messagebox.showinfo("Devolución registrada", texto, parent=self))

        Formulario(self, "Devolución de compra", campos, guardar)

    def _liquidar_mora(self) -> None:
        total = self.repo.liquidar_mora(date.today())
        self.app.datos_cambiaron()
        messagebox.showinfo("Mora", f"Se liquidaron {formato(total)} de mora y cobranza hasta hoy.", parent=self)

    def _condiciones(self) -> None:
        p = self._producto_seleccionado()
        if not p:
            return
        base = self.repo.condiciones_producto(p["id"])

        def guardar(v: dict) -> None:
            self.repo.guardar_condiciones_producto(p["id"], leer_condiciones(v, base))
            self.refrescar()

        Formulario(self, f"Condiciones de {p['nombre']}", campos_condiciones(base), guardar, ancho=600,
                   texto_boton="Guardar condiciones")

    # ------------------------------------------------------------ organizar deuda

    def _organizar(self) -> None:
        p = self._producto_seleccionado()
        if p:
            VentanaOrganizar(self, p)

    def _eliminar_refi(self) -> None:
        id_ = self.t_refis.seleccionado()
        if id_ is None:
            return error(self, "Selecciona una deuda organizada.")
        if confirmar(self, "¿Deshacer esta refinanciación? Las deudas anteriores vuelven a quedar activas."):
            try:
                self.repo.eliminar_refinanciacion(id_)
            except ValueError as e:
                return error(self, str(e))
            self.app.datos_cambiaron()


class VentanaCronograma(ctk.CTkToplevel):
    """Tabla de amortización con cargos, mora y costo total de la financiación."""

    def __init__(self, pagina, titulo: str, credito_id: int):
        super().__init__(pagina)
        repo = pagina.repo
        self.title("Cronograma y costo")
        tamano_ventana(self, 1180, 640, min_ancho=700, min_alto=420)
        self.transient(pagina.winfo_toplevel())
        cond = repo.condiciones_credito(credito_id)
        costo = repo.costo_credito(credito_id)
        cuotas = repo.cronograma_credito(credito_id)
        ctk.CTkLabel(self, text=titulo, font=FUENTE_SUBTITULO).pack(anchor="w", padx=16, pady=(14, 0))
        acreedor = cond["acreedor"]
        partes = [f"Tasa pactada: {tasa(float(cond['tasa']['valor']))} % {cond['tasa']['modalidad']} "
                  f"({tasa(costo.tasa_ea_contractual)} % E.A.)", f"Sistema: {dict((v, k) for k, v in SISTEMAS)[cond['sistema']]}",
                  f"Periodicidad: {cond['periodicidad']}"]
        if acreedor.get("nombre"):
            partes.append(f"Acreedor: {acreedor['nombre']}" + (f" (financia {acreedor['financiador']})"
                                                               if acreedor.get("financiador") else ""))
        ctk.CTkLabel(self, text="   ·   ".join(partes), text_color=GRIS).pack(anchor="w", padx=16)

        tabla = Tabla(self, [("#", 40, "centro"), ("Fecha", 90, "centro"), ("Saldo inicial", 110, "der"),
                             ("Intereses", 100, "der"), ("Abono a capital", 110, "der"), ("Cargos", 100, "der"),
                             ("Mora y cobranza", 110, "der"), ("Cuota", 110, "der"), ("Saldo final", 110, "der"),
                             ("Pagado", 100, "der"), ("Estado", 90, "centro")], alto=12)
        tabla.pack(fill="both", expand=True, padx=16, pady=8)
        saldo = sum(c["capital"] for c in cuotas if c["estado"] != "refinanciada")
        filas = []
        for c in cuotas:
            detalle = cond_mod.cargar(c["detalle"], {}) if c["detalle"] else {}
            cargos = pesos(c["otros"]) + (f" ({', '.join(detalle)})" if detalle else "")
            filas.append((c["id"], [c["numero"], c["fecha"], pesos(saldo), pesos(c["interes"]), pesos(c["capital"]),
                                    cargos, pesos(c["mora"] + c["cobranza"]),
                                    pesos(c["capital"] + c["interes"] + c["otros"] + c["mora"] + c["cobranza"]),
                                    pesos(saldo - c["capital"]), pesos(c["pagado"]), c["estado"].capitalize()]))
            if c["estado"] != "refinanciada":
                saldo -= c["capital"]
        tabla.cargar(filas)

        resumen = ctk.CTkFrame(self, fg_color=FONDO_TARJETA, corner_radius=12)
        resumen.pack(fill="x", padx=16, pady=(0, 14))
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
        for i, (k, v) in enumerate(datos):
            ctk.CTkLabel(resumen, text=k, anchor="w").grid(row=i // 3, column=(i % 3) * 2, sticky="w", padx=(14, 6),
                                                           pady=2)
            ctk.CTkLabel(resumen, text=v, font=("Segoe UI", 13, "bold"), anchor="e"
                         ).grid(row=i // 3, column=(i % 3) * 2 + 1, sticky="e", padx=(0, 24), pady=2)
        nota = ("La tasa efectiva real incluye intereses y cargos según las fechas de cada pago; no reemplaza la tasa "
                "contractual. ")
        if cuotas and cuotas[0]["numero"] > 1:
            nota += "Esta deuda se registró a mitad de camino: el costo solo cuenta las cuotas registradas."
        ctk.CTkLabel(resumen, text=nota, text_color=GRIS, font=FUENTE_PEQUENA, wraplength=1100, justify="left"
                     ).grid(row=4, column=0, columnspan=6, sticky="w", padx=14, pady=(4, 10))
        self.after(100, self.lift)


class VentanaComparar(ctk.CTkToplevel):
    """Compara una misma compra con distintas ofertas reales de financiación."""

    CAMPOS = [("nombre", "Alternativa", "texto"), ("inicial", "Cuota inicial ($)", "monto"),
              ("financiado", "Precio financiado ($, si es distinto)", "monto"), ("cuotas", "Número de cuotas", "entero"),
              ("tasa", "Tasa (%)", "tasa"), ("modalidad", "Modalidad de la tasa", MODALIDADES),
              ("periodicidad", "Periodicidad", PERIODICIDADES), ("sistema", "Sistema", SISTEMAS),
              ("fianza", "Fianza / aval (% capital)", "tasa"), ("iva", "IVA fianza / aval (%)", "tasa"),
              ("cobro", "Cobro de la fianza / aval", COBROS), ("seguro", "Seguro por cuota ($)", "monto"),
              ("otros_cuota", "Otros cargos por cuota ($)", "monto"), ("otros_inicial", "Otros cargos iniciales ($)", "monto")]
    DEFECTOS = [{"nombre": "Contado", "cuotas": "1"}, {"nombre": "Addi", "cuotas": "3"},
                {"nombre": "Sistecrédito", "cuotas": "6"}, {"nombre": "Crédito del almacén", "cuotas": "12"}]

    def __init__(self, pagina):
        super().__init__(pagina)
        self.title("Comparar financiación")
        tamano_ventana(self, 1180, 760, min_ancho=700, min_alto=420)
        self.transient(pagina.winfo_toplevel())
        arriba = ctk.CTkFrame(self, fg_color="transparent")
        arriba.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(arriba, text="Precio de contado del producto ($)").pack(side="left")
        self.precio = ctk.CTkEntry(arriba, width=160)
        self.precio.pack(side="left", padx=8)
        ctk.CTkButton(arriba, text="Comparar", command=self._comparar).pack(side="left")
        ctk.CTkLabel(arriba, text="Usa las condiciones reales de cada oferta. La columna «Contado» se paga toda como "
                                  "cuota inicial.", text_color=GRIS).pack(side="left", padx=10)
        rejilla = ctk.CTkScrollableFrame(self, height=380)
        rejilla.pack(fill="x", padx=16)
        self.entradas: list[dict] = [{} for _ in self.DEFECTOS]
        for fila, (clave, etiqueta, tipo) in enumerate(self.CAMPOS):
            ctk.CTkLabel(rejilla, text=etiqueta, anchor="w").grid(row=fila, column=0, sticky="w", padx=4, pady=2)
            for col, defecto in enumerate(self.DEFECTOS):
                if isinstance(tipo, list):
                    w = ctk.CTkComboBox(rejilla, values=[e for e, _ in tipo], state="readonly", width=190)
                    w.set(tipo[0][0])
                else:
                    w = ctk.CTkEntry(rejilla, width=190)
                    if defecto.get(clave):
                        w.insert(0, defecto[clave])
                w.grid(row=fila, column=col + 1, padx=4, pady=2)
                self.entradas[col][clave] = (w, tipo)
        self.mensaje = ctk.CTkLabel(self, text="", text_color=ROJO)
        self.mensaje.pack(fill="x", padx=16)
        self.tabla = Tabla(self, [("Concepto", 230, "izq")] + [(d["nombre"], 200, "der") for d in self.DEFECTOS],
                           alto=12)
        self.tabla.pack(fill="both", expand=True, padx=16, pady=(4, 14))
        self.after(100, self.lift)

    def _oferta(self, col: int, precio: int) -> Oferta | None:
        v = {}
        for clave, (w, tipo) in self.entradas[col].items():
            texto = w.get().strip()
            if isinstance(tipo, list):
                v[clave] = dict(tipo)[texto]
            elif not texto:
                v[clave] = None
            elif tipo == "monto":
                v[clave] = a_centavos(texto)
            elif tipo == "tasa":
                v[clave] = a_tasa(texto)
            elif tipo == "entero":
                v[clave] = int(texto)
            else:
                v[clave] = texto
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

    def _comparar(self) -> None:
        self.mensaje.configure(text="")
        try:
            precio = a_centavos(self.precio.get())
            if precio <= 0:
                raise ValueError("Indica el precio de contado")
            ofertas = [o for o in (self._oferta(i, precio) for i in range(len(self.DEFECTOS))) if o]
            resultados = comparar_ofertas(ofertas)
        except ValueError as e:
            self.mensaje.configure(text=str(e))
            return
        self.tabla.arbol.configure(columns=[f"c{i}" for i in range(len(resultados) + 1)])
        self.tabla.arbol.heading("c0", text="Concepto")
        self.tabla.arbol.column("c0", width=230, anchor="w")
        for i, (o, _, _) in enumerate(resultados, start=1):
            self.tabla.arbol.heading(f"c{i}", text=o.nombre)
            self.tabla.arbol.column(f"c{i}", width=200, anchor="e")
        filas = [
            ("Cuota inicial", lambda o, cr, c: formato(c.cuota_inicial)),
            ("Número de cuotas", lambda o, cr, c: str(c.num_cuotas)),
            ("Valor de la cuota", lambda o, cr, c: formato(cr[0].total) if cr else "—"),
            ("Intereses", lambda o, cr, c: formato(c.intereses)),
            ("Fianza / aval, seguros y otros cargos", lambda o, cr, c: formato(c.total_cargos)),
            ("Total pagado", lambda o, cr, c: formato(c.total_pagado)),
            ("Diferencia vs. contado", lambda o, cr, c: formato(c.diferencia)),
            ("Incremento del costo", lambda o, cr, c: f"{tasa(c.incremento_pct, 1)} %"),
            ("Costo comercial (sobreprecio)", lambda o, cr, c: formato(c.costo_comercial)),
            ("Tasa contractual", lambda o, cr, c: f"{tasa(c.tasa_ea_contractual)} % E.A."),
            ("Costo efectivo (tasa real por flujos)", lambda o, cr, c: f"{tasa(c.tasa_ea_efectiva)} % E.A."
             if c.tasa_ea_efectiva is not None else "—"),
        ]
        self.tabla.cargar([(k, [k] + [f(o, cr, c) for o, cr, c in resultados]) for k, f in filas])


class VentanaOrganizar(ctk.CTkToplevel):
    """Registrar o simular la refinanciación ("organizar deuda") de una tarjeta."""

    def __init__(self, pagina: PaginaDeudas, producto):
        super().__init__(pagina)
        self.pagina = pagina
        self.repo = pagina.repo
        self.producto = producto
        self.resultado = None
        self.title(f"Organizar deuda · {producto['nombre']}")
        tamano_ventana(self, 1080, 720, min_ancho=760, min_alto=420)
        self.transient(pagina.winfo_toplevel())
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        izq = ctk.CTkScrollableFrame(self, width=340)
        izq.grid(row=0, column=0, sticky="nsw", padx=(14, 6), pady=14)
        ctk.CTkLabel(izq, text="Datos de la app del banco", font=FUENTE_SUBTITULO, anchor="w").pack(fill="x")
        ctk.CTkLabel(izq, text="Registra la refinanciación que hiciste o simula una antes de aceptarla. "
                               "Basta con el valor de la cuota o la tasa; con ambos la app verifica que coincidan.",
                     text_color=GRIS, wraplength=320, justify="left", anchor="w").pack(fill="x", pady=(0, 8))
        hoy = date.today()
        self.entradas: dict[str, ctk.CTkEntry] = {}
        for clave, etiqueta, defecto, ayuda in [
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
            ctk.CTkLabel(izq, text=etiqueta, anchor="w").pack(fill="x", pady=(6, 0))
            e = ctk.CTkEntry(izq)
            e.insert(0, defecto)
            e.pack(fill="x")
            if ayuda:
                ctk.CTkLabel(izq, text=ayuda, text_color=GRIS, font=FUENTE_PEQUENA, anchor="w", justify="left",
                             wraplength=320).pack(fill="x")
            self.entradas[clave] = e
        self._deudas_opciones = {"Todas las deudas de esta tarjeta / cupo": None}
        for c in self.repo.creditos(producto["id"]):
            cr = c["credito"]
            etiqueta = f"{cr['descripcion'] or ORIGENES[cr['origen']]} · {cr['fecha']} · saldo {formato(c['saldo'])}"
            self._deudas_opciones[etiqueta] = [cr["id"]]
        ctk.CTkLabel(izq, text="Deudas que se organizan", anchor="w").pack(fill="x", pady=(6, 0))
        self.deudas = ctk.CTkComboBox(izq, values=list(self._deudas_opciones), state="readonly",
                                      command=self._cambiar_deudas)
        self.deudas.set(next(iter(self._deudas_opciones)))
        self.deudas.pack(fill="x")
        ctk.CTkLabel(izq, text="Elige una compra si solo refinanciaste esa (ej. una compra de Addi).", text_color=GRIS,
                     font=FUENTE_PEQUENA, anchor="w", justify="left", wraplength=320).pack(fill="x")
        self.acuerdo = ctk.CTkCheckBox(izq, text="Es un acuerdo de pago (por mora)")
        self.acuerdo.pack(anchor="w", pady=(8, 0))
        self.mensaje = ctk.CTkLabel(izq, text="", text_color=ROJO, wraplength=320, justify="left")
        self.mensaje.pack(fill="x", pady=6)
        ctk.CTkButton(izq, text="Calcular", command=self._calcular).pack(fill="x", pady=(4, 4))
        self.boton_registrar = ctk.CTkButton(izq, text="Registrar refinanciación", fg_color=MORADO,
                                             state="disabled", command=self._registrar)
        self.boton_registrar.pack(fill="x")

        der = ctk.CTkFrame(self, fg_color="transparent")
        der.grid(row=0, column=1, sticky="nsew", padx=(6, 14), pady=14)
        self.resumen = ctk.CTkFrame(der, fg_color=FONDO_TARJETA, corner_radius=12)
        self.resumen.pack(fill="x")
        ctk.CTkLabel(self.resumen, text="Completa los datos y presiona «Calcular».", text_color=GRIS
                     ).pack(padx=14, pady=14)
        self.tabla = Tabla(der, [("#", 40, "centro"), ("Fecha", 100, "centro"), ("Capital", 120, "der"),
                                 ("Intereses", 110, "der"), ("Cuota", 120, "der")], alto=10)
        self.tabla.pack(fill="both", expand=True, pady=(8, 0))
        self.after(100, self.lift)

    def _ids(self) -> list[int] | None:
        return self._deudas_opciones.get(self.deudas.get())

    def _cambiar_deudas(self, _valor=None) -> None:
        deuda = self.repo.deuda_para_refinanciar(self.producto["id"], date.today(), self._ids())
        self.entradas["deuda"].delete(0, "end")
        self.entradas["deuda"].insert(0, formato(deuda, signo=False))
        self.resultado = None
        self.boton_registrar.configure(state="disabled")

    def _leer(self) -> dict:
        e = {k: w.get().strip() for k, w in self.entradas.items()}
        if not e["cuotas"]:
            raise ValueError("Indica el número de cuotas.")
        if not e["cuota"] and not e["tasa"]:
            raise ValueError("Indica el valor de la cuota o la tasa E.A.")
        return {
            "fecha": parsear_fecha(e["fecha"]),
            "deuda": a_centavos(e["deuda"]),
            "pagado": a_centavos(e["pagado"] or "0"),
            "cuotas": int(e["cuotas"]),
            "cuota": a_centavos(e["cuota"]) if e["cuota"] else None,
            "tasa": a_tasa(e["tasa"]) if e["tasa"] else None,
            "saldo": a_centavos(e["saldo"]) if e["saldo"] else None,
            "primera": parsear_fecha(e["primera"]),
        }

    def _calcular(self) -> None:
        self.mensaje.configure(text="")
        try:
            v = self._leer()
            r = self.repo.simular_refinanciacion(self.producto["id"], v["fecha"], v["deuda"], v["pagado"], v["cuotas"],
                                                 v["cuota"], v["tasa"], v["saldo"], v["primera"])
        except ValueError as e:
            self.mensaje.configure(text=str(e))
            self.boton_registrar.configure(state="disabled")
            return
        self.resultado = (v["fecha"], r)
        self.boton_registrar.configure(state="normal")
        self._mostrar(r)

    def _mostrar(self, r) -> None:
        for w in self.resumen.winfo_children():
            w.destroy()
        actual = self.repo.situacion_actual(self.producto["id"], self._ids())
        ctk.CTkLabel(self.resumen, text="Resultado", font=FUENTE_SUBTITULO, anchor="w").pack(fill="x", padx=14,
                                                                                           pady=(12, 4))
        lineas = [
            ("Saldo refinanciado", formato(r.saldo)),
            ("Cuota mensual", formato(r.cuota)),
            ("Tasa según la cuota", f"{tasa(r.ea_implicita)} % E.A." if r.ea_implicita is not None
             else f"{tasa(r.tasa_ea_declarada)} % E.A. (declarada)"),
            ("Intereses de las cuotas", formato(r.intereses_cuotas)),
            ("Total a pagar (valor pagado + cuotas)", formato(r.total_pagar)),
            ("Costo de organizar la deuda", formato(r.costo_total)),
            ("Última cuota", r.ultima_fecha.isoformat() if r.ultima_fecha else "—"),
        ]
        rejilla = ctk.CTkFrame(self.resumen, fg_color="transparent")
        rejilla.pack(fill="x", padx=14)
        for i, (k, val) in enumerate(lineas):
            ctk.CTkLabel(rejilla, text=k, anchor="w").grid(row=i, column=0, sticky="w", pady=1)
            ctk.CTkLabel(rejilla, text=val, anchor="e", font=("Segoe UI", 13, "bold")).grid(row=i, column=1,
                                                                                           sticky="e", padx=(30, 0))
        for adv in r.advertencias:
            ctk.CTkLabel(self.resumen, text="⚠ " + adv, text_color=NARANJA, wraplength=620, justify="left",
                         anchor="w").pack(fill="x", padx=14, pady=(6, 0))

        if actual["total"]:
            ctk.CTkLabel(self.resumen, text="Comparación con seguir como estás", font=FUENTE_SUBTITULO,
                         anchor="w").pack(fill="x", padx=14, pady=(12, 2))
            comp = ctk.CTkFrame(self.resumen, fg_color="transparent")
            comp.pack(fill="x", padx=14)
            for j, t in enumerate(("", "Como estoy", "Organizada")):
                ctk.CTkLabel(comp, text=t, font=("Segoe UI", 12, "bold")).grid(row=0, column=j, sticky="e", padx=10)
            filas = [("Próximo pago", formato(actual["proximo_pago"]), formato(r.cuota)),
                     ("Meses que faltan", str(actual["meses"]), str(r.n)),
                     ("Intereses y cargos que faltan", formato(actual["costos"]), formato(r.costo_total))]
            for i, (k, a, b) in enumerate(filas, start=1):
                ctk.CTkLabel(comp, text=k, anchor="w").grid(row=i, column=0, sticky="w", padx=10)
                ctk.CTkLabel(comp, text=a).grid(row=i, column=1, sticky="e", padx=10)
                ctk.CTkLabel(comp, text=b).grid(row=i, column=2, sticky="e", padx=10)
            diferencia_pago = actual["proximo_pago"] - r.cuota
            diferencia_costo = r.costo_total - actual["costos"]
            veredicto = (f"Tu pago {'baja' if diferencia_pago >= 0 else 'sube'} {formato(abs(diferencia_pago))} "
                         f"al mes, pero pagas {formato(abs(diferencia_costo))} "
                         f"{'más' if diferencia_costo >= 0 else 'menos'} en intereses y cargos.")
            ctk.CTkLabel(self.resumen, text=veredicto, font=("Segoe UI", 13, "bold"),
                         text_color=NARANJA if diferencia_costo > 0 else VERDE, wraplength=620, justify="left",
                         anchor="w").pack(fill="x", padx=14, pady=(8, 0))
            ctk.CTkLabel(self.resumen, text="«Como estoy» usa las compras y deudas registradas en la app para esta "
                                            "tarjeta; si no las registraste todas, la comparación es parcial.",
                         text_color=GRIS, font=FUENTE_PEQUENA, wraplength=620, justify="left", anchor="w"
                         ).pack(fill="x", padx=14)
        ctk.CTkFrame(self.resumen, height=10, fg_color="transparent").pack()
        self.tabla.cargar([(c.numero, [c.numero, c.fecha.isoformat(), pesos(c.capital), pesos(c.interes),
                                       pesos(c.total)]) for c in r.cronograma])

    def _registrar(self) -> None:
        if not self.resultado:
            return
        fecha, r = self.resultado
        alcance = ("Las compras y deudas activas de esta tarjeta" if self._ids() is None
                   else "La deuda elegida")
        if not confirmar(self, f"{alcance} quedarán reemplazadas por la deuda organizada. ¿Registrar?"):
            return
        try:
            self.repo.registrar_refinanciacion(self.producto["id"], fecha, r,
                                               "acuerdo_pago" if self.acuerdo.get() else "refinanciacion",
                                               credito_ids=self._ids())
        except ValueError as e:
            self.mensaje.configure(text=str(e))
            return
        self.pagina.app.datos_cambiaron()
        self.destroy()

