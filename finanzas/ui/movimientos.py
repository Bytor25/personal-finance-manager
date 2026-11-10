"""Ingresos y compras (un solo formulario de compra para efectivo y tarjeta)."""

import customtkinter as ctk

from ..dinero import formato
from ..fechas import parsear_dias_pago
from ..repositorio import CupoInsuficiente
from .app import Pagina
from .condiciones import campos as campos_condiciones
from .condiciones import leer as leer_condiciones
from .widgets import Campo, Formulario, SelectorMes, Tabla, confirmar, error, hoy_texto, pesos

MEDIOS = {"efectivo": "Efectivo / débito", "tarjeta": "A crédito (tarjeta, Addi, Sistecrédito, almacén)"}
MEDIO_CORTO = {"efectivo": "Efectivo / débito", "tarjeta": "A crédito"}


def dialogo_compra(pagina: Pagina) -> None:
    repo = pagina.repo
    creditos = [(p["nombre"] + (" (cupo)" if p["tipo"] == "cupo" else ""), p["id"])
                for p in repo.productos() if p["tipo"] in ("tarjeta", "cupo")]
    categorias = [(c["nombre"], c["id"]) for c in repo.categorias()]
    medios = [(MEDIOS["efectivo"], "efectivo")] + ([(MEDIOS["tarjeta"], "tarjeta")] if creditos else [])
    campos = [
        Campo("fecha", "Fecha", "fecha", defecto=hoy_texto()),
        Campo("descripcion", "¿Qué compraste?", opcional=True),
        Campo("categoria", "Categoría", "opcion", categorias),
        Campo("monto", "Valor", "monto", ayuda="Ej.: 85.000 o 469.027,32"),
        Campo("medio", "¿Cómo pagaste?", "opcion", medios, defecto="efectivo",
              ayuda="A crédito no sale plata de tu bolsillo: aumenta lo que debes." if creditos else
              "Para comprar a crédito, primero registra la tarjeta o el cupo en «Tarjetas y deudas»."),
        Campo("producto", "Tarjeta o cupo", "opcion", creditos, visible_si=("medio", "tarjeta")),
        Campo("cuotas", "Número de cuotas", "entero", defecto=1, visible_si=("medio", "tarjeta")),
        Campo("tasa", "Tasa E.A. de esta compra (%)", "tasa", opcional=True, visible_si=("medio", "tarjeta"),
              ayuda="Vacío = la tasa de la tarjeta o cupo. Pon 0 si es sin intereses (ej. Addi a 3 cuotas)."),
        Campo("primera", "Fecha de la primera cuota", "fecha", opcional=True, visible_si=("medio", "tarjeta"),
              ayuda="Vacío = automático: tarjeta según la fecha de corte; cupo un mes después de la compra."),
        Campo("cargo", "Cargo fijo por cuota (aval, fianza, plataforma)", "monto", opcional=True,
              visible_si=("medio", "tarjeta")),
        Campo("inicial", "Cuota inicial (pagada de tu bolsillo)", "monto", opcional=True,
              visible_si=("medio", "tarjeta"), ayuda="Se financia el valor menos la cuota inicial."),
        Campo("contado", "Precio de contado", "monto", opcional=True, visible_si=("medio", "tarjeta"),
              ayuda="Si financiado es más caro, pon aquí el precio de contado para medir el sobrecosto."),
        Campo("propias", "Esta compra tiene condiciones propias (Addi, Sistecrédito, almacén…)", "check",
              visible_si=("medio", "tarjeta"),
              ayuda="Registra la oferta que aceptaste: tasa y su modalidad, periodicidad, fianza/aval, seguros, "
                    "mora, orden de pagos. Si no, se usan las condiciones de la tarjeta o cupo."),
    ]
    base = repo.condiciones_producto(creditos[0][1]) if creditos else None
    if base:
        campos += campos_condiciones(base, visible_si=("propias", True))

    def guardar(v: dict) -> None:
        condiciones = None
        if v["medio"] == "tarjeta" and v["propias"]:
            if v["tasa"] is not None or v["cargo"]:
                raise ValueError("Marcaste «condiciones propias»: escribe la tasa y los cargos en esa sección y deja "
                                 "vacíos «Tasa E.A. de esta compra» y «Cargo fijo por cuota».")
            condiciones = leer_condiciones(v, repo.condiciones_producto(v["producto"]))
        datos = dict(tasa_ea=None if condiciones else v["tasa"], primera_cuota=v["primera"],
                     cargo_por_cuota=0 if condiciones else v["cargo"] or 0, condiciones=condiciones,
                     cuota_inicial=v["inicial"] or 0, precio_contado=v["contado"])
        args = (v["fecha"], v["descripcion"] or "", v["categoria"], v["monto"], v["medio"], v["producto"], v["cuotas"])
        try:
            repo.registrar_compra(*args, **datos)
        except CupoInsuficiente as e:
            if not confirmar(pagina, f"{e}\n\n¿Registrar la compra de todas formas?"):
                raise ValueError("Compra no registrada: supera el cupo disponible.") from None
            repo.registrar_compra(*args, **datos, permitir_sobrecupo=True)
        pagina.app.datos_cambiaron()

    Formulario(pagina, "Nueva compra", campos, guardar, ancho=560)


