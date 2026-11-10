"""Ventana principal (Flet): navegación lateral adaptable y páginas que se crean al abrirlas."""

import asyncio
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

import flet as ft

from .. import __version__, db
from ..repositorio import Repositorio
from . import tema
from .componentes import error

ICONO = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets" / "finanzas.ico"
ANCHO_EXTENDIDO = 1100   # Desde este ancho la barra lateral muestra los nombres.
ANCHO_COMPACTO = 720     # Por debajo, la barra se vuelve un menú desplegable.

PAGINAS = [
    ("inicio", "Inicio", ft.Icons.HOME_OUTLINED, ft.Icons.HOME),
    ("movimientos", "Ingresos y compras", ft.Icons.PAYMENTS_OUTLINED, ft.Icons.PAYMENTS),
    ("servicios", "Servicios", ft.Icons.RECEIPT_LONG_OUTLINED, ft.Icons.RECEIPT_LONG),
    ("deudas", "Tarjetas y deudas", ft.Icons.CREDIT_CARD_OUTLINED, ft.Icons.CREDIT_CARD),
    ("plan", "Plan del ingreso", ft.Icons.CALCULATE_OUTLINED, ft.Icons.CALCULATE),
    ("reserva", "Reserva (Cajita)", ft.Icons.ACCOUNT_BALANCE_OUTLINED, ft.Icons.ACCOUNT_BALANCE),
    ("ahorros", "Ahorros (cajas)", ft.Icons.SAVINGS_OUTLINED, ft.Icons.SAVINGS),
    ("configuracion", "Configuración", ft.Icons.SETTINGS_OUTLINED, ft.Icons.SETTINGS),
]


def _clase(clave: str):
    """Importa la página solo cuando se abre por primera vez (arranque más rápido).

    Las importaciones van escritas una por una para que PyInstaller las incluya en el ejecutable.
    """
    if clave == "inicio":
        from .paginas.inicio import PaginaInicio as clase
    elif clave == "movimientos":
        from .paginas.movimientos import PaginaMovimientos as clase
    elif clave == "servicios":
        from .paginas.servicios import PaginaServicios as clase
    elif clave == "deudas":
        from .paginas.deudas import PaginaDeudas as clase
    elif clave == "plan":
        from .paginas.plan import PaginaPlan as clase
    elif clave == "reserva":
        from .paginas.reserva import PaginaReserva as clase
    elif clave == "ahorros":
        from .paginas.ahorros import PaginaAhorros as clase
    else:
        from .paginas.configuracion import PaginaConfiguracion as clase
    return clase


