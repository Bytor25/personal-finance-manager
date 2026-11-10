"""Componentes reutilizables de la interfaz: colores, tablas, formularios y tarjetas de resumen."""

import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk
from typing import Any, Callable

import customtkinter as ctk

from ..campos import Campo, hoy_texto, parsear_fecha, pesos  # noqa: F401  (se re-exportan)
from ..campos import convertir
from ..dinero import formato  # noqa: F401

# Colores fijos de la app (claro, oscuro).
VERDE = ("#15803d", "#4ade80")       # Efectivo / bien
MORADO = ("#7c3aed", "#a78bfa")      # Tarjeta
ROJO = ("#b91c1c", "#f87171")
NARANJA = ("#c2410c", "#fb923c")
AMARILLO = ("#a16207", "#facc15")
GRIS = ("#6b7280", "#9ca3af")
FONDO_TARJETA = ("#f3f4f6", "#1f2937")

COLOR_NIVEL = {"sano": VERDE, "moderado": AMARILLO, "alto": NARANJA, "critico": ROJO}
ICONO_NIVEL = {"sano": "🟢", "moderado": "🟡", "alto": "🟠", "critico": "🔴"}

FUENTE_TITULO = ("Segoe UI", 22, "bold")
FUENTE_SUBTITULO = ("Segoe UI", 15, "bold")
FUENTE_CIFRA = ("Segoe UI", 20, "bold")
FUENTE_NORMAL = ("Segoe UI", 13)
FUENTE_PEQUENA = ("Segoe UI", 11)


def color(par: tuple[str, str]) -> str:
    return par[1] if ctk.get_appearance_mode() == "Dark" else par[0]


def error(master, texto: str) -> None:
    messagebox.showerror("Finanzas", texto, parent=master)


def confirmar(master, texto: str) -> bool:
    return messagebox.askyesno("Finanzas", texto, parent=master)


def aplicar_estilo_tablas() -> None:
    oscuro = ctk.get_appearance_mode() == "Dark"
    fondo, texto, encabezado = ("#111827", "#e5e7eb", "#1f2937") if oscuro else ("#ffffff", "#111827", "#e5e7eb")
    estilo = ttk.Style()
    estilo.theme_use("clam")
    estilo.configure("Treeview", background=fondo, fieldbackground=fondo, foreground=texto, rowheight=26,
                     font=FUENTE_PEQUENA, borderwidth=0)
    estilo.configure("Treeview.Heading", background=encabezado, foreground=texto, font=("Segoe UI", 11, "bold"),
                     relief="flat")
    estilo.map("Treeview", background=[("selected", "#7c3aed")], foreground=[("selected", "#ffffff")])


class Tabla(ctk.CTkFrame):
    """Treeview con columnas (titulo, ancho, alineación) y filas asociadas a un id."""

    def __init__(self, master, columnas: list[tuple[str, int, str]], alto: int = 8,
                 al_doble_click: Callable[[Any], None] | None = None):
        super().__init__(master, fg_color="transparent")
        nombres = [f"c{i}" for i in range(len(columnas))]
        self.arbol = ttk.Treeview(self, columns=nombres, show="headings", height=alto, selectmode="browse")
        for nombre, (titulo, ancho, alin) in zip(nombres, columnas):
            self.arbol.heading(nombre, text=titulo, anchor="center")
            self.arbol.column(nombre, width=ancho, anchor={"izq": "w", "der": "e", "centro": "center"}[alin],
                              stretch=True)
        barra = ttk.Scrollbar(self, orient="vertical", command=self.arbol.yview)
        self.arbol.configure(yscrollcommand=barra.set)
        self.arbol.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self._ids: dict[str, Any] = {}
        if al_doble_click:
            self.arbol.bind("<Double-1>", lambda _e: self.seleccionado() is not None and
                            al_doble_click(self.seleccionado()))

    def cargar(self, filas: list[tuple[Any, list]]) -> None:
        self.arbol.delete(*self.arbol.get_children())
        self._ids.clear()
        for id_, valores in filas:
            item = self.arbol.insert("", "end", values=["" if v is None else v for v in valores])
            self._ids[item] = id_

    def seleccionado(self) -> Any:
        sel = self.arbol.selection()
        return self._ids.get(sel[0]) if sel else None


