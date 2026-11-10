"""Servicios y pagos recurrentes (arriendo, luz, internet, celular, seguridad social)."""

from datetime import date

import customtkinter as ctk

from ..dinero import formato
from ..fechas import periodo
from ..repositorio import CupoInsuficiente
from .app import Pagina
from .movimientos import MEDIOS
from .widgets import Campo, Formulario, Tabla, confirmar, error, hoy_texto, pesos


class PaginaServicios(Pagina):
    titulo = "Servicios"

    def construir(self) -> None:
        self.seccion("🧾 Pagos recurrentes",
                     "Lo que pagas todos los meses. El plan los reserva antes de su fecha de vencimiento. "
                     "Al pagarlos, usa «Marcar pagado»: escribes el valor real (puede ser menor o mayor que el "
                     "estimado) y cómo lo pagaste (efectivo/débito o a crédito).")
        botones = self.fila_botones()
        ctk.CTkButton(botones, text="+ Servicio", command=lambda: self._dialogo(None)).pack(side="left")
        ctk.CTkButton(botones, text="Editar", command=self._editar).pack(side="left", padx=8)
        ctk.CTkButton(botones, text="✓ Marcar pagado", command=self._pagar).pack(side="left")
        ctk.CTkButton(botones, text="Desactivar", fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self._desactivar).pack(side="left", padx=8)
        self.total = ctk.CTkLabel(botones, text="")
        self.total.pack(side="right")
        self.tabla = self.bloque(lambda m: Tabla(
            m, [("Servicio", 220, "izq"), ("Categoría", 150, "izq"), ("Vence el día", 100, "centro"),
                ("Valor estimado", 130, "der"), ("Este mes", 200, "izq")], alto=14,
            al_doble_click=lambda _id: self._editar()))

    def refrescar(self) -> None:
        per = periodo(date.today())
        filas = []
        self._servicios = {s["id"]: s for s in self.repo.servicios()}
        for s in self._servicios.values():
            estado = self.repo.estado_servicio(s["id"], per)
            if estado["saldado"]:
                este_mes = f"✓ Pagado {formato(estado['pagado'])}"
            elif estado["pagos"]:
                este_mes = f"Parcial: {formato(estado['pagado'])}, faltan {formato(estado['falta'])}"
            else:
                este_mes = "Pendiente"
            filas.append((s["id"], [s["nombre"], s["categoria"] or "—", s["dia_vencimiento"],
                                    pesos(s["monto_estimado"]), este_mes]))
        self.tabla.cargar(filas)
        self.total.configure(text=f"Total mensual estimado: "
                                  f"{formato(sum(s['monto_estimado'] for s in self._servicios.values()))}")

    def _dialogo(self, s) -> None:
        categorias = [(c["nombre"], c["id"]) for c in self.repo.categorias()]
        servicios_id = next((c["id"] for c in self.repo.categorias() if c["nombre"] == "Servicios"), None)
        campos = [
            Campo("nombre", "Nombre", defecto=s["nombre"] if s else None),
            Campo("categoria", "Categoría", "opcion", categorias,
                  defecto=s["categoria_id"] if s else servicios_id),
            Campo("monto", "Valor estimado al mes", "monto",
                  defecto=formato(s["monto_estimado"], signo=False) if s else None),
            Campo("dia", "Día de vencimiento", "entero", defecto=s["dia_vencimiento"] if s else None),
        ]

        def guardar(v: dict) -> None:
            self.repo.guardar_servicio(s["id"] if s else None, v["nombre"], v["categoria"], v["monto"], v["dia"])
            self.refrescar()

        Formulario(self, "Editar servicio" if s else "Nuevo servicio", campos, guardar)

    def _seleccion(self):
        id_ = self.tabla.seleccionado()
        if id_ is None:
            error(self, "Selecciona un servicio.")
            return None
        return self._servicios[id_]

    def _editar(self) -> None:
        s = self._seleccion()
        if s:
            self._dialogo(s)

    def _pagar(self) -> None:
        s = self._seleccion()
        if not s:
            return
        estado = self.repo.estado_servicio(s["id"], periodo(date.today()))
        sugerido = estado["falta"] or s["monto_estimado"]
        creditos = [(p["nombre"] + (" (cupo)" if p["tipo"] == "cupo" else ""), p["id"])
                    for p in self.repo.productos() if p["tipo"] in ("tarjeta", "cupo")]
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
            Campo("producto", "Tarjeta o cupo", "opcion", creditos, visible_si=("medio", "tarjeta")),
            Campo("cuotas", "Número de cuotas", "entero", defecto=1, visible_si=("medio", "tarjeta")),
        ]

        def guardar(v: dict) -> None:
            args = dict(medio=v["medio"], producto_id=v.get("producto"), num_cuotas=v.get("cuotas"),
                        parcial=bool(v["parcial"]), actualizar_estimado=bool(v.get("actualizar")))
            try:
                self.repo.pagar_servicio(s["id"], v["fecha"], v["monto"], **args)
            except CupoInsuficiente as e:
                if not confirmar(self, f"{e}\n\n¿Registrar el pago de todas formas?"):
                    raise ValueError("Pago no registrado: supera el cupo disponible.") from None
                self.repo.pagar_servicio(s["id"], v["fecha"], v["monto"], permitir_sobrecupo=True, **args)
            self.app.datos_cambiaron()

        Formulario(self, f"Pagar {s['nombre']}", campos, guardar, texto_boton="Registrar pago", ancho=520)

    def _desactivar(self) -> None:
        s = self._seleccion()
        if s and confirmar(self, f"¿Desactivar {s['nombre']}? Ya no se tendrá en cuenta en el plan."):
            self.repo.guardar_servicio(s["id"], s["nombre"], s["categoria_id"], s["monto_estimado"],
                                       s["dia_vencimiento"], activo=False)
            self.refrescar()
