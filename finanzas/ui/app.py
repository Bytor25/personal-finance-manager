"""Ventana principal: barra lateral de navegación y páginas."""

import sys
import traceback
from pathlib import Path

import customtkinter as ctk

from .. import __version__, db
from ..repositorio import Repositorio
from .widgets import FUENTE_SUBTITULO, GRIS, aplicar_estilo_tablas, error, tamano_ventana

ICONO = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets" / "finanzas.ico"

PAGINAS = [
    ("inicio", "🏠  Inicio"),
    ("movimientos", "💵  Ingresos y compras"),
    ("servicios", "🧾  Servicios"),
    ("deudas", "💳  Tarjetas y deudas"),
    ("plan", "🧮  Plan del ingreso"),
    ("reserva", "🏦  Reserva (Cajita)"),
    ("ahorros", "🐷  Ahorros (cajas)"),
    ("configuracion", "⚙️  Configuración"),
]


class App(ctk.CTk):
    def __init__(self, repo: Repositorio):
        super().__init__()
        self.repo = repo
        self.title(f"Finanzas personales {__version__}")
        tamano_ventana(self, 1320, 840, min_ancho=900, min_alto=560)

        if ICONO.exists():
            self.after(250, lambda: self.iconbitmap(ICONO))  # CustomTkinter pone su ícono a los 200 ms.
        modo = repo.config().get("apariencia", "System")
        ctk.set_appearance_mode(modo)
        aplicar_estilo_tablas()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        lateral = ctk.CTkFrame(self, width=230, corner_radius=0)
        lateral.grid(row=0, column=0, sticky="nsw")
        lateral.grid_propagate(False)
        ctk.CTkLabel(lateral, text="Finanzas", font=("Segoe UI", 24, "bold")).pack(pady=(24, 4))
        ctk.CTkLabel(lateral, text="Mes adelantado, deuda bajo control", text_color=GRIS).pack(pady=(0, 20))
        self.botones: dict[str, ctk.CTkButton] = {}
        for clave, texto in PAGINAS:
            b = ctk.CTkButton(lateral, text=texto, anchor="w", height=38, font=("Segoe UI", 14),
                              fg_color="transparent", text_color=("gray10", "gray90"),
                              hover_color=("gray80", "gray25"), command=lambda c=clave: self.mostrar(c))
            b.pack(fill="x", padx=12, pady=2)
            self.botones[clave] = b

        self.contenido = ctk.CTkFrame(self, fg_color="transparent")
        self.contenido.grid(row=0, column=1, sticky="nsew")
        self.contenido.grid_columnconfigure(0, weight=1)
        self.contenido.grid_rowconfigure(0, weight=1)

        from .ahorros import PaginaAhorros
        from .configuracion import PaginaConfiguracion
        from .deudas import PaginaDeudas
        from .inicio import PaginaInicio
        from .movimientos import PaginaMovimientos
        from .plan import PaginaPlan
        from .reserva import PaginaReserva
        from .servicios import PaginaServicios
        clases = {"inicio": PaginaInicio, "movimientos": PaginaMovimientos, "servicios": PaginaServicios,
                  "deudas": PaginaDeudas, "plan": PaginaPlan, "reserva": PaginaReserva, "ahorros": PaginaAhorros,
                  "configuracion": PaginaConfiguracion}
        self.paginas = {}
        for clave, clase in clases.items():
            pagina = clase(self.contenido, self)
            pagina.grid(row=0, column=0, sticky="nsew")
            self.paginas[clave] = pagina
        self.actual = None
        self.mostrar("inicio")

    def mostrar(self, clave: str) -> None:
        for c, b in self.botones.items():
            b.configure(fg_color=("gray75", "gray30") if c == clave else "transparent")
        self.actual = clave
        pagina = self.paginas[clave]
        # CTkScrollableFrame se ubica con un marco contenedor: ese es el que hay que traer al frente.
        getattr(pagina, "_parent_frame", pagina).tkraise()
        pagina.refrescar()

    def datos_cambiaron(self) -> None:
        """Llamar después de cualquier cambio: refresca la página visible."""
        self.paginas[self.actual].refrescar()

    def report_callback_exception(self, exc, val, tb):
        traceback.print_exception(exc, val, tb)
        error(self, f"Ocurrió un error inesperado:\n{val}\n\nSi se repite, cuéntalo para revisarlo.")


class Pagina(ctk.CTkScrollableFrame):
    titulo = ""

    def __init__(self, master, app: App):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.repo = app.repo
        self.encabezado = ctk.CTkFrame(self, fg_color="transparent")
        self.encabezado.pack(fill="x", padx=24, pady=(20, 10))
        ctk.CTkLabel(self.encabezado, text=self.titulo, font=("Segoe UI", 24, "bold")).pack(side="left")
        self.construir()

    def construir(self) -> None:
        raise NotImplementedError

    def refrescar(self) -> None:
        raise NotImplementedError

    def seccion(self, texto: str, ayuda: str = "") -> ctk.CTkFrame:
        marco = ctk.CTkFrame(self, fg_color="transparent")
        marco.pack(fill="x", padx=24, pady=(14, 4))
        ctk.CTkLabel(marco, text=texto, font=FUENTE_SUBTITULO, anchor="w").pack(fill="x")
        if ayuda:
            ctk.CTkLabel(marco, text=ayuda, text_color=GRIS, anchor="w", justify="left",
                         wraplength=980).pack(fill="x")
        return marco

    def fila_botones(self) -> ctk.CTkFrame:
        marco = ctk.CTkFrame(self, fg_color="transparent")
        marco.pack(fill="x", padx=24, pady=4)
        return marco

    def bloque(self, widget_factory) -> ctk.CTkFrame:
        widget = widget_factory(self)
        widget.pack(fill="x", padx=24, pady=4)
        return widget


def main() -> None:
    carpeta = db.carpeta_datos()
    ruta = carpeta / "finanzas.db"
    try:
        db.respaldar_archivo(ruta, carpeta / "respaldos")  # Antes de cualquier cambio de estructura.
    except Exception:
        traceback.print_exc()
    con = db.conectar(ruta)
    try:
        db.mantenimiento(con, carpeta / "respaldos")
    except Exception:  # Un fallo de respaldo no debe impedir abrir la app.
        traceback.print_exc()
    repo = Repositorio(con)
    repo.generar_cierre()
    app = App(repo)
    app.mainloop()
    con.close()


if __name__ == "__main__":
    sys.exit(main())