class TarjetaCifra(ctk.CTkFrame):
    """Recuadro con una pregunta, una cifra grande y una nota."""

    def __init__(self, master, titulo: str, color_cifra: tuple[str, str] | None = None):
        super().__init__(master, fg_color=FONDO_TARJETA, corner_radius=12)
        ctk.CTkLabel(self, text=titulo, font=FUENTE_NORMAL, anchor="w").pack(fill="x", padx=14, pady=(12, 0))
        self.cifra = ctk.CTkLabel(self, text="—", font=FUENTE_CIFRA, anchor="w", text_color=color_cifra)
        self.cifra.pack(fill="x", padx=14)
        self.nota = ctk.CTkLabel(self, text="", font=FUENTE_PEQUENA, anchor="w", text_color=GRIS, justify="left",
                                 wraplength=230)
        self.nota.pack(fill="x", padx=14, pady=(0, 12))

    def mostrar(self, cifra: str, nota: str = "", color_cifra: tuple[str, str] | None = None) -> None:
        self.cifra.configure(text=cifra)
        if color_cifra:
            self.cifra.configure(text_color=color_cifra)
        self.nota.configure(text=nota)


class SelectorMes(ctk.CTkFrame):
    def __init__(self, master, al_cambiar: Callable[[str], None]):
        super().__init__(master, fg_color="transparent")
        from ..fechas import nombre_periodo, periodo, periodo_siguiente
        self._nombre, self._sig = nombre_periodo, periodo_siguiente
        self.periodo = periodo(date.today())
        self.al_cambiar = al_cambiar
        ctk.CTkButton(self, text="◀", width=32, command=lambda: self._mover(-1)).pack(side="left")
        self.etiqueta = ctk.CTkLabel(self, text="", width=110, font=FUENTE_SUBTITULO)
        self.etiqueta.pack(side="left", padx=6)
        ctk.CTkButton(self, text="▶", width=32, command=lambda: self._mover(1)).pack(side="left")
        self.etiqueta.configure(text=self._nombre(self.periodo))

    def _mover(self, n: int) -> None:
        self.periodo = self._sig(self.periodo, n)
        self.etiqueta.configure(text=self._nombre(self.periodo))
        self.al_cambiar(self.periodo)


# ---------------------------------------------------------------- formularios

def escala(ventana) -> float:
    """Escala de Windows (ej. 1,25 con 125 %). CustomTkinter multiplica por ella los tamaños de `geometry()`."""
    try:
        return ctk.ScalingTracker.get_window_scaling(ventana) or 1.0
    except Exception:
        return 1.0


def area_pantalla(ventana) -> tuple[int, int]:
    """Ancho y alto útiles de la pantalla en unidades de `geometry()` (sin la barra de tareas, aprox.)."""
    e = escala(ventana)
    return int(ventana.winfo_screenwidth() * 0.94 / e), int(ventana.winfo_screenheight() * 0.86 / e)


