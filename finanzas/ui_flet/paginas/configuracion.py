"""Configuración: fuentes de ingreso, parámetros del plan, tasas legales, categorías y datos."""

import os
from datetime import date
from pathlib import Path

import flet as ft

from ... import db
from ...campos import Campo, pesos
from ...dinero import a_tasa, formato
from ...exportar import exportar_excel
from ...fechas import parsear_dias_pago
from ...plan import NIVELES, NOMBRE_NIVEL
from ...ui.condiciones import MODALIDADES_LEGALES
from ..componentes import (Pagina, Pestanas, Tabla, ayuda, barra_botones, boton, requiere, tarjeta, texto,
                           titulo_seccion)
from ..tema import ROJO, VERDE

ESTADOS = {"activa": "Activa", "esperada": "Esperada (aún no confirmada)", "inactiva": "Inactiva"}
APARIENCIAS = [("System", "Como Windows"), ("Light", "Clara"), ("Dark", "Oscura")]
ESTRATEGIAS = [("avalancha", "Avalancha: primero la deuda más cara"),
               ("bola_de_nieve", "Bola de nieve: primero la deuda más pequeña")]


class PaginaConfiguracion(Pagina):
    titulo = "Configuración"

    def construir(self) -> None:
        self.pestanas = Pestanas([
            ("Ingresos", ft.Icons.PAYMENTS_OUTLINED, self._tab_ingresos()),
            ("Parámetros del plan", ft.Icons.TUNE, self._tab_parametros()),
            ("Tasas legales", ft.Icons.GAVEL, self._tab_tasas()),
            ("Categorías", ft.Icons.CATEGORY_OUTLINED, self._tab_categorias()),
            ("Datos", ft.Icons.STORAGE, self._tab_datos()),
        ])
        self.agregar(tarjeta(self.pestanas.vista))

    def refrescar(self) -> None:
        self.t_tasas.cargar([(t["id"], [t["modalidad"], t["desde"], t["hasta"],
                                        f"{t['ibc_ea']:.2f} %".replace(".", ",") if t["ibc_ea"] else "—",
                                        f"{t['usura_ea']:.2f} %".replace(".", ","), t["notas"]])
                             for t in self.repo.tasas_legales()])
        self._fuentes = {f["id"]: f for f in self.repo.fuentes()}
        self.t_fuentes.cargar([(f["id"], [f["nombre"], pesos(f["monto_mensual"]), f["dias_pago"],
                                          "Variable" if f["variable"] else "Fijo",
                                          (ESTADOS[f["estado"]], VERDE if f["estado"] == "activa" else None)])
                               for f in self._fuentes.values()])
        self._categorias = {c["id"]: c for c in self.repo.categorias(False)}
        self.t_categorias.cargar([(c["id"], [c["nombre"], "Necesidad" if c["grupo"] == "necesidad" else "Deseo",
                                             "Sí" if c["activa"] else "No"]) for c in self._categorias.values()])
        self._cargar_parametros()

    # ------------------------------------------------------------ ingresos

    def _tab_ingresos(self) -> ft.Control:
        self.t_fuentes = Tabla([("Fuente", "izq"), ("Al mes", "der"), ("Días de pago", "centro"), ("Tipo", "centro"),
                                ("Estado", "izq")], al_doble_clic=lambda _id: self._editar_fuente(),
                               vacio="Agrega tu primera fuente de ingreso.")
        return ft.Column([
            ayuda("Tus fuentes de ingreso definen el ingreso mensual estimado (para el % de endeudamiento) y los días "
                  "en que cobras (para saber qué vence antes del próximo ingreso). Un ingreso «esperado» (ej. un "
                  "freelance sin confirmar) no entra al plan, salvo que lo pidas en la simulación."),
            barra_botones(boton("Fuente de ingreso", lambda _e: self._dialogo_fuente(None), ft.Icons.ADD),
                          boton("Editar", self._editar_fuente, ft.Icons.EDIT_OUTLINED, "tonal"),
                          boton("Eliminar", self._eliminar_fuente, ft.Icons.DELETE_OUTLINE, "borde")),
            self.t_fuentes.vista], spacing=10)

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
            self.cambio()

        self.formulario("Editar fuente de ingreso" if f else "Nueva fuente de ingreso", campos, guardar)

    def _editar_fuente(self, _e=None) -> None:
        id_ = requiere(self.t_fuentes, self, "Selecciona una fuente en la tabla.")
        if id_ is not None:
            self._dialogo_fuente(self._fuentes[id_])

    async def _eliminar_fuente(self, _e=None) -> None:
        id_ = requiere(self.t_fuentes, self, "Selecciona una fuente en la tabla.")
        if id_ is not None and await self.confirmar(
                "¿Eliminar esta fuente? Los ingresos ya registrados se conservan.", si="Eliminar", peligro=True):
            self.repo.eliminar_fuente(id_)
            self.cambio()

    # ------------------------------------------------------------ parámetros

    def _tab_parametros(self) -> ft.Control:
        self.param: dict[str, ft.TextField] = {}

        def entrada(clave: str, etiqueta: str, ayuda_: str = "", sufijo: str | None = None, ancho: int = 220,
                    col=None) -> ft.TextField:
            e = ft.TextField(label=etiqueta, helper=ayuda_ or None, helper_max_lines=2, suffix=sufijo,
                             col=col or {"xs": 12, "sm": 6, "lg": 4})
            self.param[clave] = e
            return e

        self.estrategia = ft.Dropdown(label="Estrategia del abono extra", col={"xs": 12, "md": 8},
                                      options=[ft.DropdownOption(key=k, text=t) for k, t in ESTRATEGIAS])
        self.apariencia = ft.Dropdown(label="Apariencia", col={"xs": 12, "sm": 6, "md": 4},
                                      options=[ft.DropdownOption(key=k, text=t) for k, t in APARIENCIAS])
        self.msg_param = ft.Text("", size=13)
        return ft.Column([
            titulo_seccion("Niveles de endeudamiento"),
            ayuda("% del ingreso mensual que se va en pagos de deuda el mes siguiente."),
            ft.ResponsiveRow([entrada("umbral_sano", "Sano por debajo de", sufijo="%"),
                              entrada("umbral_moderado", "Moderado por debajo de", sufijo="%"),
                              entrada("umbral_alto", "Alto por debajo de", "Por encima es crítico", "%")],
                             spacing=12, run_spacing=12),
            ft.Divider(height=20),
            titulo_seccion("Reparto del excedente por nivel"),
            ayuda("Tres porcentajes separados por coma: ahorro, abono extra a deuda, libre. Deben sumar 100."),
            ft.ResponsiveRow([entrada(f"reparto_{n}", NOMBRE_NIVEL[n], "ahorro, abono, libre",
                                      col={"xs": 12, "sm": 6, "lg": 3}) for n in NIVELES], spacing=12, run_spacing=12),
            ft.Divider(height=20),
            titulo_seccion("Otros"),
            ft.ResponsiveRow([
                self.estrategia, self.apariencia,
                entrada("tasa_cajita_ea", "Tasa de la Cajita", "Para estimar el rendimiento de la reserva", "% E.A."),
                entrada("tasa_usura_ea", "Usura de respaldo", "Solo si no hay tasas en «Tasas legales». Opcional.",
                        "% E.A."),
                entrada("dia_a_dia_estimado", "Gasto del día a día al mes ($)",
                        "Mientras no haya 1 mes completo de compras registradas"),
                entrada("dias_alerta", "Avisar pagos con (días de anticipación)", "Alertas de Inicio"),
            ], spacing=12, run_spacing=16),
            ft.Row([boton("Guardar parámetros", self._guardar_parametros, ft.Icons.SAVE), self.msg_param],
                   spacing=14, wrap=True),
        ], spacing=10)

    def _cargar_parametros(self) -> None:
        c = self.repo.config()
        for clave, e in self.param.items():
            valor = c.get(clave, "")
            e.value = valor.replace(".", ",") if clave.startswith("tasa") else valor
        self.estrategia.value = "bola_de_nieve" if c.get("estrategia") == "bola_de_nieve" else "avalancha"
        self.apariencia.value = c.get("apariencia", "System")

    def _guardar_parametros(self, _e=None) -> None:
        try:
            valores = {}
            umbrales = []
            for k in ("umbral_sano", "umbral_moderado", "umbral_alto"):
                umbrales.append(a_tasa(self.param[k].value or ""))
                valores[k] = str(umbrales[-1])
            if not 0 < umbrales[0] < umbrales[1] < umbrales[2] <= 100:
                raise ValueError("Los umbrales deben ir de menor a mayor, entre 0 y 100.")
            for nivel in NIVELES:
                partes = [a_tasa(x) for x in (self.param[f"reparto_{nivel}"].value or "").split(",")]
                if len(partes) != 3 or abs(sum(partes) - 100) > 0.01 or min(partes) < 0:
                    raise ValueError(f"El reparto {NOMBRE_NIVEL[nivel]} debe tener 3 valores que sumen 100.")
                valores[f"reparto_{nivel}"] = ",".join(f"{x:g}" for x in partes)
            for k in ("tasa_cajita_ea", "tasa_usura_ea"):
                valores[k] = str(a_tasa(self.param[k].value or "0"))
            dia = (self.param["dia_a_dia_estimado"].value or "").replace(".", "").replace("$", "").strip() or "0"
            valores["dia_a_dia_estimado"] = str(int(dia))
            dias_alerta = int((self.param["dias_alerta"].value or "").strip() or "7")
            if not 0 <= dias_alerta <= 60:
                raise ValueError("Los días de anticipación de las alertas deben estar entre 0 y 60.")
            valores["dias_alerta"] = str(dias_alerta)
        except ValueError as e:
            self.msg_param.value = str(e)
            self.msg_param.color = ROJO[0]
            self.page.update()
            return
        valores["estrategia"] = self.estrategia.value or "avalancha"
        anterior = self.repo.config().get("apariencia", "System")
        valores["apariencia"] = self.apariencia.value or "System"
        self.repo.guardar_config(valores)
        if valores["apariencia"] != anterior:
            self.app.cambiar_apariencia(valores["apariencia"])
        self.app.page.update()
        self.notificar("✓ Parámetros guardados")

    # ------------------------------------------------------------ categorías

    def _tab_categorias(self) -> ft.Control:
        self.t_categorias = Tabla([("Categoría", "izq"), ("Grupo", "izq"), ("Activa", "centro")],
                                  al_doble_clic=lambda _id: self._editar_categoria())
        return ft.Column([
            ayuda("«Necesidad» = indispensable; «Deseo» = se puede recortar si el plan muestra déficit."),
            barra_botones(boton("Categoría", lambda _e: self._dialogo_categoria(None), ft.Icons.ADD),
                          boton("Editar", self._editar_categoria, ft.Icons.EDIT_OUTLINED, "tonal")),
            self.t_categorias.vista], spacing=10)

    def _dialogo_categoria(self, c) -> None:
        campos = [Campo("nombre", "Nombre", defecto=c["nombre"] if c else None),
                  Campo("grupo", "Grupo", "opcion", [("Necesidad", "necesidad"), ("Deseo", "deseo")],
                        defecto=c["grupo"] if c else "necesidad"),
                  Campo("activa", "Activa", "check", defecto=bool(c["activa"]) if c else True)]

        def guardar(v: dict) -> None:
            self.repo.guardar_categoria(c["id"] if c else None, v["nombre"], v["grupo"], v["activa"])
            self.cambio()

        self.formulario("Editar categoría" if c else "Nueva categoría", campos, guardar)

    def _editar_categoria(self, _e=None) -> None:
        id_ = requiere(self.t_categorias, self, "Selecciona una categoría en la tabla.")
        if id_ is not None:
            self._dialogo_categoria(self._categorias[id_])

    # ------------------------------------------------------------ datos

    def _tab_datos(self) -> ft.Control:
        carpeta = db.carpeta_datos()
        return ft.Column([
            tarjeta(ft.Row([ft.Icon(ft.Icons.FOLDER_OUTLINED, color=ft.Colors.PRIMARY),
                            ft.Column([texto("Tus datos están en:", 13),
                                       ft.Text(str(carpeta / "finanzas.db"), size=13, selectable=True,
                                               weight=ft.FontWeight.W_600)], spacing=2, expand=True, tight=True)]),
                    ayuda("Cada día que abres la app se guarda un respaldo comprimido en la carpeta «respaldos» (se "
                          "conservan 7 diarios y 1 por mes durante 12 meses)."),
                    color=ft.Colors.SURFACE_CONTAINER_HIGH),
            barra_botones(boton("Abrir carpeta de datos", lambda _e: os.startfile(carpeta), ft.Icons.FOLDER_OPEN,
                                "tonal"),
                          boton("Exportar a Excel", self._exportar, ft.Icons.TABLE_VIEW)),
        ], spacing=12)

    async def _exportar(self, _e=None) -> None:
        if not hasattr(self, "_selector_archivo"):
            self._selector_archivo = ft.FilePicker()
            self.page.services.append(self._selector_archivo)
            self.page.update()
        destino = await self._selector_archivo.save_file(
            dialog_title="Exportar a Excel", file_name=f"finanzas_{date.today().isoformat()}.xlsx",
            initial_directory=str(db.carpeta_datos()), file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx"])
        if not destino:
            return
        if not destino.lower().endswith(".xlsx"):
            destino += ".xlsx"
        try:
            exportar_excel(self.repo, Path(destino))
        except PermissionError:
            return self.error("No se pudo guardar: cierra el archivo si está abierto en Excel.")
        self.informar("Exportado", f"Archivo guardado en:\n{destino}")

    # ------------------------------------------------------------ tasas legales

    def _tab_tasas(self) -> ft.Control:
        self.t_tasas = Tabla([("Modalidad", "izq"), ("Desde", "centro"), ("Hasta", "centro"), ("IBC E.A.", "der"),
                              ("Usura E.A.", "der"), ("Notas", "izq")], al_doble_clic=lambda _id: self._editar_tasa(),
                             vacio="Sin tasas registradas.")
        return ft.Column([
            ayuda("Interés bancario corriente (IBC) y tasa de usura certificados por la Superintendencia Financiera "
                  "para cada periodo y modalidad. Se usan para limitar la tasa de mora y para las alertas. Se "
                  "ingresan a mano desde la certificación vigente; la app no trae tasas fijas."),
            barra_botones(boton("Periodo", lambda _e: self._dialogo_tasa(None), ft.Icons.ADD),
                          boton("Editar", self._editar_tasa, ft.Icons.EDIT_OUTLINED, "tonal"),
                          boton("Eliminar", self._eliminar_tasa, ft.Icons.DELETE_OUTLINE, "borde")),
            self.t_tasas.vista], spacing=10)

    def _dialogo_tasa(self, fila) -> None:
        campos = [
            Campo("modalidad", "Modalidad", "opcion", MODALIDADES_LEGALES,
                  defecto=fila["modalidad"] if fila else "consumo"),
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
            self.cambio()

        self.formulario("Tasa legal del periodo", campos, guardar)

    def _editar_tasa(self, _e=None) -> None:
        id_ = requiere(self.t_tasas, self, "Selecciona un periodo en la tabla.")
        if id_ is not None:
            self._dialogo_tasa(next(t for t in self.repo.tasas_legales() if t["id"] == id_))

    async def _eliminar_tasa(self, _e=None) -> None:
        id_ = requiere(self.t_tasas, self, "Selecciona un periodo en la tabla.")
        if id_ is not None and await self.confirmar("¿Eliminar esta tasa? La mora ya liquidada no cambia.",
                                                    si="Eliminar", peligro=True):
            self.repo.eliminar_tasa_legal(id_)
            self.cambio()
