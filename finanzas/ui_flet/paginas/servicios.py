"""Servicios y pagos recurrentes (arriendo, luz, internet, celular, seguridad social)."""

from datetime import date

import flet as ft

from ...campos import Campo, hoy_texto, pesos
from ...dinero import formato
from ...fechas import periodo
from ...repositorio import CupoInsuficiente
from ..componentes import Pagina, Tabla, barra_botones, boton, requiere, seccion, texto
from ..tema import NARANJA, VERDE
from .movimientos import MEDIOS, opciones_credito


class PaginaServicios(Pagina):
    titulo = "Servicios"

    def construir(self) -> None:
        self.total = texto("", 13, ft.FontWeight.W_600)
        self.tabla = Tabla([("Servicio", "izq"), ("Categoría", "izq"), ("Vence el día", "centro"),
                            ("Valor estimado", "der"), ("Este mes", "izq")],
                           al_doble_clic=lambda _id: self._pagar(), vacio="Aún no tienes servicios registrados.")
        self.agregar(seccion(
            "🧾 Pagos recurrentes",
            barra_botones(boton("Servicio", lambda _e: self._dialogo(None), ft.Icons.ADD),
                          boton("Marcar pagado", self._pagar, ft.Icons.CHECK, color=VERDE),
                          boton("Editar", self._editar, ft.Icons.EDIT_OUTLINED, "tonal"),
                          boton("Desactivar", self._desactivar, ft.Icons.PAUSE_CIRCLE_OUTLINE, "borde"),
                          derecha=self.total),
            self.tabla.vista,
            explicacion="Lo que pagas todos los meses. El plan los reserva antes de su fecha de vencimiento. Al "
                        "pagarlos, usa «Marcar pagado»: escribes el valor real (puede ser menor o mayor que el "
                        "estimado) y cómo lo pagaste (efectivo/débito o a crédito). Doble clic en una fila = pagar."))

    def refrescar(self) -> None:
        per = periodo(date.today())
        filas = []
        self._servicios = {s["id"]: s for s in self.repo.servicios()}
        for s in self._servicios.values():
            estado = self.repo.estado_servicio(s["id"], per)
            if estado["saldado"]:
                este_mes = (f"✓ Pagado {formato(estado['pagado'])}", VERDE)
            elif estado["pagos"]:
                este_mes = (f"Parcial: {formato(estado['pagado'])}, faltan {formato(estado['falta'])}", NARANJA)
            else:
                este_mes = "Pendiente"
            filas.append((s["id"], [s["nombre"], s["categoria"] or "—", s["dia_vencimiento"],
                                    pesos(s["monto_estimado"]), este_mes]))
        self.tabla.cargar(filas)
        self.total.value = f"Total mensual estimado: {formato(sum(s['monto_estimado'] for s in self._servicios.values()))}"

    def _dialogo(self, s) -> None:
        categorias = [(c["nombre"], c["id"]) for c in self.repo.categorias()]
        servicios_id = next((c["id"] for c in self.repo.categorias() if c["nombre"] == "Servicios"), None)
        campos = [
            Campo("nombre", "Nombre", defecto=s["nombre"] if s else None),
            Campo("categoria", "Categoría", "opcion", categorias, defecto=s["categoria_id"] if s else servicios_id),
            Campo("monto", "Valor estimado al mes", "monto",
                  defecto=formato(s["monto_estimado"], signo=False) if s else None),
            Campo("dia", "Día de vencimiento", "entero", defecto=s["dia_vencimiento"] if s else None),
        ]

        def guardar(v: dict) -> None:
            self.repo.guardar_servicio(s["id"] if s else None, v["nombre"], v["categoria"], v["monto"], v["dia"])
            self.cambio()

        self.formulario("Editar servicio" if s else "Nuevo servicio", campos, guardar)

    def _seleccion(self):
        id_ = requiere(self.tabla, self, "Selecciona un servicio en la tabla.")
        return self._servicios[id_] if id_ is not None else None

    def _editar(self, _e=None) -> None:
        s = self._seleccion()
        if s:
            self._dialogo(s)

    def _pagar(self, _e=None) -> None:
        s = self._seleccion()
        if not s:
            return
        estado = self.repo.estado_servicio(s["id"], periodo(date.today()))
        sugerido = estado["falta"] or s["monto_estimado"]
        reserva = self.repo.saldo_reserva()
        creditos = opciones_credito(self.repo)
        medios = [(MEDIOS["efectivo"], "efectivo")] + ([(MEDIOS["tarjeta"], "tarjeta")] if creditos else [])
        campos = [
            Campo("fecha", "Fecha de pago", "fecha", defecto=hoy_texto()),
            Campo("monto", "Valor pagado", "monto", defecto=formato(sugerido, signo=False),
                  ayuda=f"Estimado: {formato(s['monto_estimado'])}. Escribe lo que realmente pagaste, "
                        "aunque sea menos o más."),
            Campo("parcial", "Es un pago parcial (todavía me falta pagar una parte este mes)", "check",
                  ayuda="Si lo marcas, el resto sigue pendiente en el plan. Si no, el servicio queda pagado "
                        "este mes aunque el valor sea distinto al estimado."),
            Campo("actualizar", "Usar este valor como nuevo estimado para los próximos meses", "check",
                  visible_si=("parcial", False)),
            Campo("medio", "¿Cómo pagaste?", "opcion", medios, defecto="efectivo",
                  ayuda="A crédito no sale plata de tu bolsillo hoy: queda como deuda en la tarjeta o cupo."
                  if creditos else "Para pagar a crédito, primero registra la tarjeta en «Tarjetas y deudas»."),
            Campo("reserva", "Lo pagué con la plata de la reserva (Cajita)", "check",
                  defecto=reserva >= sugerido > 0, visible_si=("medio", "efectivo"),
                  ayuda=f"Saldo de la reserva: {formato(max(0, reserva))}. La reserva guarda los servicios del mes "
                        "siguiente: si de ahí salió la plata, márcalo para que no se descuente de tu disponible."),
            Campo("producto", "Tarjeta o cupo", "opcion", creditos, visible_si=("medio", "tarjeta")),
            Campo("cuotas", "Número de cuotas", "entero", defecto=1, visible_si=("medio", "tarjeta")),
        ]

        async def guardar(v: dict) -> None:
            args = dict(medio=v["medio"], producto_id=v.get("producto"), num_cuotas=v.get("cuotas"),
                        parcial=bool(v["parcial"]), actualizar_estimado=bool(v.get("actualizar")),
                        desde_reserva=bool(v.get("reserva")))
            try:
                self.repo.pagar_servicio(s["id"], v["fecha"], v["monto"], **args)
            except CupoInsuficiente as e:
                if not await self.confirmar(f"{e}\n\n¿Registrar el pago de todas formas?", titulo="Supera el cupo",
                                            si="Registrar igual"):
                    raise ValueError("Pago no registrado: supera el cupo disponible.") from None
                self.repo.pagar_servicio(s["id"], v["fecha"], v["monto"], permitir_sobrecupo=True, **args)
            self.cambio()
            self.notificar(f"Pago de {s['nombre']} registrado")

        self.formulario(f"Pagar {s['nombre']}", campos, guardar, texto_boton="Registrar pago", ancho=520)

    async def _desactivar(self, _e=None) -> None:
        s = self._seleccion()
        if s and await self.confirmar(f"¿Desactivar {s['nombre']}? Ya no se tendrá en cuenta en el plan.",
                                      si="Desactivar"):
            self.repo.guardar_servicio(s["id"], s["nombre"], s["categoria_id"], s["monto_estimado"],
                                       s["dia_vencimiento"], activo=False)
            self.cambio()
