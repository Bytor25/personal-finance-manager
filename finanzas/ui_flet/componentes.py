"""Componentes reutilizables: página base, tarjetas, tablas, formularios y diálogos.

Todos usan composición (`.vista` es el control de Flet) para no depender de cómo Flet
maneja las subclases de sus controles.
"""

import asyncio
import inspect
from datetime import date, datetime
from typing import Any, Callable

import flet as ft

from ..campos import Campo, convertir, parsear_fecha, visible
from ..fechas import nombre_periodo, periodo, periodo_siguiente
from .tema import GRIS, ROJO, c

RADIO = 16


# ---------------------------------------------------------------- textos y botones

def texto(valor: str, tamano: int = 14, peso=None, color=None, **kw) -> ft.Text:
    return ft.Text(valor, size=tamano, weight=peso, color=c(color) if color else None, **kw)


def ayuda(valor: str) -> ft.Text:
    return ft.Text(valor, size=12, color=GRIS)


def titulo_seccion(valor: str) -> ft.Text:
    return ft.Text(valor, size=17, weight=ft.FontWeight.W_600)


def boton(etiqueta: str, al_hacer_clic: Callable | None = None, icono=None, estilo: str = "lleno",
          color=None, deshabilitado: bool = False) -> ft.Control:
    """estilo: lleno | tonal | borde | texto."""
    clase = {"lleno": ft.FilledButton, "tonal": ft.FilledTonalButton, "borde": ft.OutlinedButton,
             "texto": ft.TextButton}[estilo]
    kw = {}
    if color and estilo in ("lleno", "tonal"):
        kw["bgcolor"] = c(color)
        kw["color"] = ft.Colors.WHITE
    return clase(content=etiqueta, icon=icono, on_click=al_hacer_clic, disabled=deshabilitado, **kw)