def tamano_ventana(ventana, ancho: int, alto: int, min_ancho: int = 420, min_alto: int = 300) -> None:
    """Tamaño inicial que cabe en la pantalla, centrado, redimensionable y con un mínimo usable."""
    max_ancho, max_alto = area_pantalla(ventana)
    ancho, alto = min(ancho, max_ancho), min(alto, max_alto)
    e = escala(ventana)
    x = max(0, int(ventana.winfo_screenwidth() / e - ancho) // 2)
    y = max(0, int(ventana.winfo_screenheight() * 0.92 / e - alto) // 2)
    ventana.geometry(f"{ancho}x{alto}+{x}+{y}")
    ventana.minsize(min(min_ancho, ancho), min(min_alto, alto))
    ventana.resizable(True, True)


class Formulario(ctk.CTkToplevel):
    """Ventana de formulario. `al_guardar(valores)` puede lanzar ValueError para mostrar un error.

    Los campos van en un área desplazable (rueda del mouse o barra); el mensaje de error y los
    botones quedan siempre visibles abajo. La ventana se puede agrandar o reducir y crece sola
    (sin salirse de la pantalla) cuando aparecen campos nuevos.
    """

    EXTRA = 150  # Alto del título, el mensaje, los botones y los márgenes.

    def __init__(self, master, titulo: str, campos: list[Campo], al_guardar: Callable[[dict], None],
                 texto_boton: str = "Guardar", ancho: int = 460):
        super().__init__(master)
        self.title(titulo)
        self.ancho = ancho
        tamano_ventana(self, ancho, 400, min_ancho=360, min_alto=260)
        self.transient(master.winfo_toplevel())
        self.campos = campos
        self.al_guardar = al_guardar
        self.widgets: dict[str, Any] = {}
        self.filas: dict[str, ctk.CTkFrame] = {}
        self.ayudas: list[ctk.CTkLabel] = []
        self._ajustado_a_mano = False

        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=14, pady=12)
        ctk.CTkLabel(cuerpo, text=titulo, font=FUENTE_SUBTITULO, anchor="w").pack(side="top", fill="x", pady=(0, 6))
        # Botones y mensaje se empacan antes que los campos para que nunca queden fuera de la ventana.
        botones = ctk.CTkFrame(cuerpo, fg_color="transparent")
        botones.pack(side="bottom", fill="x", pady=(8, 0))
        ctk.CTkButton(botones, text=texto_boton, command=self._guardar).pack(side="right")
        ctk.CTkButton(botones, text="Cancelar", fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self.destroy).pack(side="right", padx=8)
        self.mensaje = ctk.CTkLabel(cuerpo, text="", text_color=ROJO, wraplength=ancho - 40, justify="left")
        self.mensaje.pack(side="bottom", fill="x", pady=(6, 0))
        self.contenedor = ctk.CTkScrollableFrame(cuerpo, fg_color="transparent", height=120)
        self.contenedor.pack(side="top", fill="both", expand=True)
        for campo in campos:
            self._crear_campo(campo)
        self._actualizar_visibles()
        self.bind("<Return>", lambda _e: self._guardar())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Configure>", self._al_redimensionar)
        self.after(120, self._enfocar)

    def _alto_necesario(self) -> int:
        """Alto (en unidades de `geometry()`) para ver todos los campos visibles sin desplazarse."""
        self.update_idletasks()
        return int(self.contenedor.winfo_reqheight() / escala(self)) + self.EXTRA

    def _ajustar_alto(self, solo_crecer: bool = False) -> None:
        """Alto suficiente para ver todos los campos, sin pasar del alto de la pantalla."""
        if not self.winfo_exists():
            return
        _, max_alto = area_pantalla(self)
        alto = min(self._alto_necesario(), max_alto)
        e = escala(self)
        actual = self.winfo_height() / e
        if solo_crecer and (alto <= actual or self._ajustado_a_mano):
            return
        self._alto_auto = alto
        self.geometry(f"{max(int(self.winfo_width() / e), 200)}x{alto}")

    def _al_redimensionar(self, evento) -> None:
        if evento.widget is not self:
            return
        # Las ayudas se acomodan al ancho disponible (los eventos llegan en píxeles reales).
        e = escala(self)
        ancho = max(240, int(evento.width / e) - 70)
        if ancho != getattr(self, "_ancho_ayudas", None):
            self._ancho_ayudas = ancho
            for etiqueta in self.ayudas:
                etiqueta.configure(wraplength=ancho)
            self.mensaje.configure(wraplength=ancho)
        alto = evento.height / e
        if getattr(self, "_listo", False) and abs(alto - getattr(self, "_alto_auto", alto)) > 6:
            self._ajustado_a_mano = True  # El usuario cambió el alto: no se vuelve a ajustar solo.

    def _enfocar(self) -> None:
        if not self.winfo_exists():
            return
        self._ajustar_alto()  # Fija `_alto_auto` con el alto pedido (el real llega después en <Configure>).
        self.update_idletasks()
        self._listo = True
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _crear_campo(self, campo: Campo) -> None:
        fila = ctk.CTkFrame(self.contenedor, fg_color="transparent")
        fila.pack(fill="x", pady=3)
        self.filas[campo.clave] = fila
        if campo.tipo == "check":
            var = tk.BooleanVar(value=bool(campo.defecto))
            w = ctk.CTkCheckBox(fila, text=campo.etiqueta, variable=var, command=self._actualizar_visibles)
            w.pack(anchor="w")
            self.widgets[campo.clave] = var
        else:
            ctk.CTkLabel(fila, text=campo.etiqueta + ("" if not campo.opcional else " (opcional)"),
                         anchor="w").pack(fill="x")
            if campo.tipo == "opcion":
                etiquetas = [e for e, _ in campo.opciones]
                w = ctk.CTkComboBox(fila, values=etiquetas, state="readonly",
                                    command=lambda _v: self._actualizar_visibles())
                inicial = next((e for e, v in campo.opciones if v == campo.defecto), etiquetas[0] if etiquetas else "")
                w.set(inicial)
            else:
                w = ctk.CTkEntry(fila)
                if campo.defecto is not None:
                    w.insert(0, str(campo.defecto))
            w.pack(fill="x")
            self.widgets[campo.clave] = w
        if campo.ayuda:
            ayuda = ctk.CTkLabel(fila, text=campo.ayuda, anchor="w", text_color=GRIS, font=FUENTE_PEQUENA,
                                 justify="left", wraplength=self.ancho - 70)
            ayuda.pack(fill="x")
            self.ayudas.append(ayuda)

    def _valor_crudo(self, campo: Campo) -> Any:
        w = self.widgets[campo.clave]
        if campo.tipo == "check":
            return w.get()
        if campo.tipo == "opcion":
            return dict(campo.opciones).get(w.get())
        return w.get().strip()

    def _actualizar_visibles(self) -> None:
        for campo in self.campos:
            if campo.visible_si is None:
                continue
            clave, esperado = campo.visible_si
            otro = next(c for c in self.campos if c.clave == clave)
            valor = self._valor_crudo(otro)
            visible = valor in esperado if isinstance(esperado, tuple) else valor == esperado
            visible = visible and self._es_visible(otro)  # Si el campo que lo controla está oculto, también.
            fila = self.filas[campo.clave]
            if visible and not fila.winfo_manager():
                fila.pack(fill="x", pady=3, after=self._fila_anterior(campo))
            elif not visible and fila.winfo_manager():
                fila.pack_forget()
        if getattr(self, "_listo", False):
            self._ajustar_alto(solo_crecer=True)  # Aparecieron campos: crecer si cabe en la pantalla.

    def _fila_anterior(self, campo: Campo) -> ctk.CTkFrame:
        anterior = None
        for c in self.campos:
            if c is campo:
                break
            if self.filas[c.clave].winfo_manager():
                anterior = self.filas[c.clave]
        return anterior or self.filas[self.campos[0].clave]

    def _es_visible(self, campo: Campo) -> bool:
        return bool(self.filas[campo.clave].winfo_manager())

    def valores(self) -> dict:
        resultado = {}
        for campo in self.campos:
            if not self._es_visible(campo):
                resultado[campo.clave] = None
                continue
            crudo = self._valor_crudo(campo)
            if campo.tipo in ("check", "opcion"):
                resultado[campo.clave] = crudo
                continue
            if crudo == "":
                if campo.opcional:
                    resultado[campo.clave] = None
                    continue
                raise ValueError(f"Completa el campo «{campo.etiqueta}»")
            resultado[campo.clave] = convertir(campo, crudo)
        return resultado

    def _guardar(self) -> None:
        try:
            self.al_guardar(self.valores())
        except ValueError as e:
            self.mensaje.configure(text=str(e))
            return
        self.destroy()