class App:
    def __init__(self, page: ft.Page, repo: Repositorio):
        self.page = page
        self.repo = repo
        self.paginas: dict = {}
        self.actual: str | None = None

        page.title = f"Finanzas personales {__version__}"
        page.padding = 0
        page.spacing = 0
        page.window.min_width = 420
        page.window.min_height = 480
        page.window.maximized = True  # Cabe en cualquier pantalla y escala de Windows; se puede restaurar y redimensionar.
        if ICONO.exists():
            page.window.icon = str(ICONO)
        tema.aplicar(page, repo.config().get("apariencia", "System"))
        page.on_resize = self._al_redimensionar
        page.on_platform_brightness_change = self._al_cambiar_brillo
        page.on_error = lambda e: print("Error de Flet:", e.data, file=sys.stderr)

        self.rail = ft.NavigationRail(
            selected_index=0, label_type=ft.NavigationRailLabelType.ALL, min_width=84, min_extended_width=232,
            group_alignment=-0.85, on_change=self._al_navegar,
            leading=ft.Container(self._marca(), padding=ft.Padding.only(top=12, bottom=12)),
            destinations=[ft.NavigationRailDestination(icon=i, selected_icon=s, label=t) for _, t, i, s in PAGINAS])
        self.menu = ft.NavigationDrawer(
            on_change=self._al_navegar_menu, selected_index=0,
            controls=[ft.Container(self._marca(True), padding=ft.Padding.only(left=24, top=20, bottom=12))]
            + [ft.NavigationDrawerDestination(icon=i, selected_icon=s, label=t) for _, t, i, s in PAGINAS])
        page.drawer = self.menu
        self.boton_menu = ft.IconButton(ft.Icons.MENU, tooltip="Menú", on_click=lambda _e: page.show_drawer())
        self.barra_superior = ft.Container(
            ft.Row([self.boton_menu, ft.Text("Finanzas", size=18, weight=ft.FontWeight.BOLD)], spacing=4),
            padding=ft.Padding.only(left=8, top=6, bottom=2), visible=False)
        # Fundido propio: ft.AnimatedSwitcher deja sin dibujar las ResponsiveRow en el primer cuadro.
        self.contenido = ft.Container(expand=True, opacity=1, animate_opacity=ft.Animation(200, ft.AnimationCurve.EASE_OUT))
        self.separador = ft.VerticalDivider(width=1)
        page.add(ft.Row([self.rail, self.separador,
                         ft.Column([self.barra_superior, self.contenido], expand=True, spacing=0)],
                        expand=True, spacing=0, vertical_alignment=ft.CrossAxisAlignment.STRETCH))
        self._ajustar_navegacion()
        self.mostrar("inicio")

    def _marca(self, extendida: bool = True) -> ft.Control:
        return ft.Column([ft.Icon(ft.Icons.SAVINGS, size=34, color=ft.Colors.PRIMARY),
                          ft.Text("Finanzas", size=20, weight=ft.FontWeight.BOLD),
                          ft.Text("Mes adelantado,\ndeuda bajo control", size=11, color=tema.GRIS,
                                  text_align=ft.TextAlign.CENTER if not extendida else None)],
                         spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True)

    # ------------------------------------------------------------ navegación

    def _ajustar_navegacion(self) -> None:
        ancho = self.page.width or 1320
        compacto = ancho < ANCHO_COMPACTO
        self.rail.visible = self.separador.visible = not compacto
        self.barra_superior.visible = compacto
        self.rail.extended = ancho >= ANCHO_EXTENDIDO
        self.rail.label_type = ft.NavigationRailLabelType.NONE if self.rail.extended else \
            ft.NavigationRailLabelType.ALL
        self.rail.leading.visible = self.rail.extended

    def _al_redimensionar(self, _e=None) -> None:
        antes = (self.rail.visible, self.rail.extended)
        self._ajustar_navegacion()
        if antes != (self.rail.visible, self.rail.extended):
            self.page.update()

    def _al_cambiar_brillo(self, _e=None) -> None:
        tema.actualizar_brillo(self.page)
        self.datos_cambiaron()

    def _al_navegar(self, e) -> None:
        self.mostrar(PAGINAS[e.control.selected_index][0])

    def _al_navegar_menu(self, e) -> None:
        self.page.close_drawer() if hasattr(self.page, "close_drawer") else None
        self.mostrar(PAGINAS[e.control.selected_index][0])

    def mostrar(self, clave: str) -> None:
        indice = next(i for i, p in enumerate(PAGINAS) if p[0] == clave)
        self.rail.selected_index = self.menu.selected_index = indice
        if clave not in self.paginas:
            self.paginas[clave] = _clase(clave)(self)
        self.actual = clave
        pagina = self.paginas[clave]
        self._refrescar(pagina)
        self.contenido.content = pagina.vista
        self.contenido.opacity = 0
        self.page.update()
        self.page.run_task(self._aparecer)

    async def _aparecer(self) -> None:
        await asyncio.sleep(0.03)
        self.contenido.opacity = 1
        self.contenido.update()

    def _refrescar(self, pagina) -> None:
        try:
            pagina.refrescar()
        except Exception as ex:  # Un error al calcular no debe dejar la ventana en blanco.
            traceback.print_exc()
            error(self.page, f"Ocurrió un error al mostrar «{pagina.titulo}»: {ex}")

    def datos_cambiaron(self) -> None:
        """Llamar después de cualquier cambio: refresca la página visible y marca las demás para refrescar."""
        if self.actual:
            self._refrescar(self.paginas[self.actual])
        self.page.update()

    def cambiar_apariencia(self, apariencia: str) -> None:
        tema.aplicar(self.page, apariencia)
        # Los colores propios se calculan al refrescar: se reconstruyen las páginas abiertas.
        actual = self.actual
        self.paginas.clear()
        self.mostrar(actual or "inicio")