def barra_botones(*controles: ft.Control, derecha: ft.Control | None = None) -> ft.Row:
    fila = ft.Row(list(controles), wrap=True, spacing=8, run_spacing=8,
                  vertical_alignment=ft.CrossAxisAlignment.CENTER)
    if derecha is not None:
        return ft.ResponsiveRow([ft.Container(fila, col={"xs": 12, "lg": 8}),
                                 ft.Container(derecha, col={"xs": 12, "lg": 4}, alignment=ft.Alignment.CENTER_RIGHT)],
                                run_spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    return fila


def tarjeta(*controles: ft.Control, padding: int = 16, col=None, color=None, espacio: int = 6) -> ft.Container:
    return ft.Container(
        content=ft.Column(list(controles), spacing=espacio, tight=True),
        bgcolor=c(color) if color else ft.Colors.SURFACE_CONTAINER_LOW, border_radius=RADIO, padding=padding,
        col=col, animate=ft.Animation(250, ft.AnimationCurve.EASE_OUT))


def seccion(titulo: str, *controles: ft.Control, explicacion: str = "") -> ft.Container:
    cabeza = [titulo_seccion(titulo)] + ([ayuda(explicacion)] if explicacion else [])
    return tarjeta(*cabeza, *controles, espacio=10)


def contenedor(control: ft.Control | None = None) -> ft.Column:
    """Columna vacía que se rellena en cada `refrescar` (ej. alertas o resúmenes)."""
    return ft.Column([control] if control else [], spacing=6, tight=True)


# ---------------------------------------------------------------- cifras y medidores

class TarjetaCifra:
    """Recuadro con una pregunta, una cifra grande y una nota. Se acomoda en una ResponsiveRow."""

    def __init__(self, titulo: str, color=None, col=None):
        self._color = color
        self.cifra = ft.Text("—", size=24, weight=ft.FontWeight.BOLD, color=c(color) if color else None)
        self.nota = ft.Text("", size=12, color=GRIS)
        self.vista = tarjeta(ft.Text(titulo, size=13, color=GRIS), self.cifra, self.nota,
                             col=col or {"xs": 12, "sm": 6, "lg": 3}, espacio=4)

    def mostrar(self, cifra: str, nota: str = "", color=None) -> None:
        self.cifra.value = cifra
        if color or self._color:
            self.cifra.color = c(color or self._color)
        self.nota.value = nota


class Medidor:
    def __init__(self, titulo: str, col=None):
        self.cifra = ft.Text("", size=17, weight=ft.FontWeight.W_600)
        self.barra = ft.ProgressBar(value=0, bar_height=10, border_radius=5)
        self.nota = ft.Text("", size=12, color=GRIS)
        self.vista = tarjeta(ft.Text(titulo, size=13, color=GRIS), self.cifra, self.barra, self.nota,
                             col=col or {"xs": 12, "md": 6}, espacio=8)

    def mostrar(self, cifra: str, progreso: float, color, nota: str) -> None:
        self.cifra.value = cifra
        self.cifra.color = c(color)
        self.barra.value = max(0.0, min(1.0, progreso))
        self.barra.color = c(color)
        self.nota.value = nota


def linea_dato(etiqueta: str, valor: str, color=None, negrita: bool = True) -> ft.Row:
    return ft.Row([ft.Text(etiqueta, expand=True, size=13),
                   ft.Text(valor, size=13, weight=ft.FontWeight.W_600 if negrita else None,
                           color=c(color) if color else None)], spacing=12)


def aviso(valor: str, color=None, icono: str = "") -> ft.Text:
    return ft.Text((icono + " " if icono else "") + valor, size=13, color=c(color) if color else None)


# ---------------------------------------------------------------- selector de mes

class SelectorMes:
    def __init__(self, al_cambiar: Callable[[str], None], inicial: str | None = None):
        self.periodo = inicial or periodo(date.today())
        self.al_cambiar = al_cambiar
        self.etiqueta = ft.Text(nombre_periodo(self.periodo), size=15, weight=ft.FontWeight.W_600, width=120,
                                text_align=ft.TextAlign.CENTER)
        self.vista = ft.Container(
            ft.Row([ft.IconButton(ft.Icons.CHEVRON_LEFT, on_click=lambda _e: self._mover(-1), tooltip="Mes anterior"),
                    self.etiqueta,
                    ft.IconButton(ft.Icons.CHEVRON_RIGHT, on_click=lambda _e: self._mover(1),
                                  tooltip="Mes siguiente")], spacing=0, tight=True),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW, border_radius=24)

    def fijar(self, per: str) -> None:
        self.periodo = per
        self.etiqueta.value = nombre_periodo(per)

    def _mover(self, n: int) -> None:
        self.fijar(periodo_siguiente(self.periodo, n))
        self.al_cambiar(self.periodo)


# ---------------------------------------------------------------- tabla

class Tabla:
    """DataTable con selección de una fila, doble clic y desplazamiento horizontal en ventanas angostas.

    `columnas`: lista de (título, alineación) con alineación izq | der | centro.
    Cada fila de `cargar` es (id, valores); un valor puede ser texto, (texto, color) o un control.
    """

    def __init__(self, columnas: list[tuple[str, str]], al_doble_clic: Callable[[Any], None] | None = None,
                 al_seleccionar: Callable[[Any], None] | None = None, vacio: str = "Sin datos todavía"):
        self.columnas = columnas
        self.al_doble_clic = al_doble_clic
        self.al_seleccionar = al_seleccionar
        self._sel: ft.DataRow | None = None
        self.tabla = ft.DataTable(
            columns=self._columnas(columnas), rows=[], heading_row_height=40, data_row_min_height=38,
            data_row_max_height=64, column_spacing=22, horizontal_margin=12, show_checkbox_column=False,
            heading_text_style=ft.TextStyle(weight=ft.FontWeight.W_600, size=13, color=GRIS),
            divider_thickness=0.5)
        self.vacio = ft.Container(ft.Text(vacio, color=GRIS, size=13), padding=ft.Padding.symmetric(vertical=10, horizontal=12),
                                  visible=False)
        self.vista = ft.Column([ft.Row([self.tabla], scroll=ft.ScrollMode.AUTO), self.vacio], spacing=0)

    @staticmethod
    def _columnas(columnas) -> list[ft.DataColumn]:
        return [ft.DataColumn(label=ft.Text(t), numeric=alin == "der") for t, alin in columnas]

    def cambiar_columnas(self, columnas: list[tuple[str, str]]) -> None:
        self.columnas = columnas
        self.tabla.columns = self._columnas(columnas)

    def _celda(self, valor, alin: str) -> ft.DataCell:
        if isinstance(valor, ft.Control):
            contenido = valor
        else:
            color = None
            if isinstance(valor, tuple):
                valor, color = valor
            contenido = ft.Text("" if valor is None else str(valor), size=13, color=c(color) if color else None,
                                text_align=ft.TextAlign.RIGHT if alin == "der" else
                                ft.TextAlign.CENTER if alin == "centro" else ft.TextAlign.LEFT)
        return ft.DataCell(content=contenido)

    def cargar(self, filas: list[tuple[Any, list]]) -> None:
        anterior = self.seleccionado()
        self._sel = None
        rows = []
        for id_, valores in filas:
            fila = ft.DataRow(cells=[self._celda(v, alin) for v, (_, alin) in zip(valores, self.columnas)], data=id_)
            fila.on_select_change = lambda _e, f=fila: self._seleccionar(f)
            for celda in fila.cells:
                celda.on_double_tap = lambda _e, f=fila: self._doble(f)
                celda.on_tap = lambda _e, f=fila: self._seleccionar(f)
            if anterior is not None and id_ == anterior:
                fila.selected = True
                self._sel = fila
            rows.append(fila)
        self.tabla.rows = rows
        self.vacio.visible = not rows

    def _seleccionar(self, fila: ft.DataRow) -> None:
        if self._sel is not None and self._sel is not fila:
            self._sel.selected = False
        fila.selected = True
        self._sel = fila
        self.tabla.update()
        if self.al_seleccionar:
            self.al_seleccionar(fila.data)

    def _doble(self, fila: ft.DataRow) -> None:
        self._seleccionar(fila)
        if self.al_doble_clic:
            resultado = self.al_doble_clic(fila.data)
            if inspect.isawaitable(resultado):
                asyncio.ensure_future(resultado)

    def seleccionado(self) -> Any:
        return self._sel.data if self._sel is not None else None

    def limpiar_seleccion(self) -> None:
        if self._sel is not None:
            self._sel.selected = False
        self._sel = None


# ---------------------------------------------------------------- diálogos

def cerrar(page: ft.Page, dialogo: ft.DialogControl) -> None:
    """Cierra un diálogo concreto (no necesariamente el de encima)."""
    if dialogo.open:
        dialogo.open = False
        dialogo.update()


async def confirmar(page: ft.Page, mensaje: str, titulo: str = "¿Seguro?", si: str = "Sí",
                    no: str = "Cancelar", peligro: bool = False) -> bool:
    futuro: asyncio.Future = asyncio.get_running_loop().create_future()

    async def responder(valor: bool) -> None:
        cerrar(page, dialogo)
        if not futuro.done():
            futuro.set_result(valor)

    async def al_si(_e):
        await responder(True)

    async def al_no(_e):
        await responder(False)

    dialogo = ft.AlertDialog(
        modal=True, title=ft.Text(titulo), content=ft.Container(ft.Text(mensaje, size=14), width=440),
        actions=[ft.TextButton(no, on_click=al_no),
                 ft.FilledButton(si, on_click=al_si, bgcolor=c(ROJO) if peligro else None,
                                 color=ft.Colors.WHITE if peligro else None)],
        scrollable=True)
    page.show_dialog(dialogo)
    return await futuro


def informar(page: ft.Page, titulo: str, mensaje: str | list[ft.Control], icono=ft.Icons.CHECK_CIRCLE_OUTLINE) -> None:
    contenido = ft.Column(mensaje if isinstance(mensaje, list) else [ft.Text(mensaje, size=14)], tight=True,
                          spacing=6)
    dialogo = ft.AlertDialog(title=ft.Text(titulo), icon=ft.Icon(icono), content=ft.Container(contenido, width=460),
                             scrollable=True)
    dialogo.actions = [ft.FilledButton("Entendido", on_click=lambda _e: cerrar(page, dialogo))]
    page.show_dialog(dialogo)


def notificar(page: ft.Page, mensaje: str, error: bool = False) -> None:
    page.show_dialog(ft.SnackBar(ft.Text(mensaje, color=ft.Colors.WHITE if error else None),
                                 bgcolor=c(ROJO) if error else None, behavior=ft.SnackBarBehavior.FLOATING,
                                 width=min(560, (page.width or 800) - 40), duration=3500, show_close_icon=True))


def error(page: ft.Page, mensaje: str) -> None:
    notificar(page, mensaje, error=True)


# ---------------------------------------------------------------- formulario

class Formulario:
    """Diálogo con campos (`finanzas.campos.Campo`). `al_guardar(valores)` puede ser async y lanzar
    ValueError para mostrar el error sin cerrar el diálogo."""

    def __init__(self, page: ft.Page, titulo: str, campos: list[Campo], al_guardar: Callable[[dict], Any],
                 texto_boton: str = "Guardar", ancho: int = 480, explicacion: str = ""):
        self.page = page
        self.campos = campos
        self.al_guardar = al_guardar
        self.widgets: dict[str, ft.Control] = {}
        self.filas: dict[str, ft.Column] = {}
        ancho = int(min(ancho, (page.width or 1000) - 80))
        controles: list[ft.Control] = [ayuda(explicacion)] if explicacion else []
        for campo in campos:
            fila = self._crear(campo, ancho)
            self.filas[campo.clave] = fila
            controles.append(fila)
        self.mensaje = ft.Text("", color=c(ROJO), size=13)
        controles.append(self.mensaje)
        self.boton = ft.FilledButton(texto_boton, on_click=self._guardar)
        self.dialogo = ft.AlertDialog(
            modal=True, title=ft.Text(titulo), scrollable=True,
            content=ft.Container(ft.Column(controles, spacing=12, tight=True,
                                           horizontal_alignment=ft.CrossAxisAlignment.STRETCH), width=ancho),
            actions=[ft.TextButton("Cancelar", on_click=lambda _e: cerrar(page, self.dialogo)), self.boton])
        self._actualizar_visibles()
        page.show_dialog(self.dialogo)

    def _crear(self, campo: Campo, ancho: int) -> ft.Column:
        etiqueta = campo.etiqueta + (" (opcional)" if campo.opcional else "")
        if campo.tipo == "check":
            w = ft.Checkbox(label=campo.etiqueta, value=bool(campo.defecto), on_change=self._al_cambiar)
        elif campo.tipo == "opcion":
            indice = next((i for i, (_, v) in enumerate(campo.opciones) if v == campo.defecto), 0)
            w = ft.Dropdown(label=etiqueta, width=ancho, value=str(indice) if campo.opciones else None,
                            options=[ft.DropdownOption(key=str(i), text=e) for i, (e, _) in enumerate(campo.opciones)],
                            on_select=self._al_cambiar, menu_width=ancho)
        else:
            w = ft.TextField(label=etiqueta, value="" if campo.defecto is None else str(campo.defecto),
                             on_submit=self._guardar, dense=False, autofocus=not self.widgets,
                             keyboard_type=ft.KeyboardType.NUMBER if campo.tipo in ("monto", "entero", "tasa")
                             else ft.KeyboardType.TEXT,
                             prefix="$ " if campo.tipo == "monto" else None,
                             suffix="%" if campo.tipo == "tasa" else None)
            if campo.tipo == "fecha":
                w.hint_text = "AAAA-MM-DD"
                w.suffix_icon = ft.IconButton(ft.Icons.CALENDAR_MONTH, tooltip="Elegir en el calendario",
                                              on_click=lambda _e, t=w: self._calendario(t))
        self.widgets[campo.clave] = w
        hijos = [w] + ([ayuda(campo.ayuda)] if campo.ayuda else [])
        return ft.Column(hijos, spacing=4, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    def _calendario(self, campo_texto: ft.TextField) -> None:
        try:
            actual = parsear_fecha(campo_texto.value or "")
        except ValueError:
            actual = date.today()

        def elegido(e) -> None:
            valor = e.control.value
            if valor:
                campo_texto.value = (valor.date() if isinstance(valor, datetime) else valor).isoformat()
                campo_texto.update()

        self.page.show_dialog(ft.DatePicker(value=datetime(actual.year, actual.month, actual.day),
                                            first_date=datetime(2000, 1, 1), last_date=datetime(2100, 12, 31),
                                            on_change=elegido, help_text="Elige la fecha", cancel_text="Cancelar",
                                            confirm_text="Aceptar"))

    def _crudo(self, campo: Campo) -> Any:
        w = self.widgets[campo.clave]
        if campo.tipo == "check":
            return bool(w.value)
        if campo.tipo == "opcion":
            if w.value is None or not campo.opciones:
                return None
            return campo.opciones[int(w.value)][1]
        return (w.value or "").strip()

    def _visibles(self) -> set[str]:
        crudos = {campo.clave: self._crudo(campo) for campo in self.campos}
        visibles: set[str] = set()
        for campo in self.campos:
            if visible(campo, crudos, visibles):
                visibles.add(campo.clave)
        return visibles

    def _actualizar_visibles(self) -> None:
        visibles = self._visibles()
        for campo in self.campos:
            self.filas[campo.clave].visible = campo.clave in visibles

    def _al_cambiar(self, _e=None) -> None:
        self._actualizar_visibles()
        self.dialogo.update()

    def valores(self) -> dict:
        visibles = self._visibles()
        resultado = {}
        for campo in self.campos:
            if campo.clave not in visibles:
                resultado[campo.clave] = None
                continue
            crudo = self._crudo(campo)
            if campo.tipo in ("check", "opcion"):
                resultado[campo.clave] = crudo
            elif crudo == "":
                if not campo.opcional:
                    raise ValueError(f"Completa el campo «{campo.etiqueta}»")
                resultado[campo.clave] = None
            else:
                resultado[campo.clave] = convertir(campo, crudo)
        return resultado

    async def _guardar(self, _e=None) -> None:
        self.mensaje.value = ""
        self.boton.disabled = True
        self.dialogo.update()
        try:
            resultado = self.al_guardar(self.valores())
            if inspect.isawaitable(resultado):
                await resultado
        except ValueError as ex:
            self.mensaje.value = str(ex)
            self.boton.disabled = False
            self.dialogo.update()
            return
        except Exception:
            self.boton.disabled = False
            self.dialogo.update()
            raise
        cerrar(self.page, self.dialogo)


# ---------------------------------------------------------------- página base

class Pagina:
    """Página desplazable con encabezado. Las subclases implementan `construir()` y `refrescar()`."""

    titulo = ""
    icono = ft.Icons.CIRCLE_OUTLINED
    icono_activo = None

    def __init__(self, app):
        self.app = app
        self.repo = app.repo
        self.page: ft.Page = app.page
        self.acciones = ft.Row(spacing=8, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self.controles: list[ft.Control] = []
        self.construir()
        encabezado = ft.Row([ft.Text(self.titulo, size=28, weight=ft.FontWeight.BOLD), self.acciones],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True, run_spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self.vista = ft.ListView([encabezado] + self.controles, expand=True, spacing=14,
                                 padding=ft.Padding.only(left=24, right=24, top=20, bottom=32))

    def agregar(self, *controles: ft.Control) -> None:
        self.controles.extend(controles)

    def construir(self) -> None:
        raise NotImplementedError

    def refrescar(self) -> None:
        raise NotImplementedError

    # Atajos
    def cambio(self) -> None:
        """Tras guardar algo: refresca la página visible."""
        self.app.datos_cambiaron()

    def formulario(self, *args, **kwargs) -> Formulario:
        return Formulario(self.page, *args, **kwargs)

    async def confirmar(self, mensaje: str, **kwargs) -> bool:
        return await confirmar(self.page, mensaje, **kwargs)

    def informar(self, titulo: str, mensaje, **kwargs) -> None:
        informar(self.page, titulo, mensaje, **kwargs)

    def error(self, mensaje: str) -> None:
        error(self.page, mensaje)

    def notificar(self, mensaje: str) -> None:
        notificar(self.page, mensaje)


def requiere(tabla: Tabla, pagina: Pagina, mensaje: str):
    """Id seleccionado de la tabla o None (mostrando `mensaje`)."""
    id_ = tabla.seleccionado()
    if id_ is None:
        pagina.error(mensaje)
    return id_


class Pestanas:
    """Pestañas que muestran un control a la vez (sin TabBarView, que exige un alto fijo)."""

    def __init__(self, paginas: list[tuple[str, Any, ft.Control]], al_cambiar: Callable[[int], None] | None = None):
        self.cuerpos = [p[2] for p in paginas]
        self.al_cambiar = al_cambiar
        self.cuerpo = ft.Container(self.cuerpos[0], padding=ft.Padding.only(top=8))
        self.tabs = ft.Tabs(length=len(paginas), selected_index=0, on_change=self._cambiar,
                            content=ft.TabBar(tabs=[ft.Tab(label=t, icon=i) for t, i, _ in paginas], scrollable=True,
                                              tab_alignment=ft.TabAlignment.START))
        self.vista = ft.Column([self.tabs, self.cuerpo], spacing=4)

    @property
    def indice(self) -> int:
        return self.tabs.selected_index or 0

    def _cambiar(self, _e=None) -> None:
        self.cuerpo.content = self.cuerpos[self.indice]
        if self.al_cambiar:
            self.al_cambiar(self.indice)
        self.cuerpo.update()