def dialogo_ingreso(pagina: Pagina) -> None:
    repo = pagina.repo
    fuentes = repo.fuentes()
    opciones = [("Sin fuente", None)] + [(f["nombre"] + (" (esperada)" if f["estado"] == "esperada" else ""), f["id"])
                                          for f in fuentes if f["estado"] != "inactiva"]
    activa = next((f for f in fuentes if f["estado"] == "activa"), None)
    sugerido = None
    if activa:
        sugerido = formato(activa["monto_mensual"] // len(parsear_dias_pago(activa["dias_pago"])), signo=False)
    campos = [
        Campo("fecha", "Fecha", "fecha", defecto=hoy_texto()),
        Campo("fuente", "Fuente", "opcion", opciones, defecto=activa["id"] if activa else None),
        Campo("monto", "Valor recibido", "monto", defecto=sugerido),
        Campo("tipo", "Tipo", "opcion", [("Ordinario (sueldo, honorarios)", "ordinario"),
                                         ("Extraordinario (prima, bono, otros)", "extraordinario")]),
        Campo("descripcion", "Descripción", opcional=True),
    ]

    def guardar(v: dict) -> None:
        repo.registrar_ingreso(v["fecha"], v["monto"], v["fuente"], v["tipo"], v["descripcion"] or "")
        pagina.app.datos_cambiaron()

    Formulario(pagina, "Nuevo ingreso", campos, guardar)


class PaginaMovimientos(Pagina):
    titulo = "Ingresos y compras"

    def construir(self) -> None:
        self.selector = SelectorMes(self.encabezado, lambda _p: self.refrescar())
        self.selector.pack(side="right")

        self.seccion("💵 Ingresos", "Cada pago que recibes. Después de registrarlo, ve a «Plan del ingreso».")
        botones = self.fila_botones()
        ctk.CTkButton(botones, text="+ Ingreso", command=lambda: dialogo_ingreso(self)).pack(side="left")
        ctk.CTkButton(botones, text="Eliminar", fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self._eliminar_ingreso).pack(side="left", padx=8)
        self.total_ingresos = ctk.CTkLabel(botones, text="")
        self.total_ingresos.pack(side="right")
        self.t_ingresos = self.bloque(lambda m: Tabla(m, [("Fecha", 100, "centro"), ("Fuente", 180, "izq"),
                                                          ("Tipo", 120, "izq"), ("Descripción", 300, "izq"),
                                                          ("Valor", 130, "der")], alto=6))

        self.seccion("🛒 Compras", "Todo lo que compras, en efectivo o con tarjeta. Las compras con tarjeta crean "
                                  "su cronograma de cuotas automáticamente.")
        botones = self.fila_botones()
        ctk.CTkButton(botones, text="+ Compra", command=lambda: dialogo_compra(self)).pack(side="left")
        ctk.CTkButton(botones, text="Eliminar", fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self._eliminar_compra).pack(side="left", padx=8)
        self.total_compras = ctk.CTkLabel(botones, text="")
        self.total_compras.pack(side="right")
        self.t_compras = self.bloque(lambda m: Tabla(m, [("Fecha", 100, "centro"), ("Descripción", 260, "izq"),
                                                         ("Categoría", 140, "izq"), ("Cómo pagué", 200, "izq"),
                                                         ("Cuotas", 70, "centro"), ("Valor", 130, "der")], alto=12))

    def refrescar(self) -> None:
        per = self.selector.periodo
        ingresos = self.repo.ingresos(per)
        self.t_ingresos.cargar([(i["id"], [i["fecha"], i["fuente"] or "—", i["tipo"].capitalize(),
                                           i["descripcion"], pesos(i["monto"])]) for i in ingresos])
        self.total_ingresos.configure(text=f"Total: {formato(sum(i['monto'] for i in ingresos))}")
        compras = self.repo.compras(per)
        self.t_compras.cargar([(c["id"], [c["fecha"], c["descripcion"], c["categoria"] or "—",
                                          MEDIO_CORTO[c["medio"]] + (f" · {c['producto']}" if c["producto"] else ""),
                                          c["num_cuotas"] or "", pesos(c["monto"])]) for c in compras])
        efectivo = sum(c["monto"] for c in compras if c["medio"] == "efectivo")
        tarjeta = sum(c["monto"] for c in compras if c["medio"] == "tarjeta")
        self.total_compras.configure(text=f"Efectivo/débito: {formato(efectivo)}   ·   A crédito: {formato(tarjeta)}")

    def _eliminar_ingreso(self) -> None:
        id_ = self.t_ingresos.seleccionado()
        if id_ is None:
            return error(self, "Selecciona un ingreso.")
        if confirmar(self, "¿Eliminar este ingreso?"):
            self.repo.eliminar_ingreso(id_)
            self.refrescar()

    def _eliminar_compra(self) -> None:
        id_ = self.t_compras.seleccionado()
        if id_ is None:
            return error(self, "Selecciona una compra.")
        if confirmar(self, "¿Eliminar esta compra? Si fue con tarjeta, también se elimina su cronograma."):
            try:
                self.repo.eliminar_compra(id_)
            except ValueError as e:
                return error(self, str(e))
            self.refrescar()
