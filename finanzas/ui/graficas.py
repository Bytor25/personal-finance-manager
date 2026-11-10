"""Gráficas con matplotlib embebidas en la interfaz."""

import customtkinter as ctk
import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from ..fechas import nombre_periodo  # noqa: E402
from .widgets import FONDO_TARJETA, GRIS, MORADO, NARANJA, ROJO, VERDE, AMARILLO, color  # noqa: E402

PALETA_PRODUCTOS = ["#7c3aed", "#0891b2", "#db2777", "#ca8a04", "#059669", "#4f46e5"]


def _pesos_corto(valor: float, _pos=None) -> str:
    """Eje en pesos: 1.2M, 350k."""
    valor = valor / 100
    if abs(valor) >= 1_000_000:
        return f"${valor / 1_000_000:.1f}M".replace(".", ",")
    if abs(valor) >= 1_000:
        return f"${valor / 1_000:.0f}k"
    return f"${valor:.0f}"


class Grafica(ctk.CTkFrame):
    """Contenedor de una figura que se redibuja con `dibujar(funcion)`."""

    def __init__(self, master, alto: float = 3.0, ancho: float = 6.0):
        super().__init__(master, fg_color=FONDO_TARJETA, corner_radius=12)
        self.figura = Figure(figsize=(ancho, alto), dpi=100)
        self.lienzo = FigureCanvasTkAgg(self.figura, master=self)
        self.lienzo.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

    def _preparar(self):
        fondo = color(FONDO_TARJETA)
        texto = color(("#111827", "#e5e7eb"))
        self.figura.clear()
        self.figura.set_facecolor(fondo)
        ax = self.figura.add_subplot(111)
        ax.set_facecolor(fondo)
        ax.tick_params(colors=texto, labelsize=9)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            ax.spines[lado].set_color(color(GRIS))
        ax.title.set_color(texto)
        return ax, texto

    def _vacio(self, ax, texto: str, mensaje: str) -> None:
        ax.text(0.5, 0.5, mensaje, ha="center", va="center", color=texto, transform=ax.transAxes, fontsize=11)
        ax.set_xticks([])
        ax.set_yticks([])

    def _terminar(self) -> None:
        texto = color(("#111827", "#e5e7eb"))
        for ax in self.figura.axes:  # set_title aplica el color por defecto: se corrige aquí para el modo oscuro.
            ax.title.set_color(texto)
        self.figura.tight_layout()
        self.lienzo.draw()

    # ------------------------------------------------------------ gráficas

    def en_que_gaste(self, por_categoria) -> None:
        ax, texto = self._preparar()
        ax.set_title("¿En qué gasté?", loc="left", fontsize=12, fontweight="bold")
        filas = list(por_categoria)[:10][::-1]
        if not filas:
            self._vacio(ax, texto, "Sin compras este mes")
        else:
            nombres = [f["categoria"] for f in filas]
            efectivo = [f["efectivo"] for f in filas]
            tarjeta = [f["tarjeta"] for f in filas]
            ax.barh(nombres, efectivo, color=color(VERDE), label="Efectivo / débito")
            ax.barh(nombres, tarjeta, left=efectivo, color=color(MORADO), label="Tarjeta de crédito")
            ax.xaxis.set_major_formatter(FuncFormatter(_pesos_corto))
            ax.legend(loc="lower right", fontsize=8, frameon=False, labelcolor=texto)
        self._terminar()

    def proyeccion(self, datos: dict[str, dict[str, int]], ingreso_mensual: int) -> None:
        ax, texto = self._preparar()
        ax.set_title("¿Cuándo termino de pagar? (próximos 12 meses)", loc="left", fontsize=12, fontweight="bold")
        periodos = list(datos)
        productos = sorted({p for fila in datos.values() for p in fila})
        if not productos:
            self._vacio(ax, texto, "No hay cuotas pendientes")
        else:
            etiquetas = [nombre_periodo(p) for p in periodos]
            base = [0] * len(periodos)
            for i, prod in enumerate(productos):
                valores = [datos[p].get(prod, 0) for p in periodos]
                ax.bar(etiquetas, valores, bottom=base, color=PALETA_PRODUCTOS[i % len(PALETA_PRODUCTOS)], label=prod)
                base = [b + v for b, v in zip(base, valores)]
            if ingreso_mensual:
                for pct, c in ((0.20, AMARILLO), (0.35, NARANJA), (0.50, ROJO)):
                    ax.axhline(ingreso_mensual * pct, color=color(c), linestyle="--", linewidth=1)
                    ax.text(len(periodos) - 0.5, ingreso_mensual * pct, f" {int(pct * 100)} % del ingreso",
                            color=color(c), fontsize=8, va="bottom", ha="right")
            ax.yaxis.set_major_formatter(FuncFormatter(_pesos_corto))
            ax.tick_params(axis="x", rotation=45)
            ax.legend(fontsize=8, frameon=False, labelcolor=texto)
        self._terminar()

    def historial(self, filas: list[dict]) -> None:
        ax, texto = self._preparar()
        ax.set_title("¿Cuánto me cuesta la deuda? y % del ingreso que se fue en deuda", loc="left",
                     fontsize=12, fontweight="bold")
        if not any(f["costo_deuda"] or f["pagos_credito"] for f in filas):
            self._vacio(ax, texto, "Aún no hay pagos registrados")
            self._terminar()
            return
        etiquetas = [nombre_periodo(f["periodo"]) for f in filas]
        ax.bar(etiquetas, [f["costo_deuda"] for f in filas], color=color(ROJO), label="Intereses y cargos pagados")
        ax.yaxis.set_major_formatter(FuncFormatter(_pesos_corto))
        ax.tick_params(axis="x", rotation=45)
        ax2 = ax.twinx()
        ratios = [f["ratio"] * 100 if f["ratio"] is not None else None for f in filas]
        xs = [i for i, r in enumerate(ratios) if r is not None]
        ax2.plot(xs, [ratios[i] for i in xs], color=color(MORADO), marker="o", label="% del ingreso en deuda")
        ax2.set_ylim(0, max(60, max((r for r in ratios if r is not None), default=0) + 10))
        for pct, c in ((20, AMARILLO), (35, NARANJA), (50, ROJO)):
            ax2.axhline(pct, color=color(c), linestyle=":", linewidth=1)
        ax2.tick_params(colors=texto, labelsize=9)
        ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f} %"))
        for lado in ("top",):
            ax2.spines[lado].set_visible(False)
        lineas = ax.get_legend_handles_labels()
        lineas2 = ax2.get_legend_handles_labels()
        ax.legend(lineas[0] + lineas2[0], lineas[1] + lineas2[1], fontsize=8, frameon=False, labelcolor=texto,
                  loc="upper left")
        self._terminar()

    def entro_salio(self, filas: list[dict]) -> None:
        ax, texto = self._preparar()
        ax.set_title("Entró vs. salió de mi bolsillo", loc="left", fontsize=12, fontweight="bold")
        if not any(f["entro"] or f["salio"] for f in filas):
            self._vacio(ax, texto, "Aún no hay movimientos")
            self._terminar()
            return
        etiquetas = [nombre_periodo(f["periodo"]) for f in filas]
        xs = range(len(filas))
        ax.bar([x - 0.2 for x in xs], [f["entro"] for f in filas], width=0.4, color=color(VERDE), label="Entró")
        ax.bar([x + 0.2 for x in xs], [f["salio"] for f in filas], width=0.4, color=color(NARANJA), label="Salió")
        ax.set_xticks(list(xs), etiquetas, rotation=45)
        ax.yaxis.set_major_formatter(FuncFormatter(_pesos_corto))
        ax.legend(fontsize=8, frameon=False, labelcolor=texto)
        self._terminar()

    def patrimonio(self, filas: list[dict]) -> None:
        """Una sola serie: lo que tienes menos lo que debes al cierre de cada mes."""
        ax, texto = self._preparar()
        ax.set_title("Patrimonio al cierre de cada mes (lo que tienes − lo que debes)", loc="left",
                     fontsize=12, fontweight="bold")
        if not any(f["activos"] or f["deuda"] for f in filas):
            self._vacio(ax, texto, "Aún no hay movimientos")
            self._terminar()
            return
        etiquetas = [nombre_periodo(f["periodo"]) for f in filas]
        valores = [f["patrimonio"] for f in filas]
        xs = list(range(len(filas)))
        ax.axhline(0, color=color(GRIS), linewidth=1)
        ax.plot(xs, valores, color=color(MORADO), linewidth=2, marker="o", markersize=7)
        ultimo = valores[-1]
        ax.annotate(_pesos_corto(ultimo), (xs[-1], ultimo), textcoords="offset points", xytext=(0, 10),
                    ha="center", fontsize=9, color=texto, fontweight="bold")
        ax.set_xticks(xs, etiquetas, rotation=45)
        ax.yaxis.set_major_formatter(FuncFormatter(_pesos_corto))
        ax.grid(axis="y", color=color(GRIS), alpha=0.2, linewidth=0.8)
        self._terminar()
