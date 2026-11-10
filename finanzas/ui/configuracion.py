"""Configuración: fuentes de ingreso, categorías, parámetros del plan y datos."""

import os
from pathlib import Path
from datetime import date
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .. import db
from ..dinero import a_tasa, formato
from ..exportar import exportar_excel
from ..fechas import parsear_dias_pago
from ..plan import NIVELES, NOMBRE_NIVEL
from .app import Pagina
from .widgets import (FONDO_TARJETA, GRIS, Campo, Formulario, Tabla, aplicar_estilo_tablas, confirmar, error,
                      pesos)

ESTADOS = {"activa": "Activa", "esperada": "Esperada (aún no confirmada)", "inactiva": "Inactiva"}


class PaginaConfiguracion(Pagina):
    titulo = "Configuración"

    def construir(self) -> None:
        self.tabs = ctk.CTkTabview(self, height=620)
        self.tabs.pack(fill="both", expand=True, padx=24, pady=4)
        for nombre in ("Ingresos", "Parámetros del plan", "Tasas legales", "Categorías", "Datos"):
            self.tabs.add(nombre)
        self._tab_ingresos(self.tabs.tab("Ingresos"))
        self._tab_parametros(self.tabs.tab("Parámetros del plan"))
        self._tab_categorias(self.tabs.tab("Categorías"))
        self._tab_datos(self.tabs.tab("Datos"))
        self._tab_tasas(self.tabs.tab("Tasas legales"))

    def refrescar(self) -> None:
        self.t_tasas.cargar([(t["id"], [t["modalidad"], t["desde"], t["hasta"],
                                        f"{t['ibc_ea']:.2f} %".replace(".", ",") if t["ibc_ea"] else "—",
                                        f"{t['usura_ea']:.2f} %".replace(".", ","), t["notas"]])
                             for t in self.repo.tasas_legales()])
        self._fuentes = {f["id"]: f for f in self.repo.fuentes()}
        self.t_fuentes.cargar([(f["id"], [f["nombre"], pesos(f["monto_mensual"]), f["dias_pago"],
                                          "Variable" if f["variable"] else "Fijo", ESTADOS[f["estado"]]])
                               for f in self._fuentes.values()])
        self._categorias = {c["id"]: c for c in self.repo.categorias(False)}
        self.t_categorias.cargar([(c["id"], [c["nombre"], "Necesidad" if c["grupo"] == "necesidad" else "Deseo",
                                             "Sí" if c["activa"] else "No"]) for c in self._categorias.values()])
        self._cargar_parametros()

    # ------------------------------------------------------------ ingresos

    def _tab_ingresos(self, t) -> None:
        ctk.CTkLabel(t, text="Tus fuentes de ingreso definen el ingreso mensual estimado (para el % de endeudamiento) "
                             "y los días en que cobras (para saber qué vence antes del próximo ingreso). "
                             "Un ingreso «esperado» (ej. un freelance sin confirmar) no entra al plan, salvo que lo "
                             "pidas en la simulación.", text_color=GRIS, wraplength=950, justify="left",
                     anchor="w").pack(fill="x")
        b = ctk.CTkFrame(t, fg_color="transparent")
        b.pack(fill="x", pady=6)
        ctk.CTkButton(b, text="+ Fuente de ingreso", command=lambda: self._dialogo_fuente(None)).pack(side="left")
        ctk.CTkButton(b, text="Editar", command=self._editar_fuente).pack(side="left", padx=6)
        ctk.CTkButton(b, text="Eliminar", fg_color="transparent", border_width=1, text_color=("gray10", "gray90"),
                      command=self._eliminar_fuente).pack(side="left", padx=6)
        self.t_fuentes = Tabla(t, [("Fuente", 220, "izq"), ("Al mes", 130, "der"), ("Días de pago", 120, "centro"),
                                   ("Tipo", 90, "centro"), ("Estado", 220, "izq")], alto=8,
                               al_doble_click=lambda _id: self._editar_fuente())
        self.t_fuentes.pack(fill="both", expand=True)

    def _dialogo_fuente(self, f) -> None:
        campos = [
            Campo("nombre", "Nombre", defecto=f["nombre"] if f else None, ayuda="Ej.: Sueldo, Freelance"),
            Campo("monto", "¿Cuánto recibes al mes?", "monto",
                  defecto=formato(f["monto_mensual"], signo=False) if f else None,
                  ayuda="El total del mes. Si te pagan por quincena, la app lo divide entre los días de pago."),
            Campo("dias", "Días de pago", defecto=f["dias_pago"] if f else "15,30",
                  ayuda="Separados por coma. 30 o 31 = último día del mes. Ej.: «15,30» quincenal, «30» mensual."),
            Campo("variable", "El valor cambia cada mes (la app usa el promedio de los últimos 3 meses)", "check",
                  defecto=bool(f["variable"]) if f else False),
            Campo("estado", "Estado", "opcion", [(v, k) for k, v in ESTADOS.items()],
                  defecto=f["estado"] if f else "activa"),
        ]

        def guardar(v: dict) -> None:
            parsear_dias_pago(v["dias"])
            self.repo.guardar_fuente(f["id"] if f else None, v["nombre"], v["monto"], v["dias"], v["variable"],
                                     v["estado"])
            self.refrescar()

        Formulario(self, "Editar fuente de ingreso" if f else "Nueva fuente de ingreso", campos, guardar)

    def _editar_fuente(self) -> None:
        id_ = self.t_fuentes.seleccionado()
        if id_ is None:
            return error(self, "Selecciona una fuente.")
        self._dialogo_fuente(self._fuentes[id_])

    def _eliminar_fuente(self) -> None:
        id_ = self.t_fuentes.seleccionado()
        if id_ is None:
            return error(self, "Selecciona una fuente.")
        if confirmar(self, "¿Eliminar esta fuente? Los ingresos ya registrados se conservan."):
            self.repo.eliminar_fuente(id_)
            self.refrescar()

    # ------------------------------------------------------------ parámetros

    def _tab_parametros(self, t) -> None:
        cont = ctk.CTkScrollableFrame(t, fg_color="transparent")
        cont.pack(fill="both", expand=True)
        self.param: dict[str, ctk.CTkEntry] = {}

        def entrada(master, clave: str, etiqueta: str, ayuda: str = "", fila: int = 0) -> None:
            ctk.CTkLabel(master, text=etiqueta, anchor="w").grid(row=fila, column=0, sticky="w", pady=3)
            e = ctk.CTkEntry(master, width=140)
            e.grid(row=fila, column=1, sticky="w", padx=10)
            if ayuda:
                ctk.CTkLabel(master, text=ayuda, text_color=GRIS, anchor="w").grid(row=fila, column=2, sticky="w")
            self.param[clave] = e

        ctk.CTkLabel(cont, text="Niveles de endeudamiento", font=("Segoe UI", 15, "bold"), anchor="w").pack(fill="x")
        ctk.CTkLabel(cont, text="% del ingreso mensual que se va en pagos de deuda el mes siguiente.", text_color=GRIS,
                     anchor="w").pack(fill="x")
        m = ctk.CTkFrame(cont, fg_color="transparent")
        m.pack(fill="x", pady=4)
        entrada(m, "umbral_sano", "Sano por debajo de (%)", fila=0)
        entrada(m, "umbral_moderado", "Moderado por debajo de (%)", fila=1)
        entrada(m, "umbral_alto", "Alto por debajo de (%) — por encima es crítico", fila=2)

        ctk.CTkLabel(cont, text="Reparto del excedente por nivel", font=("Segoe UI", 15, "bold"), anchor="w"
                     ).pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(cont, text="Tres porcentajes separados por coma: ahorro, abono extra a deuda, libre. Deben sumar "
                                "100.", text_color=GRIS, anchor="w").pack(fill="x")
        m = ctk.CTkFrame(cont, fg_color="transparent")
        m.pack(fill="x", pady=4)
        for i, nivel in enumerate(NIVELES):
            entrada(m, f"reparto_{nivel}", NOMBRE_NIVEL[nivel], "ahorro, abono, libre", fila=i)

        ctk.CTkLabel(cont, text="Otros", font=("Segoe UI", 15, "bold"), anchor="w").pack(fill="x", pady=(12, 0))
        m = ctk.CTkFrame(cont, fg_color="transparent")
        m.pack(fill="x", pady=4)
        ctk.CTkLabel(m, text="Estrategia del abono extra", anchor="w").grid(row=0, column=0, sticky="w", pady=3)
        self.estrategia = ctk.CTkComboBox(m, width=320, state="readonly", values=[
            "Avalancha: primero la deuda más cara", "Bola de nieve: primero la deuda más pequeña"])
        self.estrategia.grid(row=0, column=1, columnspan=2, sticky="w", padx=10)
        entrada(m, "tasa_cajita_ea", "Tasa de la Cajita (% E.A.)", "Para estimar el rendimiento de la reserva", 1)
        entrada(m, "tasa_usura_ea", "Usura de respaldo (% E.A.)",
                "Solo si no hay tasas en «Tasas legales» para la fecha. Opcional.", 2)
        entrada(m, "dia_a_dia_estimado", "Gasto del día a día al mes ($)",
                "Se usa mientras no haya 1 mes completo de compras registradas", 3)
        ctk.CTkLabel(m, text="Apariencia", anchor="w").grid(row=4, column=0, sticky="w", pady=3)
        self.apariencia = ctk.CTkComboBox(m, width=140, state="readonly", values=["System", "Light", "Dark"])
        self.apariencia.grid(row=4, column=1, sticky="w", padx=10)
        entrada(m, "dias_alerta", "Avisar pagos con (días de anticipación)", "Alertas de Inicio", 5)

        self.msg_param = ctk.CTkLabel(cont, text="", anchor="w")
        self.msg_param.pack(fill="x", pady=4)
        ctk.CTkButton(cont, text="Guardar parámetros", command=self._guardar_parametros).pack(anchor="w")

    def _cargar_parametros(self) -> None:
        c = self.repo.config()
        for clave, e in self.param.items():
            e.delete(0, "end")
            valor = c.get(clave, "")
            e.insert(0, valor.replace(".", ",") if clave.startswith("tasa") else valor)
        self.estrategia.set(self.estrategia.cget("values")[1 if c.get("estrategia") == "bola_de_nieve" else 0])
        self.apariencia.set(c.get("apariencia", "System"))

    def _guardar_parametros(self) -> None:
        try:
            valores = {}
            umbrales = []
            for k in ("umbral_sano", "umbral_moderado", "umbral_alto"):
                umbrales.append(a_tasa(self.param[k].get()))
                valores[k] = str(umbrales[-1])
            if not 0 < umbrales[0] < umbrales[1] < umbrales[2] <= 100:
                raise ValueError("Los umbrales deben ir de menor a mayor, entre 0 y 100.")
            for nivel in NIVELES:
                partes = [a_tasa(x) for x in self.param[f"reparto_{nivel}"].get().split(",")]
                if len(partes) != 3 or abs(sum(partes) - 100) > 0.01 or min(partes) < 0:
                    raise ValueError(f"El reparto {NOMBRE_NIVEL[nivel]} debe tener 3 valores que sumen 100.")
                valores[f"reparto_{nivel}"] = ",".join(f"{x:g}" for x in partes)
            for k in ("tasa_cajita_ea", "tasa_usura_ea"):
                valores[k] = str(a_tasa(self.param[k].get() or "0"))
            dia = self.param["dia_a_dia_estimado"].get().replace(".", "").replace("$", "").strip() or "0"
            valores["dia_a_dia_estimado"] = str(int(dia))
            dias_alerta = int(self.param["dias_alerta"].get().strip() or "7")
            if not 0 <= dias_alerta <= 60:
                raise ValueError("Los días de anticipación de las alertas deben estar entre 0 y 60.")
            valores["dias_alerta"] = str(dias_alerta)
        except ValueError as e:
            self.msg_param.configure(text=str(e), text_color="#dc2626")
            return
        valores["estrategia"] = "bola_de_nieve" if self.estrategia.get().startswith("Bola") else "avalancha"
        valores["apariencia"] = self.apariencia.get()
        self.repo.guardar_config(valores)
        ctk.set_appearance_mode(valores["apariencia"])
        aplicar_estilo_tablas()
        self.msg_param.configure(text="✓ Guardado", text_color="#16a34a")

    # ------------------------------------------------------------ categorías

    def _tab_categorias(self, t) -> None:
        ctk.CTkLabel(t, text="«Necesidad» = indispensable; «Deseo» = se puede recortar si el plan muestra déficit.",
                     text_color=GRIS, anchor="w").pack(fill="x")
        b = ctk.CTkFrame(t, fg_color="transparent")
        b.pack(fill="x", pady=6)
        ctk.CTkButton(b, text="+ Categoría", command=lambda: self._dialogo_categoria(None)).pack(side="left")
        ctk.CTkButton(b, text="Editar", command=self._editar_categoria).pack(side="left", padx=6)
        self.t_categorias = Tabla(t, [("Categoría", 260, "izq"), ("Grupo", 140, "izq"), ("Activa", 80, "centro")],
                                  alto=14, al_doble_click=lambda _id: self._editar_categoria())
        self.t_categorias.pack(fill="both", expand=True)

    def _dialogo_categoria(self, c) -> None:
        campos = [Campo("nombre", "Nombre", defecto=c["nombre"] if c else None),
                  Campo("grupo", "Grupo", "opcion", [("Necesidad", "necesidad"), ("Deseo", "deseo")],
                        defecto=c["grupo"] if c else "necesidad"),
                  Campo("activa", "Activa", "check", defecto=bool(c["activa"]) if c else True)]

        def guardar(v: dict) -> None:
            self.repo.guardar_categoria(c["id"] if c else None, v["nombre"], v["grupo"], v["activa"])
            self.refrescar()

        Formulario(self, "Editar categoría" if c else "Nueva categoría", campos, guardar)

    def _editar_categoria(self) -> None:
        id_ = self.t_categorias.seleccionado()
        if id_ is None:
            return error(self, "Selecciona una categoría.")
        self._dialogo_categoria(self._categorias[id_])

    # ------------------------------------------------------------ datos

    def _tab_datos(self, t) -> None:
        carpeta = db.carpeta_datos()
        caja = ctk.CTkFrame(t, fg_color=FONDO_TARJETA, corner_radius=12)
        caja.pack(fill="x", pady=6)
        ctk.CTkLabel(caja, text=f"Tus datos están en:\n{carpeta / 'finanzas.db'}", anchor="w", justify="left"
                     ).pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(caja, text="Cada día que abres la app se guarda un respaldo comprimido en la carpeta «respaldos» "
                                "(se conservan 7 diarios y 1 por mes durante 12 meses).", text_color=GRIS,
                     anchor="w", justify="left", wraplength=900).pack(fill="x", padx=14, pady=(0, 12))
        b = ctk.CTkFrame(t, fg_color="transparent")
        b.pack(fill="x", pady=6)
        ctk.CTkButton(b, text="📂 Abrir carpeta de datos", command=lambda: os.startfile(carpeta)).pack(side="left")
        ctk.CTkButton(b, text="📊 Exportar a Excel", command=self._exportar).pack(side="left", padx=8)

    def _exportar(self) -> None:
        destino = filedialog.asksaveasfilename(
            parent=self, defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
            initialdir=db.carpeta_datos(), initialfile=f"finanzas_{date.today().isoformat()}.xlsx")
        if not destino:
            return
        try:
            exportar_excel(self.repo, Path(destino))
        except PermissionError:
            return error(self, "No se pudo guardar: cierra el archivo si está abierto en Excel.")
        messagebox.showinfo("Exportado", f"Archivo guardado en:\n{destino}", parent=self)

    # ------------------------------------------------------------ tasas legales

    def _tab_tasas(self, t) -> None:
        ctk.CTkLabel(t, text="Interés bancario corriente (IBC) y tasa de usura certificados por la Superintendencia "
                             "Financiera para cada periodo y modalidad. Se usan para limitar la tasa de mora y para "
                             "las alertas. Se ingresan a mano desde la certificación vigente; la app no trae tasas fijas.",
                     text_color=GRIS, wraplength=950, justify="left", anchor="w").pack(fill="x")
        b = ctk.CTkFrame(t, fg_color="transparent")
        b.pack(fill="x", pady=6)
        ctk.CTkButton(b, text="+ Periodo", command=lambda: self._dialogo_tasa(None)).pack(side="left")
        ctk.CTkButton(b, text="Editar", command=self._editar_tasa).pack(side="left", padx=6)
        ctk.CTkButton(b, text="Eliminar", fg_color="transparent", border_width=1, text_color=("gray10", "gray90"),
                      command=self._eliminar_tasa).pack(side="left", padx=6)
        self.t_tasas = Tabla(t, [("Modalidad", 140, "izq"), ("Desde", 100, "centro"), ("Hasta", 100, "centro"),
                                 ("IBC E.A.", 100, "der"), ("Usura E.A.", 100, "der"), ("Notas", 300, "izq")],
                             alto=12, al_doble_click=lambda _id: self._editar_tasa())
        self.t_tasas.pack(fill="both", expand=True)

    def _dialogo_tasa(self, fila) -> None:
        from .condiciones import MODALIDADES_LEGALES
        campos = [
            Campo("modalidad", "Modalidad", "opcion", MODALIDADES_LEGALES, defecto=fila["modalidad"] if fila else "consumo"),
            Campo("desde", "Desde", "fecha", defecto=fila["desde"] if fila else None),
            Campo("hasta", "Hasta", "fecha", defecto=fila["hasta"] if fila else None),
            Campo("ibc", "Interés bancario corriente (% E.A.)", "tasa", opcional=True,
                  defecto=str(fila["ibc_ea"]).replace(".", ",") if fila and fila["ibc_ea"] else None),
            Campo("usura", "Tasa de usura (% E.A.)", "tasa",
                  defecto=str(fila["usura_ea"]).replace(".", ",") if fila else None),
            Campo("notas", "Notas (ej. número de resolución)", opcional=True, defecto=fila["notas"] if fila else None),
        ]

        def guardar(v: dict) -> None:
            self.repo.guardar_tasa_legal(fila["id"] if fila else None, v["modalidad"], v["desde"], v["hasta"],
                                         v["usura"], v["ibc"], v["notas"] or "")
            self.refrescar()

        Formulario(self, "Tasa legal del periodo", campos, guardar)

    def _editar_tasa(self) -> None:
        id_ = self.t_tasas.seleccionado()
        if id_ is None:
            return error(self, "Selecciona un periodo.")
        self._dialogo_tasa(next(t for t in self.repo.tasas_legales() if t["id"] == id_))

    def _eliminar_tasa(self) -> None:
        id_ = self.t_tasas.seleccionado()
        if id_ is None:
            return error(self, "Selecciona un periodo.")
        if confirmar(self, "¿Eliminar esta tasa? La mora ya liquidada no cambia."):
            self.repo.eliminar_tasa_legal(id_)
            self.refrescar()
