"""Ingresos y compras (un solo formulario de compra para efectivo y tarjeta)."""

import flet as ft

from ...campos import Campo, hoy_texto, pesos
from ...dinero import formato
from ...fechas import parsear_dias_pago
from ...repositorio import CupoInsuficiente
from ...ui.condiciones import campos as campos_condiciones
from ...ui.condiciones import leer as leer_condiciones
from ..componentes import Pagina, SelectorMes, Tabla, barra_botones, boton, requiere, seccion, texto
from ..tema import MORADO, VERDE

MEDIOS = {"efectivo": "Efectivo / débito", "tarjeta": "A crédito (tarjeta, Addi, Sistecrédito, almacén)"}
MEDIO_CORTO = {"efectivo": "Efectivo / débito", "tarjeta": "A crédito"}


def opciones_credito(repo) -> list[tuple[str, int]]:
    return [(p["nombre"] + (" (cupo)" if p["tipo"] == "cupo" else ""), p["id"])
            for p in repo.productos() if p["tipo"] in ("tarjeta", "cupo")]


def dialogo_compra(pagina: Pagina) -> None:
    repo = pagina.repo
    creditos = opciones_credito(repo)
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

    async def guardar(v: dict) -> None:
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
            if not await pagina.confirmar(f"{e}\n\n¿Registrar la compra de todas formas?", titulo="Supera el cupo",
                                          si="Registrar igual"):
                raise ValueError("Compra no registrada: supera el cupo disponible.") from None
            repo.registrar_compra(*args, **datos, permitir_sobrecupo=True)
        pagina.cambio()
        pagina.notificar("Compra registrada")

    pagina.formulario("Nueva compra", campos, guardar, ancho=580)


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
        pagina.cambio()
        pagina.notificar("Ingreso registrado. Ve a «Plan del ingreso» para repartirlo.")

    pagina.formulario("Nuevo ingreso", campos, guardar)


class PaginaMovimientos(Pagina):
    titulo = "Ingresos y compras"

    def construir(self) -> None:
        self.selector = SelectorMes(lambda _p: self.app.datos_cambiaron())
        self.acciones.controls.append(self.selector.vista)

        self.total_ingresos = texto("", 13, ft.FontWeight.W_600, VERDE)
        self.t_ingresos = Tabla([("Fecha", "centro"), ("Fuente", "izq"), ("Tipo", "izq"), ("Descripción", "izq"),
                                 ("Valor", "der")], vacio="No hay ingresos registrados este mes.")
        self.total_compras = texto("", 13, ft.FontWeight.W_600)
        self.t_compras = Tabla([("Fecha", "centro"), ("Descripción", "izq"), ("Categoría", "izq"),
                                ("Cómo pagué", "izq"), ("Cuotas", "centro"), ("Valor", "der")],
                               vacio="No hay compras registradas este mes.")
        self.agregar(
            seccion("💵 Ingresos",
                    barra_botones(boton("Ingreso", lambda _e: dialogo_ingreso(self), ft.Icons.ADD),
                                  boton("Eliminar", self._eliminar_ingreso, ft.Icons.DELETE_OUTLINE, "borde"),
                                  derecha=self.total_ingresos),
                    self.t_ingresos.vista,
                    explicacion="Cada pago que recibes. Después de registrarlo, ve a «Plan del ingreso»."),
            seccion("🛒 Compras",
                    barra_botones(boton("Compra", lambda _e: dialogo_compra(self), ft.Icons.ADD_SHOPPING_CART),
                                  boton("Eliminar", self._eliminar_compra, ft.Icons.DELETE_OUTLINE, "borde"),
                                  derecha=self.total_compras),
                    self.t_compras.vista,
                    explicacion="Todo lo que compras, en efectivo o con tarjeta. Las compras con tarjeta crean su "
                                "cronograma de cuotas automáticamente."),
        )

    def refrescar(self) -> None:
        per = self.selector.periodo
        ingresos = self.repo.ingresos(per)
        self.t_ingresos.cargar([(i["id"], [i["fecha"], i["fuente"] or "—", i["tipo"].capitalize(),
                                           i["descripcion"], pesos(i["monto"])]) for i in ingresos])
        self.total_ingresos.value = f"Total: {formato(sum(i['monto'] for i in ingresos))}"
        compras = self.repo.compras(per)
        self.t_compras.cargar([(c["id"], [c["fecha"], c["descripcion"], c["categoria"] or "—",
                                          (MEDIO_CORTO[c["medio"]] + (f" · {c['producto']}" if c["producto"] else ""),
                                           MORADO if c["medio"] == "tarjeta" else None),
                                          c["num_cuotas"] or "", pesos(c["monto"])]) for c in compras])
        efectivo = sum(c["monto"] for c in compras if c["medio"] == "efectivo")
        tarjeta = sum(c["monto"] for c in compras if c["medio"] == "tarjeta")
        self.total_compras.value = f"Efectivo/débito: {formato(efectivo)}  ·  A crédito: {formato(tarjeta)}"

    async def _eliminar_ingreso(self, _e=None) -> None:
        id_ = requiere(self.t_ingresos, self, "Selecciona un ingreso en la tabla.")
        if id_ is not None and await self.confirmar("¿Eliminar este ingreso?", si="Eliminar", peligro=True):
            self.repo.eliminar_ingreso(id_)
            self.cambio()

    async def _eliminar_compra(self, _e=None) -> None:
        id_ = requiere(self.t_compras, self, "Selecciona una compra en la tabla.")
        if id_ is not None and await self.confirmar(
                "¿Eliminar esta compra? Si fue con tarjeta, también se elimina su cronograma.", si="Eliminar",
                peligro=True):
            try:
                self.repo.eliminar_compra(id_)
            except ValueError as e:
                return self.error(str(e))
            self.cambio()