def _abrir_base() -> Repositorio:
    carpeta = db.carpeta_datos()
    ruta = carpeta / "finanzas.db"
    try:
        db.respaldar_archivo(ruta, carpeta / "respaldos")  # Antes de cualquier cambio de estructura.
    except Exception:
        traceback.print_exc()
    con = db.conectar(ruta, multihilo=True)
    try:
        db.mantenimiento(con, carpeta / "respaldos")
    except Exception:  # Un fallo de respaldo no debe impedir abrir la app.
        traceback.print_exc()
    repo = Repositorio(con)
    repo.generar_cierre()
    return repo


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _fuentes_de_respaldo_en_linea() -> None:
    """Con no_cdn, Flet busca las fuentes de emoji en una carpeta local vacía y salen como cuadritos.

    Se deja el motor (CanvasKit) local, para que la app abra sin internet, pero las fuentes de
    respaldo se piden a Google Fonts como hace Flutter por defecto. Sin internet solo faltan los emojis.
    Revisar al actualizar Flet (probado con 1.0.5).
    """
    from flet_web.fastapi import flet_static_files

    original = flet_static_files.patch_index_html
    if getattr(original, "_finanzas", False):
        return

    def parchear(*args, index_path: str, **kwargs):
        original(*args, index_path=index_path, **kwargs)
        ruta = Path(index_path)
        html = ruta.read_text(encoding="utf-8")
        ruta.write_text(html.replace('flet.fontFallbackBaseUrl="assets/fonts/";',
                                     'flet.fontFallbackBaseUrl="https://fonts.gstatic.com/s/";'),
                        encoding="utf-8")

    parchear._finanzas = True
    flet_static_files.patch_index_html = parchear


def _abrir_en_webview(iniciar) -> None:
    """Sirve la interfaz Flet en modo web (solo en este equipo) y la muestra en una ventana de pywebview.

    Así no se ejecuta flet.exe, que Smart App Control de Windows bloquea por no tener firma digital.
    La ventana usa WebView2, el motor de Edge que ya trae Windows.
    """
    import uvicorn
    import webview

    _fuentes_de_respaldo_en_linea()
    asgi = ft.run(iniciar, assets_dir=str(ICONO.parent), export_asgi_app=True, no_cdn=True)
    puerto = _puerto_libre()
    servidor = uvicorn.Server(uvicorn.Config(
        asgi, host="127.0.0.1", port=puerto, log_level="warning", ws="websockets-sansio"))
    hilo = threading.Thread(target=servidor.run, name="servidor-flet", daemon=True)
    hilo.start()
    limite = time.monotonic() + 20
    while not servidor.started:
        if not hilo.is_alive() or time.monotonic() > limite:
            raise RuntimeError("No se pudo iniciar el servidor interno de la interfaz.")
        time.sleep(0.05)

    webview.create_window(f"Finanzas personales {__version__}", f"http://127.0.0.1:{puerto}",
                          min_size=(420, 480), maximized=True)
    try:
        webview.start(private_mode=False, storage_path=str(db.carpeta_datos() / "webview"))
    finally:
        servidor.should_exit = True
        hilo.join(timeout=5)


def main() -> None:
    repo = _abrir_base()

    def iniciar(page: ft.Page) -> None:
        App(page, repo)

    try:
        if "--flet-nativo" in sys.argv:  # Ventana propia de Flet (flet.exe); Windows puede bloquearla.
            ft.run(iniciar, assets_dir=str(ICONO.parent))
        else:
            _abrir_en_webview(iniciar)
    finally:
        repo.con.close()


if __name__ == "__main__":
    sys.exit(main())
