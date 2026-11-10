"""Acceso a datos y reglas de negocio sobre la base SQLite.

Une la base de datos con los cálculos puros de `credito` y `plan`.
"""

import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta

from . import condiciones as cond_mod
from . import credito
from .credito import ABONO_CONSTANTE, CUOTA_FIJA, CuotaPendiente
from .dinero import formato
from .fechas import (FIN_DE_MES, fecha_con_dia, fecha_pago_correspondiente, fecha_primera_cuota, fechas_pago_en_mes,
                     fin_periodo,
                     inicio_periodo, parsear_dias_pago, periodo, periodo_siguiente, proxima_fecha_pago,
                     sumar_meses)
from .ahorro import (PESO_PRIORIDAD, Asignacion, CapacidadAhorro, EntradaAhorro, Meta, capacidad_ahorro,
                     repartir)
from .plan import NIVELES, ConfigPlan, EntradaPlan, Vencimiento, nivel_endeudamiento, ratio_endeudamiento

SIGNO_RESERVA = {"aporte": 1, "rendimiento": 1, "uso": -1, "retiro": -1}
TIPOS_PRODUCTO = ("tarjeta", "cupo", "prestamo")


def _iso(f: date | None) -> str | None:
    return f.isoformat() if f else None


def _fecha(texto: str) -> date:
    return date.fromisoformat(texto)


# Componente de la cuota -> columna de lo pagado.
PAGADO = {"capital": "pagado_capital", "interes": "pagado_interes", "otros": "pagado_otros",
          "mora": "pagado_mora", "cobranza": "pagado_cobranza"}
# Pagos que no salen del bolsillo en el momento en que se registran.
TIPOS_NO_PAGO = ("devolucion", "saldo_favor")


class CupoInsuficiente(ValueError):
    """La compra supera el cupo disponible del producto (se puede registrar igual si el usuario confirma)."""


def _detalle(c) -> dict[str, int]:
    """Cargos de una cuota por nombre; las cuotas antiguas sin detalle muestran «Cargos»."""
    if c["detalle"]:
        return json.loads(c["detalle"])
    return {"Cargos": c["otros"]} if c["otros"] else {}


def _tramos_mensuales(desde: date, hasta: date) -> list[tuple[date, date]]:
    """Parte [desde, hasta) en tramos que no cruzan un cambio de mes (la usura cambia cada mes)."""
    tramos = []
    while desde < hasta:
        corte = min(hasta, sumar_meses(desde.replace(day=1), 1, 1))
        tramos.append((desde, corte))
        desde = corte
    return tramos


def metodo_producto(tipo: str) -> str:
    """Tarjetas: capital fijo + intereses. Cupos y préstamos: cuota fija."""
    return ABONO_CONSTANTE if tipo == "tarjeta" else CUOTA_FIJA


class Repositorio:
    def __init__(self, con: sqlite3.Connection):
        self.con = con

    def _uno(self, sql: str, params=()) -> sqlite3.Row | None:
        return self.con.execute(sql, params).fetchone()

    def _todos(self, sql: str, params=()) -> list[sqlite3.Row]:
        return self.con.execute(sql, params).fetchall()

    def _valor(self, sql: str, params=()) -> int:
        fila = self.con.execute(sql, params).fetchone()
        return (fila[0] or 0) if fila else 0

    def _cambio(self, entidad: str, entidad_id: int | None, accion: str, antes=None, despues=None) -> None:
        """Deja constancia de un cambio (se llama dentro de la transacción de la operación)."""
        def texto(v):
            if v is None:
                return None
            if isinstance(v, sqlite3.Row):
                v = dict(v)
            return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
        self.con.execute("INSERT INTO historial_cambios (creado, entidad, entidad_id, accion, antes, despues) "
                         "VALUES (?, ?, ?, ?, ?, ?)", (datetime.now().isoformat(timespec="seconds"), entidad,
                                                       entidad_id, accion, texto(antes), texto(despues)))

    def historial_cambios(self, limite: int = 500) -> list[sqlite3.Row]:
        return self._todos("SELECT * FROM historial_cambios ORDER BY id DESC LIMIT ?", (limite,))

    # ============================================================ configuración

    def config(self) -> dict[str, str]:
        return {f["clave"]: f["valor"] for f in self._todos("SELECT clave, valor FROM configuracion")}

    def guardar_config(self, valores: dict[str, str]) -> None:
        with self.con:
            for clave, valor in valores.items():
                self.con.execute("INSERT INTO configuracion (clave, valor) VALUES (?, ?) "
                                 "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor", (clave, str(valor)))

    def config_num(self, clave: str, defecto: float = 0.0) -> float:
        try:
            return float(self.config().get(clave, defecto) or defecto)
        except ValueError:
            return defecto

    def config_plan(self) -> ConfigPlan:
        c = self.config()
        umbrales = tuple(float(c[f"umbral_{k}"]) / 100 for k in ("sano", "moderado", "alto"))
        reparto = {}
        for nivel in NIVELES:
            partes = [float(x) / 100 for x in c[f"reparto_{nivel}"].split(",")]
            reparto[nivel] = tuple(partes)
        return ConfigPlan(umbrales=umbrales, reparto=reparto)

    # ============================================================ categorías

    def categorias(self, solo_activas: bool = True) -> list[sqlite3.Row]:
        filtro = "WHERE activa = 1" if solo_activas else ""
        return self._todos(f"SELECT * FROM categorias {filtro} ORDER BY nombre")

    def guardar_categoria(self, id_: int | None, nombre: str, grupo: str, activa: bool = True) -> None:
        nombre = nombre.strip()
        if not nombre:
            raise ValueError("El nombre de la categoría es obligatorio")
        with self.con:
            if id_ is None:
                self.con.execute("INSERT INTO categorias (nombre, grupo) VALUES (?, ?)", (nombre, grupo))
            else:
                self.con.execute("UPDATE categorias SET nombre = ?, grupo = ?, activa = ? WHERE id = ?",
                                 (nombre, grupo, int(activa), id_))

    # ============================================================ ingresos

    def fuentes(self, estado: str | None = None) -> list[sqlite3.Row]:
        if estado:
            return self._todos("SELECT * FROM fuentes_ingreso WHERE estado = ? ORDER BY nombre", (estado,))
        return self._todos("SELECT * FROM fuentes_ingreso ORDER BY estado, nombre")

    def guardar_fuente(self, id_: int | None, nombre: str, monto_mensual: int, dias_pago: str,
                       variable: bool, estado: str) -> None:
        if not nombre.strip():
            raise ValueError("El nombre es obligatorio")
        parsear_dias_pago(dias_pago)  # Valida.
        with self.con:
            if id_ is None:
                self.con.execute("INSERT INTO fuentes_ingreso (nombre, monto_mensual, dias_pago, variable, estado) "
                                 "VALUES (?, ?, ?, ?, ?)", (nombre.strip(), monto_mensual, dias_pago,
                                                            int(variable), estado))
            else:
                self.con.execute("UPDATE fuentes_ingreso SET nombre = ?, monto_mensual = ?, dias_pago = ?, "
                                 "variable = ?, estado = ? WHERE id = ?",
                                 (nombre.strip(), monto_mensual, dias_pago, int(variable), estado, id_))

    def eliminar_fuente(self, id_: int) -> None:
        with self.con:
            self.con.execute("DELETE FROM fuentes_ingreso WHERE id = ?", (id_,))

    def dias_pago(self) -> list[int]:
        dias: set[int] = set()
        for f in self.fuentes("activa"):
            dias.update(parsear_dias_pago(f["dias_pago"]))
        return sorted(dias, key=lambda d: 99 if d == FIN_DE_MES else d) or [FIN_DE_MES]

    def ingresos_por_mes(self) -> int:
        return len(self.dias_pago())

    def _promedio_ingresos(self, hoy: date, fuente_id: int | None = None) -> int:
        """Promedio mensual de los últimos 3 meses completos con ingresos."""
        totales = []
        per = periodo(hoy)
        for k in range(1, 7):
            p = periodo_siguiente(per, -k)
            sql = "SELECT SUM(monto) FROM ingresos WHERE substr(fecha, 1, 7) = ? AND tipo = 'ordinario'"
            params: tuple = (p,)
            if fuente_id is not None:
                sql += " AND fuente_id = ?"
                params += (fuente_id,)
            total = self._valor(sql, params)
            if total:
                totales.append(total)
            if len(totales) == 3:
                break
        return round(sum(totales) / len(totales)) if totales else 0

    def ingreso_mensual_estimado(self, hoy: date | None = None, incluir_esperadas: bool = False) -> int:
        hoy = hoy or date.today()
        estados = ("activa", "esperada") if incluir_esperadas else ("activa",)
        fuentes = [f for f in self.fuentes() if f["estado"] in estados]
        if not fuentes:
            return self._promedio_ingresos(hoy)
        total = 0
        for f in fuentes:
            promedio = self._promedio_ingresos(hoy, f["id"]) if f["variable"] else 0
            total += promedio or f["monto_mensual"]
        return total

    def registrar_ingreso(self, fecha: date, monto: int, fuente_id: int | None = None,
                          tipo: str = "ordinario", descripcion: str = "") -> int:
        if monto <= 0:
            raise ValueError("El monto debe ser mayor que cero")
        with self.con:
            cur = self.con.execute("INSERT INTO ingresos (fecha, fuente_id, monto, tipo, descripcion) "
                                   "VALUES (?, ?, ?, ?, ?)", (_iso(fecha), fuente_id, monto, tipo, descripcion))
        return cur.lastrowid

    def ingresos(self, per: str | None = None) -> list[sqlite3.Row]:
        sql = ("SELECT i.*, f.nombre AS fuente FROM ingresos i LEFT JOIN fuentes_ingreso f ON f.id = i.fuente_id")
        if per:
            return self._todos(sql + " WHERE substr(i.fecha, 1, 7) = ? ORDER BY i.fecha DESC, i.id DESC", (per,))
        return self._todos(sql + " ORDER BY i.fecha DESC, i.id DESC")

    def ingreso(self, id_: int) -> sqlite3.Row | None:
        return self._uno("SELECT * FROM ingresos WHERE id = ?", (id_,))

    def eliminar_ingreso(self, id_: int) -> None:
        with self.con:
            self._cambio("ingreso", id_, "eliminar", self.ingreso(id_))
            self.con.execute("DELETE FROM ingresos WHERE id = ?", (id_,))

    # ============================================================ productos de crédito

    def productos(self, solo_activos: bool = True) -> list[sqlite3.Row]:
        filtro = "WHERE activo = 1" if solo_activos else ""
        return self._todos(f"SELECT * FROM productos_credito {filtro} ORDER BY tipo, nombre")

    def producto(self, id_: int) -> sqlite3.Row:
        fila = self._uno("SELECT * FROM productos_credito WHERE id = ?", (id_,))
        if fila is None:
            raise ValueError("La tarjeta o crédito no existe")
        return fila

    def guardar_producto(self, id_: int | None, nombre: str, entidad: str, tipo: str, cupo: int,
                         tasa_ea: float, dia_corte: int, dia_pago: int, cuota_manejo: int,
                         interes_una_cuota: bool, activo: bool = True) -> int:
        if not nombre.strip():
            raise ValueError("El nombre es obligatorio")
        if tipo not in TIPOS_PRODUCTO:
            raise ValueError(f"Tipo de producto inválido: {tipo}")
        if not (1 <= dia_corte <= 31 and 1 <= dia_pago <= 31):
            raise ValueError("Los días de corte y pago deben estar entre 1 y 31")
        datos = (nombre.strip(), entidad.strip(), tipo, cupo, tasa_ea, dia_corte, dia_pago, cuota_manejo,
                 int(interes_una_cuota), int(activo))
        with self.con:
            if id_ is None:
                cur = self.con.execute(
                    "INSERT INTO productos_credito (nombre, entidad, tipo, cupo, tasa_ea, dia_corte, dia_pago, "
                    "cuota_manejo, interes_una_cuota, activo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", datos)
                return cur.lastrowid
            antes = self._uno("SELECT * FROM productos_credito WHERE id = ?", (id_,))
            self.con.execute(
                "UPDATE productos_credito SET nombre = ?, entidad = ?, tipo = ?, cupo = ?, tasa_ea = ?, "
                "dia_corte = ?, dia_pago = ?, cuota_manejo = ?, interes_una_cuota = ?, activo = ? WHERE id = ?",
                datos + (id_,))
            fila = self._uno("SELECT condiciones FROM productos_credito WHERE id = ?", (id_,))
            if fila["condiciones"]:  # La plantilla sigue la tasa editada en el producto.
                cond = cond_mod.cargar(fila["condiciones"], cond_mod.por_defecto(tipo, tasa_ea))
                if abs(cond_mod.tasa_ea(cond) - tasa_ea) > 1e-9:
                    cond["tasa"] = {"valor": tasa_ea, "modalidad": "EA"}
                    self.con.execute("UPDATE productos_credito SET condiciones = ? WHERE id = ?",
                                     (cond_mod.a_texto(cond), id_))
            despues = self._uno("SELECT * FROM productos_credito WHERE id = ?", (id_,))
            if antes is not None and dict(antes) != dict(despues):
                cambios = {k: (antes[k], despues[k]) for k in despues.keys() if antes[k] != despues[k]}
                self._cambio("producto", id_, "editar", {k: v[0] for k, v in cambios.items()},
                             {k: v[1] for k, v in cambios.items()})
            return id_

    def condiciones_producto(self, producto_id: int) -> dict:
        """Plantilla de condiciones del producto (o las mínimas a partir de su tasa)."""
        p = self.producto(producto_id)
        return cond_mod.cargar(p["condiciones"], cond_mod.por_defecto(p["tipo"], p["tasa_ea"]))

    def guardar_condiciones_producto(self, producto_id: int, cond: dict) -> None:
        """Guarda la plantilla. No modifica los créditos existentes: cada uno conserva su fotografía."""
        cond = cond_mod.validar(cond)
        cond["vigente_desde"] = cond.get("vigente_desde") or date.today().isoformat()
        with self.con:
            antes = self._uno("SELECT condiciones FROM productos_credito WHERE id = ?", (producto_id,))
            self._cambio("condiciones_producto", producto_id, "editar", antes["condiciones"] if antes else None,
                         cond_mod.a_texto(cond))
            self.con.execute("UPDATE productos_credito SET condiciones = ?, tasa_ea = ? WHERE id = ?",
                             (cond_mod.a_texto(cond), cond_mod.tasa_ea(cond), producto_id))

    def primera_fecha_pago(self, producto_id: int, desde: date) -> date:
        """Fecha límite del primer pago para una deuda que nace en `desde`.

        Tarjeta: según el corte. Cupo (Addi, Sistecrédito, almacenes): un mes después
        de la compra. Préstamo: el siguiente día de pago.
        """
        p = self.producto(producto_id)
        if p["tipo"] == "tarjeta":
            return fecha_primera_cuota(desde, p["dia_corte"], p["dia_pago"])
        if p["tipo"] == "cupo":
            return sumar_meses(desde, 1)
        siguiente = fecha_con_dia(desde.year, desde.month, p["dia_pago"])
        return siguiente if siguiente > desde else sumar_meses(siguiente, 1, p["dia_pago"])

    def _dia_ancla(self, producto_id: int, primera: date, preferido: int | None = None) -> int:
        """Día de pago pactado para ubicar las cuotas mes a mes a partir de `primera`.

        Se usa `preferido` (ej. el día de la compra en un cupo) o el día de pago del
        producto si son coherentes con `primera` (28-feb es coherente con el 30 o 31);
        si no, el día de `primera`.
        """
        p = self.producto(producto_id)
        candidatos = [preferido] if preferido else []
        if p["tipo"] != "cupo":
            candidatos.append(p["dia_pago"])
        for dia in candidatos:
            if dia and fecha_con_dia(primera.year, primera.month, dia) == primera:
                return dia
        return primera.day

    def proxima_fecha_cobro(self, producto_id: int, hoy: date) -> date | None:
        """Próximo día límite de pago (hoy incluido) para cuotas que ya vienen corriendo.

        En cupos cada compra vence en su propio día: no hay una fecha común (None).
        """
        p = self.producto(producto_id)
        if p["tipo"] == "cupo":
            return None
        fecha = fecha_con_dia(hoy.year, hoy.month, p["dia_pago"])
        return fecha if fecha >= hoy else sumar_meses(fecha, 1, p["dia_pago"])

    # ============================================================ servicios

    def servicios(self, solo_activos: bool = True) -> list[sqlite3.Row]:
        filtro = "WHERE s.activo = 1" if solo_activos else ""
        return self._todos("SELECT s.*, c.nombre AS categoria FROM servicios s "
                           f"LEFT JOIN categorias c ON c.id = s.categoria_id {filtro} "
                           "ORDER BY s.dia_vencimiento, s.nombre")

    def guardar_servicio(self, id_: int | None, nombre: str, categoria_id: int | None, monto: int,
                         dia_vencimiento: int, activo: bool = True) -> None:
        if not nombre.strip():
            raise ValueError("El nombre es obligatorio")
        if not 1 <= dia_vencimiento <= 31:
            raise ValueError("El día de vencimiento debe estar entre 1 y 31")
        with self.con:
            if id_ is None:
                self.con.execute("INSERT INTO servicios (nombre, categoria_id, monto_estimado, dia_vencimiento) "
                                 "VALUES (?, ?, ?, ?)", (nombre.strip(), categoria_id, monto, dia_vencimiento))
            else:
                self.con.execute("UPDATE servicios SET nombre = ?, categoria_id = ?, monto_estimado = ?, "
                                 "dia_vencimiento = ?, activo = ? WHERE id = ?",
                                 (nombre.strip(), categoria_id, monto, dia_vencimiento, int(activo), id_))

    def servicio_pagado_en(self, servicio_id: int, per: str) -> int:
        return self._valor("SELECT SUM(monto) FROM compras WHERE servicio_id = ? AND substr(fecha, 1, 7) = ?",
                           (servicio_id, per))

    def estado_servicio(self, servicio_id: int, per: str) -> dict:
        """Lo pagado de un servicio en un mes y si ya quedó saldado.

        Queda saldado con cualquier pago que no se haya marcado como parcial (aunque el
        valor sea menor o mayor que el estimado: la factura pudo cambiar). Si todos los
        pagos fueron parciales, falta el estimado menos lo pagado.
        """
        fila = self._uno("SELECT COALESCE(SUM(monto), 0) AS pagado, COUNT(*) AS pagos, "
                         "COALESCE(SUM(pago_parcial = 0), 0) AS completos FROM compras "
                         "WHERE servicio_id = ? AND substr(fecha, 1, 7) = ?", (servicio_id, per))
        estimado = self._uno("SELECT monto_estimado FROM servicios WHERE id = ?", (servicio_id,))["monto_estimado"]
        saldado = fila["completos"] > 0 or (fila["pagos"] > 0 and fila["pagado"] >= estimado)
        return {"pagado": fila["pagado"], "saldado": saldado, "pagos": fila["pagos"],
                "falta": 0 if saldado else max(0, estimado - fila["pagado"])}

    def servicios_pendientes(self, desde: date, hasta: date) -> list[dict]:
        """Vencimientos de servicios entre dos fechas que aún no se han saldado en su mes."""
        pendientes = []
        for s in self.servicios():
            ref = desde.replace(day=1)
            while ref <= hasta:
                venc = fecha_con_dia(ref.year, ref.month, s["dia_vencimiento"])
                if desde <= venc <= hasta:
                    estado = self.estado_servicio(s["id"], periodo(venc))
                    if estado["falta"] > 0:
                        pendientes.append({"servicio": s, "fecha": venc, "monto": estado["falta"]})
                ref = sumar_meses(ref, 1, 1)
        return pendientes

    def pagar_servicio(self, servicio_id: int, fecha: date, monto: int, medio: str = "efectivo",
                       producto_id: int | None = None, num_cuotas: int | None = None, parcial: bool = False,
                       actualizar_estimado: bool = False, permitir_sobrecupo: bool = False,
                       desde_reserva: bool = False) -> int:
        """Registra el pago de un servicio por el valor real, en efectivo/débito o a crédito.

        `parcial` deja el resto (estimado − pagado) pendiente en el plan. Con
        `actualizar_estimado`, el valor pagado pasa a ser el estimado de los próximos meses.
        `desde_reserva` (solo efectivo/débito): la plata sale de la reserva (Cajita), no del disponible.
        """
        s = self._uno("SELECT * FROM servicios WHERE id = ?", (servicio_id,))
        desde_reserva = desde_reserva and medio == "efectivo"
        if desde_reserva and self.saldo_reserva() < monto:
            raise ValueError(f"La reserva tiene {formato(max(0, self.saldo_reserva()))}: no alcanza para pagar "
                             f"{formato(monto)}. Desmarca «Lo pagué con la reserva» o registra solo una parte.")
        compra_id = self.registrar_compra(fecha, s["nombre"], s["categoria_id"], monto, medio,
                                          producto_id=producto_id, num_cuotas=num_cuotas, servicio_id=servicio_id,
                                          pago_parcial=parcial, permitir_sobrecupo=permitir_sobrecupo)
        if desde_reserva:
            with self.con:
                self.con.execute("INSERT INTO reserva_movimientos (fecha, tipo, monto, compra_id, notas) "
                                 "VALUES (?, 'uso', ?, ?, ?)", (_iso(fecha), -monto, compra_id, f"Pago {s['nombre']}"))
        if actualizar_estimado and not parcial:
            with self.con:
                self.con.execute("UPDATE servicios SET monto_estimado = ? WHERE id = ?", (monto, servicio_id))
        return compra_id

    # ============================================================ compras y créditos

    def registrar_compra(self, fecha: date, descripcion: str, categoria_id: int | None, monto: int, medio: str,
                         producto_id: int | None = None, num_cuotas: int | None = None,
                         servicio_id: int | None = None, tasa_ea: float | None = None,
                         primera_cuota: date | None = None, cargo_por_cuota: int = 0,
                         condiciones: dict | None = None, cuota_inicial: int = 0,
                         precio_contado: int | None = None, permitir_sobrecupo: bool = False,
                         pago_parcial: bool = False) -> int:
        """Compra en efectivo o a crédito.

        A crédito, `monto` es el precio pagado por el producto (financiado). Se
        financia `monto − cuota_inicial` con las `condiciones` de la oferta aceptada
        (por defecto, la plantilla del producto). `tasa_ea`, `primera_cuota` y
        `cargo_por_cuota` permiten ajustar rápido la plantilla. `precio_contado`
        sirve para medir el costo frente a comprar de contado.
        """
        if monto <= 0:
            raise ValueError("El monto debe ser mayor que cero")
        if medio == "tarjeta":
            if producto_id is None:
                raise ValueError("Elige la tarjeta")
            if not num_cuotas or num_cuotas < 1:
                raise ValueError("El número de cuotas debe ser al menos 1")
            if not 0 <= cuota_inicial < monto:
                raise ValueError("La cuota inicial debe ser menor que el valor de la compra")
            prod = self.producto(producto_id)
            if prod["cupo"] > 0 and not permitir_sobrecupo:
                usado = sum(self._capital_pendiente(c) for c in self._cuotas_pendientes(producto_id=producto_id))
                disponible = prod["cupo"] - usado
                if monto - cuota_inicial > disponible:
                    raise CupoInsuficiente(
                        f"La compra financia {formato(monto - cuota_inicial)} y el cupo disponible de "
                        f"{prod['nombre']} es {formato(max(0, disponible))} (cupo {formato(prod['cupo'])}, "
                        f"usado {formato(usado)}). Si el cupo cambió, actualízalo en el producto.")
        else:
            producto_id = num_cuotas = None
            cuota_inicial = 0
        with self.con:
            cur = self.con.execute(
                "INSERT INTO compras (fecha, descripcion, categoria_id, monto, medio, producto_id, num_cuotas, "
                "servicio_id, cuota_inicial, pago_parcial) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (_iso(fecha), descripcion.strip(), categoria_id, monto, medio, producto_id, num_cuotas, servicio_id,
                 cuota_inicial, int(bool(pago_parcial and servicio_id))))
            compra_id = cur.lastrowid
            if medio == "tarjeta":
                p = self.producto(producto_id)
                base = self.condiciones_producto(producto_id)
                cond = cond_mod.cargar(cond_mod.a_texto(condiciones), base) if condiciones else base
                if tasa_ea is not None:
                    cond["tasa"] = {"valor": tasa_ea, "modalidad": "EA"}
                elif condiciones is None and p["tipo"] == "tarjeta" and num_cuotas == 1 and not p["interes_una_cuota"]:
                    cond["tasa"] = {"valor": 0.0, "modalidad": "EA"}
                if cargo_por_cuota:
                    cond["cargos"].append({"nombre": "Cargo por cuota", "base": "fijo", "valor": cargo_por_cuota,
                                           "cobro": "por_cuota", "tipo": "otro"})
                cond_mod.validar(cond)
                primera = primera_cuota or self._primera_cuota(producto_id, fecha, cond["periodicidad"])
                dia = self._dia_ancla(producto_id, primera, fecha.day if p["tipo"] == "cupo" else None)
                self._crear_desde_condiciones(producto_id, "compra", descripcion, fecha, monto - cuota_inicial,
                                              num_cuotas, cond, primera, compra_id=compra_id,
                                              precio_contado=precio_contado or monto, cuota_inicial=cuota_inicial,
                                              dia=dia)
        if medio == "tarjeta":
            self._aplicar_saldo_favor(producto_id, fecha)
        return compra_id

    def _primera_cuota(self, producto_id: int, fecha: date, periodicidad: str) -> date:
        if periodicidad != "mensual" and self.producto(producto_id)["tipo"] != "tarjeta":
            return credito.fecha_cuota(fecha, 1, periodicidad)
        return self.primera_fecha_pago(producto_id, fecha)

    def _crear_desde_condiciones(self, producto_id: int, origen: str, descripcion: str, fecha: date, capital: int,
                                 n: int, cond: dict, primera: date, compra_id: int | None = None,
                                 precio_contado: int | None = None, cuota_inicial: int = 0,
                                 cuota: int | None = None, monto_registro: int | None = None,
                                 cuotas_registro: int | None = None, desde_numero: int = 1,
                                 con_cargos_iniciales: bool = True, dia: int | None = None) -> int:
        """Crea un crédito con su cronograma y cargos, guardando la fotografía de condiciones.

        Si se indica `cuota` (cuota fija), el cronograma usa la tasa implícita en ella.
        Los cargos iniciales se registran como un pago del día de la compra (salen del
        bolsillo y son costo de la deuda).
        """
        tasa_ea = cond_mod.tasa_ea(cond)
        periodicidad = cond["periodicidad"]
        tasa = credito.tasa_periodica(tasa_ea, periodicidad)
        if cond["sistema"] == CUOTA_FIJA and cuota:
            implicita = credito.tasa_implicita_mv(capital, n, cuota)
            if implicita is None:
                cuota = None
            else:
                tasa = implicita
                tasa_ea = float(((1 + credito._dec(implicita)) ** credito.PERIODOS_ANIO[periodicidad] - 1) * 100)
                cond["tasa_segun_cuota_ea"] = tasa_ea  # La fotografía conserva la tasa declarada y la de la cuota.
        cronograma = credito.generar_cronograma(cond["sistema"], capital, tasa, primera, n=n, cuota=cuota,
                                                periodicidad=periodicidad, dia=dia)
        iniciales = credito.aplicar_cargos(cronograma, capital, cond_mod.cargos(cond))
        if not con_cargos_iniciales:
            iniciales = 0
        cur = self.con.execute(
            "INSERT INTO creditos (producto_id, compra_id, origen, descripcion, fecha, monto, num_cuotas, tasa_ea, "
            "metodo, condiciones, precio_contado, cuota_inicial, cargos_iniciales, periodicidad, dia_pago) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (producto_id, compra_id, origen, descripcion.strip(), _iso(fecha), monto_registro or capital,
             cuotas_registro or n, tasa_ea, cond["sistema"], cond_mod.a_texto(cond), precio_contado, cuota_inicial,
             iniciales, periodicidad, dia))
        credito_id = cur.lastrowid
        self._insertar_cuotas(credito_id, cronograma, desde_numero=desde_numero)
        if iniciales:
            self.con.execute(
                "INSERT INTO pagos_credito (fecha, producto_id, monto, tipo, a_costos, credito_id, notas) "
                "VALUES (?, ?, ?, 'cargo_inicial', ?, ?, 'Cargos cobrados al comprar')",
                (_iso(fecha), producto_id, iniciales, iniciales, credito_id))
        return credito_id

    def compras(self, per: str | None = None) -> list[sqlite3.Row]:
        sql = ("SELECT co.*, ca.nombre AS categoria, p.nombre AS producto FROM compras co "
               "LEFT JOIN categorias ca ON ca.id = co.categoria_id "
               "LEFT JOIN productos_credito p ON p.id = co.producto_id")
        if per:
            return self._todos(sql + " WHERE substr(co.fecha, 1, 7) = ? ORDER BY co.fecha DESC, co.id DESC", (per,))
        return self._todos(sql + " ORDER BY co.fecha DESC, co.id DESC")

    def eliminar_compra(self, id_: int) -> None:
        cr = self._uno("SELECT id, estado FROM creditos WHERE compra_id = ?", (id_,))
        if cr is not None:
            self._validar_credito_sin_movimientos(cr["id"])
        with self.con:
            self._cambio("compra", id_, "eliminar", self._uno("SELECT * FROM compras WHERE id = ?", (id_,)))
            if cr is not None:
                self.con.execute("DELETE FROM pagos_credito WHERE credito_id = ? AND tipo = 'cargo_inicial'",
                                 (cr["id"],))
            self.con.execute("DELETE FROM compras WHERE id = ?", (id_,))

    def _validar_credito_sin_movimientos(self, credito_id: int) -> None:
        cr = self._uno("SELECT estado FROM creditos WHERE id = ?", (credito_id,))
        if cr["estado"] == "refinanciado":
            raise ValueError("Esta deuda fue refinanciada. Elimina primero la refinanciación.")
        if self._valor("SELECT COUNT(*) FROM cuotas WHERE credito_id = ? AND (pagado > 0 OR mora > 0 OR "
                       "cobranza > 0 OR creada_por_pago IS NOT NULL OR reemplazada_por_pago IS NOT NULL)",
                       (credito_id,)):
            raise ValueError("Esta deuda ya tiene pagos aplicados. Elimina primero esos pagos.")

    def _crear_credito(self, producto_id: int, origen: str, descripcion: str, fecha: date, monto: int, n: int,
                       tasa_ea: float, metodo: str, cronograma: list[credito.Cuota],
                       compra_id: int | None = None, dia: int | None = None) -> int:
        cur = self.con.execute(
            "INSERT INTO creditos (producto_id, compra_id, origen, descripcion, fecha, monto, num_cuotas, tasa_ea, "
            "metodo, dia_pago) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (producto_id, compra_id, origen, descripcion.strip(), _iso(fecha), monto, n, tasa_ea, metodo, dia))
        credito_id = cur.lastrowid
        self._insertar_cuotas(credito_id, cronograma)
        return credito_id

    def _insertar_cuotas(self, credito_id: int, cronograma: list[credito.Cuota], desde_numero: int = 1,
                         pago_id: int | None = None) -> None:
        self.con.executemany(
            "INSERT INTO cuotas (credito_id, numero, fecha, capital, interes, otros, detalle, creada_por_pago) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(credito_id, desde_numero + c.numero - 1, _iso(c.fecha), c.capital, c.interes, c.otros,
              json.dumps(c.detalle, ensure_ascii=False) if c.detalle else None, pago_id)
             for c in cronograma])

    def registrar_deuda_existente(self, producto_id: int, descripcion: str, proxima_cuota: date, valor: int,
                                  cuotas_totales: int, cuotas_pagadas: int, tasa_ea: float, metodo: str,
                                  cuota: int | None = None, saldo: int | None = None,
                                  cargo_por_cuota: int = 0, condiciones: dict | None = None) -> int:
        """Compra a cuotas o préstamo que ya venía de antes, con los datos que muestra la app del banco.

        `valor` es el valor original y `cuotas_pagadas` las ya pagadas (cuota "n de N"
        → pagadas = n − 1). Si no se indica `saldo`, se calcula con el cronograma
        original. Las cuotas se numeran desde `cuotas_pagadas + 1`. Los cargos de
        `condiciones` se calculan sobre el saldo pendiente.
        """
        if valor <= 0 or cuotas_totales < 1:
            raise ValueError("El valor y el total de cuotas deben ser mayores que cero")
        if not 0 <= cuotas_pagadas < cuotas_totales:
            raise ValueError("Las cuotas ya pagadas deben ser menos que el total de cuotas")
        base = self.condiciones_producto(producto_id)
        cond = cond_mod.cargar(cond_mod.a_texto(condiciones), base) if condiciones else base
        cond["tasa"] = {"valor": tasa_ea, "modalidad": "EA"}
        cond["sistema"] = metodo
        if cargo_por_cuota:
            cond["cargos"].append({"nombre": "Cargo por cuota", "base": "fijo", "valor": cargo_por_cuota,
                                   "cobro": "por_cuota", "tipo": "otro"})
        cond_mod.validar(cond)
        cuotas_restantes = cuotas_totales - cuotas_pagadas
        tasa = credito.tasa_periodica(tasa_ea, cond["periodicidad"])
        if saldo is None:
            saldo = credito.saldo_tras_cuotas(metodo, valor, cuotas_totales, tasa, cuotas_pagadas)
        if saldo <= 0:
            raise ValueError("El saldo pendiente debe ser mayor que cero")
        with self.con:
            credito_id = self._crear_desde_condiciones(
                producto_id, "deuda_existente", descripcion, date.today(), saldo, cuotas_restantes, cond,
                proxima_cuota, cuota=cuota, monto_registro=valor, cuotas_registro=cuotas_totales,
                desde_numero=cuotas_pagadas + 1, con_cargos_iniciales=False,
                dia=self._dia_ancla(producto_id, proxima_cuota))
        self._aplicar_saldo_favor(producto_id, date.today())
        return credito_id

    def creditos(self, producto_id: int | None = None, solo_activos: bool = True) -> list[dict]:
        """Créditos con su saldo y avance."""
        sql = ("SELECT cr.*, p.nombre AS producto FROM creditos cr JOIN productos_credito p ON p.id = cr.producto_id "
               "WHERE 1 = 1")
        params: tuple = ()
        if producto_id is not None:
            sql += " AND cr.producto_id = ?"
            params += (producto_id,)
        if solo_activos:
            sql += " AND cr.estado = 'activo'"
        resultado = []
        for cr in self._todos(sql + " ORDER BY cr.fecha DESC, cr.id DESC", params):
            pendientes = self._cuotas_pendientes(credito_id=cr["id"])
            resultado.append({
                "credito": cr,
                "saldo": sum(self._capital_pendiente(c) for c in pendientes),
                "cuotas_restantes": len(pendientes),
                "proxima": pendientes[0] if pendientes else None,
            })
        return resultado

    def eliminar_credito(self, credito_id: int) -> None:
        cr = self._uno("SELECT * FROM creditos WHERE id = ?", (credito_id,))
        if cr["origen"] == "compra":
            raise ValueError("Esta deuda viene de una compra: elimina la compra.")
        if cr["origen"] == "refinanciacion":
            raise ValueError("Esta deuda viene de una refinanciación: elimina la refinanciación.")
        self._validar_credito_sin_movimientos(credito_id)
        with self.con:
            self._cambio("credito", credito_id, "eliminar", cr)
            self.con.execute("DELETE FROM creditos WHERE id = ?", (credito_id,))

    def cronograma_credito(self, credito_id: int) -> list[sqlite3.Row]:
        return self._todos("SELECT * FROM cuotas WHERE credito_id = ? AND estado != 'reemplazada' "
                           "ORDER BY fecha, numero", (credito_id,))

    # ------------------------------------------------------------ cuotas pendientes

    def _cuotas_pendientes(self, producto_id: int | None = None, credito_id: int | None = None) -> list[sqlite3.Row]:
        sql = ("SELECT cu.*, cr.producto_id, cr.tasa_ea, cr.metodo, cr.periodicidad, cr.condiciones, "
               "cr.descripcion AS credito_descripcion, cr.fecha AS credito_fecha FROM cuotas cu "
               "JOIN creditos cr ON cr.id = cu.credito_id "
               "WHERE cu.estado = 'pendiente' AND cr.estado = 'activo'")
        params: tuple = ()
        if producto_id is not None:
            sql += " AND cr.producto_id = ?"
            params += (producto_id,)
        if credito_id is not None:
            sql += " AND cr.id = ?"
            params += (credito_id,)
        return self._todos(sql + " ORDER BY cu.fecha, cu.id", params)

    @staticmethod
    def _capital_pendiente(c: sqlite3.Row) -> int:
        return max(0, c["capital"] - c["pagado_capital"])

    @staticmethod
    def _pendiente(c: sqlite3.Row) -> int:
        return sum(max(0, c[comp] - c[col]) for comp, col in PAGADO.items())

    @staticmethod
    def _cuota_pendiente(c: sqlite3.Row) -> CuotaPendiente:
        orden = cond_mod.orden(cond_mod.de_credito(c))
        return CuotaPendiente(c["id"], _fecha(c["fecha"]), c["capital"], c["interes"], c["otros"], c["pagado"],
                              mora=c["mora"], cobranza=c["cobranza"],
                              pagado_por={comp: c[col] for comp, col in PAGADO.items()}, orden=orden)

    def _total_para_cancelar(self, pendientes: list[sqlite3.Row], limite: date | None,
                             fecha: date | None = None) -> int:
        """Lo que cuesta cancelar todo en `fecha`: capital pendiente + costos de lo vencido y del ciclo.

        Los intereses de cuotas futuras no se cobran al cancelar; los cargos sí, si la
        oferta dice que se mantienen al pagar antes (ej. la fianza de algunas plataformas).
        Si la oferta dice que al prepagar solo se cobra el interés causado, la cuota del
        ciclo que aún no vence lleva el interés de los días corridos.
        """
        total = 0
        for c in pendientes:
            total += self._capital_pendiente(c)
            if limite is not None and _fecha(c["fecha"]) <= limite or limite is None:
                costos = self._pendiente(c) - self._capital_pendiente(c)
                causado = self._interes_si_cancela(c, fecha) if fecha is not None else None
                if causado is not None:
                    costos -= max(0, c["interes"] - max(causado, c["pagado_interes"]))
                total += costos
            elif cond_mod.de_credito(c)["cargos_prepago"] == "se_mantienen":
                total += max(0, c["otros"] - c["pagado_otros"])
        return total

    def _interes_si_cancela(self, c: sqlite3.Row, fecha: date) -> int | None:
        """Interés causado hasta `fecha` de una cuota que aún no vence, si la oferta cobra solo lo causado."""
        if cond_mod.de_credito(c)["prepago"].get("interes") != "causado" or _fecha(c["fecha"]) <= fecha:
            return None
        periodicidad = c["periodicidad"] or "mensual"
        vence = _fecha(c["fecha"])
        inicio = (sumar_meses(vence, -1) if periodicidad == "mensual"
                  else vence - timedelta(days=credito.DIAS_PERIODO[periodicidad]))
        saldo = self._valor("SELECT SUM(capital - pagado_capital) FROM cuotas WHERE credito_id = ? "
                            "AND estado = 'pendiente' AND fecha >= ?", (c["credito_id"], c["fecha"]))
        tasa = credito.tasa_periodica(c["tasa_ea"], periodicidad)
        return min(c["interes"], credito.interes_causado(saldo, tasa, (fecha - inicio).days, (vence - inicio).days))

    def _ajustar_interes_prepago(self, pendientes: list[sqlite3.Row], hasta: date, fecha: date,
                                 pago_id: int) -> bool:
        """Al cancelar, deja en las cuotas del ciclo solo el interés causado (se deshace al eliminar el pago)."""
        cambio = False
        for c in pendientes:
            if _fecha(c["fecha"]) > hasta:
                continue
            causado = self._interes_si_cancela(c, fecha)
            if causado is None:
                continue
            nuevo = max(causado, c["pagado_interes"])
            if nuevo < c["interes"]:
                self.con.execute("UPDATE cuotas SET interes = ? WHERE id = ?", (nuevo, c["id"]))
                self.con.execute("INSERT INTO ajustes_cuota (cuota_id, campo, antes, despues, motivo, pago_id) "
                                 "VALUES (?, 'interes', ?, ?, 'prepago', ?)", (c["id"], c["interes"], nuevo, pago_id))
                cambio = True
        return cambio

    def _deshacer_ajustes(self, pago_id: int | None = None, extracto_id: int | None = None) -> None:
        campo, valor = ("pago_id", pago_id) if pago_id is not None else ("extracto_id", extracto_id)
        filas = self._todos(f"SELECT * FROM ajustes_cuota WHERE {campo} = ? ORDER BY id DESC", (valor,))
        for a in filas:
            cu = self._uno("SELECT pagado_interes FROM cuotas WHERE id = ?", (a["cuota_id"],))
            if cu is None:
                continue
            if cu["pagado_interes"] > a["antes"]:
                raise ValueError("Hay pagos aplicados con los intereses de este extracto: elimina primero esos pagos.")
            self.con.execute("UPDATE cuotas SET interes = ? WHERE id = ?", (a["antes"], a["cuota_id"]))
        self.con.execute(f"DELETE FROM ajustes_cuota WHERE {campo} = ?", (valor,))

    # ============================================================ deuda

    def deuda_productos(self, hoy: date | None = None) -> list[dict]:
        """Por cada tarjeta/crédito: saldo de capital, uso del cupo y próximo pago."""
        hoy = hoy or date.today()
        resultado = []
        for p in self.productos():
            pendientes = self._cuotas_pendientes(producto_id=p["id"])
            saldo = sum(self._capital_pendiente(c) for c in pendientes)
            prox = self.proximo_pago_producto(p["id"], hoy)
            resultado.append({
                "producto": p,
                "saldo": saldo,
                "uso_cupo": (saldo / p["cupo"]) if p["cupo"] else None,
                "disponible": max(0, p["cupo"] - saldo) if p["cupo"] else None,
                "saldo_favor": self.saldo_a_favor(p["id"]),
                "cuotas_activas": len({c["credito_id"] for c in pendientes}),
                "ultima_fecha": _fecha(pendientes[-1]["fecha"]) if pendientes else None,
                **prox,
            })
        return resultado

    def deuda_total(self) -> int:
        return sum(self._capital_pendiente(c) for c in self._cuotas_pendientes())

    def proximo_pago_producto(self, producto_id: int, hoy: date) -> dict:
        """Mínimo y total del próximo pago de un producto (usa el extracto si lo hay)."""
        p = self.producto(producto_id)
        pendientes = self._cuotas_pendientes(producto_id=producto_id)
        saldo = sum(self._capital_pendiente(c) for c in pendientes)
        limite = self._limite_ciclo(p, pendientes, hoy)

        ext = self.extracto_vigente(producto_id, hoy)
        if ext:
            pagado = self._pagado_desde(producto_id, _fecha(ext["fecha_corte"]))
            minimo = max(0, ext["pago_minimo"] - pagado)
            total = max(0, ext["pago_total"] - pagado)
            return {"fecha_limite": _fecha(ext["fecha_limite"]), "minimo": minimo, "total": total,
                    "fuente": "extracto", "mora_estimada": 0,
                    "interes_si_minimo": credito.interes_si_paga_minimo(total - minimo, p["tasa_ea"])}

        mora = sum(f["monto"] for f in self._calcular_mora(producto_id, hoy))
        if limite is None:
            vencido = sum(self._pendiente(c) for c in pendientes) + mora
            return {"fecha_limite": None, "minimo": vencido, "total": vencido, "fuente": "cronograma",
                    "interes_si_minimo": 0, "mora_estimada": mora}
        del_ciclo = [c for c in pendientes if _fecha(c["fecha"]) <= limite]
        manejo = max(0, p["cuota_manejo"] - self._valor(
            "SELECT SUM(a_manejo) FROM pagos_credito WHERE producto_id = ? AND ciclo = ?", (producto_id, _iso(limite))))
        minimo = sum(self._pendiente(c) for c in del_ciclo) + manejo + mora
        total = self._total_para_cancelar(pendientes, limite, hoy) + manejo + mora
        capital_ciclo = sum(self._capital_pendiente(c) for c in del_ciclo)
        return {"fecha_limite": limite, "minimo": minimo, "total": total, "fuente": "cronograma",
                "interes_si_minimo": credito.interes_si_paga_minimo(saldo - capital_ciclo, p["tasa_ea"]),
                "mora_estimada": mora}

    @staticmethod
    def _limite_ciclo(p: sqlite3.Row, pendientes: list[sqlite3.Row], desde: date) -> date | None:
        """Última fecha de vencimiento que entra en el próximo pago.

        Tarjetas y préstamos: la primera cuota que vence desde `desde`. Cupos (Addi,
        Sistecrédito, almacenes): cada compra vence en su propio día, así que el
        próximo pago reúne las cuotas de ese mes.
        """
        futuras = [_fecha(c["fecha"]) for c in pendientes if _fecha(c["fecha"]) >= desde]
        if not futuras:
            return None
        if p["tipo"] != "cupo":
            return futuras[0]
        mes = periodo(futuras[0])
        return max(f for f in futuras if periodo(f) == mes)

    def _pagado_desde(self, producto_id: int, desde: date) -> int:
        return self._valor("SELECT SUM(monto) FROM pagos_credito WHERE producto_id = ? AND fecha > ? "
                           "AND tipo NOT IN ('refinanciacion', 'cargo_inicial', 'devolucion')",
                           (producto_id, _iso(desde)))

    def pagos_programados(self, desde: date | None, hasta: date) -> list[dict]:
        """Pagos de crédito pendientes con vencimiento en el rango (desde=None incluye vencidos).

        Si hay un extracto con fecha límite en el rango, su pago mínimo (menos lo ya
        pagado desde el corte) reemplaza lo calculado por el cronograma para ese mes.
        """
        hoy = date.today()
        por_clave: dict[tuple[int, str], dict] = {}
        for c in self._cuotas_pendientes():
            f = _fecha(c["fecha"])
            if f > hasta or (desde is not None and f < desde):
                continue
            clave = (c["producto_id"], periodo(f))
            item = por_clave.setdefault(clave, {"producto_id": c["producto_id"], "fecha": f, "monto": 0,
                                                "fuente": "cronograma"})
            item["monto"] += self._pendiente(c)
            item["fecha"] = max(item["fecha"], f)
        # Cuota de manejo de meses futuros en que la tarjeta tiene cuotas.
        for (producto_id, per), item in por_clave.items():
            if per >= periodo(hoy):
                item["monto"] += self.producto(producto_id)["cuota_manejo"]
        for p in self.productos():
            ext = self.extracto_vigente(p["id"], hoy)
            if not ext:
                continue
            limite = _fecha(ext["fecha_limite"])
            if limite > hasta or (desde is not None and limite < desde):
                continue
            pagado = self._pagado_desde(p["id"], _fecha(ext["fecha_corte"]))
            por_clave[(p["id"], periodo(limite))] = {"producto_id": p["id"], "fecha": limite,
                                                     "monto": max(0, ext["pago_minimo"] - pagado),
                                                     "fuente": "extracto"}
        return sorted(por_clave.values(), key=lambda i: i["fecha"])

    def total_programado(self, desde: date | None, hasta: date) -> int:
        return sum(i["monto"] for i in self.pagos_programados(desde, hasta))

    def proyeccion_pagos(self, meses: int = 12, hoy: date | None = None) -> dict[str, dict[str, int]]:
        """{periodo: {producto: monto}} de los próximos meses."""
        hoy = hoy or date.today()
        nombres = {p["id"]: p["nombre"] for p in self.productos(False)}
        resultado: dict[str, dict[str, int]] = {}
        per = periodo(hoy)
        for k in range(meses):
            p = periodo_siguiente(per, k)
            desde = None if k == 0 else inicio_periodo(p)
            fila: dict[str, int] = defaultdict(int)
            for item in self.pagos_programados(desde, fin_periodo(p)):
                fila[nombres[item["producto_id"]]] += item["monto"]
            resultado[p] = dict(fila)
        return resultado

    # ============================================================ pagos

    def registrar_pago(self, producto_id: int, fecha: date, monto: int, desde_reserva: bool = False,
                       reducir: str = "plazo", notas: str = "", canal: str = "", origen: str = "abono") -> dict:
        """Registra un pago a una tarjeta/crédito.

        1. Liquida la mora y la cobranza hasta la fecha del pago (sin duplicar lo ya liquidado).
        2. Cubre las cuotas vencidas y las del ciclo actual, cada una en el orden
           contractual de su crédito, y la cuota de manejo (o las comisiones del extracto)
           una sola vez por ciclo.
        3. Lo que sobra, según `reducir`: "plazo" o "cuota" (abono extraordinario a
           capital de la deuda más cara) o "anticipar" (cubre las cuotas siguientes completas).
        4. Lo que no se puede aplicar queda como saldo a favor del producto.

        Si hay un extracto vigente para la fecha del pago, el pago se clasifica contra
        su mínimo y su total. `origen="saldo_favor"` aplica un saldo a favor existente.
        """
        if monto <= 0:
            raise ValueError("El monto debe ser mayor que cero")
        p = self.producto(producto_id)
        if desde_reserva:
            disponible = self.saldo_reserva()
            if disponible < monto:
                raise ValueError(f"La reserva tiene {formato(max(0, disponible))}: no alcanza para pagar "
                                 f"{formato(monto)} desde ahí. Desmarca «desde la reserva» o registra antes el aporte.")
        ext = self._extracto_del_pago(producto_id, fecha)
        pagado_antes = self._pagado_desde(producto_id, _fecha(ext["fecha_corte"])) if ext else 0
        with self.con:
            pago_id = self.con.execute(
                "INSERT INTO pagos_credito (fecha, producto_id, monto, tipo, desde_reserva, notas, canal) "
                "VALUES (?, ?, ?, 'abono', ?, ?, ?)", (_iso(fecha), producto_id, monto, int(desde_reserva), notas, canal)
            ).lastrowid
            self._revertir_mora_posterior(producto_id, fecha)
            mora_liquidada = self._liquidar_mora(producto_id, fecha, pago_id)
            pendientes = self._cuotas_pendientes(producto_id=producto_id)
            hasta = self._limite_ciclo(p, pendientes, fecha) or fecha
            total = self._total_para_cancelar(pendientes, hasta, fecha)
            if monto >= total and self._ajustar_interes_prepago(pendientes, hasta, fecha, pago_id):
                pendientes = self._cuotas_pendientes(producto_id=producto_id)
                total = self._total_para_cancelar(pendientes, hasta, fecha)
            del_ciclo = [c for c in pendientes if _fecha(c["fecha"]) <= hasta]
            minimo = sum(self._pendiente(c) for c in del_ciclo)

            # Cuota de manejo (o comisiones del extracto): no está en el cronograma y se cubre una vez por ciclo.
            ciclo = ext["fecha_limite"] if ext else _iso(hasta)
            costos_ciclo = (ext["comisiones_avances"] + ext["comisiones_servicio"] + ext["cargos_conversion"]
                            if ext else (p["cuota_manejo"] if minimo else 0))
            manejo_pendiente = max(0, costos_ciclo - self._valor(
                "SELECT SUM(a_manejo) FROM pagos_credito WHERE producto_id = ? AND ciclo = ? AND id != ?",
                (producto_id, ciclo, pago_id)))

            cuotas = [self._cuota_pendiente(c) for c in pendientes]
            aplicaciones, sobrante = credito.aplicar_pago(cuotas, monto, hasta)
            manejo = min(sobrante, manejo_pendiente)
            sobrante -= manejo
            redondeo = 0
            if sobrante < credito.PESO:  # Diferencias de centavos por redondeo: se toman como cargos.
                redondeo, sobrante = sobrante, 0
            minimo += manejo_pendiente
            total += manejo_pendiente
            if ext:  # El extracto es el dato real del banco para este ciclo.
                minimo = max(0, ext["pago_minimo"] - pagado_antes)
                total = max(0, ext["pago_total"] - pagado_antes)
            anticipado = 0
            if reducir == "anticipar" and sobrante:
                futuras = [c for c in cuotas if c.fecha > hasta]
                extra, sobrante = credito.aplicar_pago(futuras, sobrante)
                aplicaciones += extra
                anticipado = sum(a.monto for a in extra)

            if origen == "saldo_favor":
                tipo = "saldo_favor"
            elif minimo == 0:
                tipo = "abono"
            elif monto >= total:
                tipo = "total"
            elif monto >= minimo:
                tipo = "minimo" if sobrante == 0 and not anticipado else "mas_del_minimo"
            else:
                tipo = "menor_al_minimo"

            self._guardar_aplicaciones(pago_id, aplicaciones)
            abono, penalidad = (self._aplicar_abono(producto_id, pago_id, sobrante, hasta, reducir)
                                if sobrante and reducir != "anticipar" else (0, 0))
            resto = sobrante - abono - penalidad
            if resto >= credito.PESO:
                # Ya no queda capital futuro que abonar (ej. cargos que se mantienen al cancelar):
                # lo que sobra cubre lo pendiente que quede, en el orden del contrato.
                cuotas = [self._cuota_pendiente(c) for c in self._cuotas_pendientes(producto_id=producto_id)]
                extra, resto_final = credito.aplicar_pago(cuotas, resto)
                self._guardar_aplicaciones(pago_id, extra)
                aplicaciones += extra
                anticipado += resto - resto_final
                sobrante -= resto - resto_final
            sin_aplicar = sobrante - abono - penalidad
            self._actualizar_estados(producto_id)
            a_costos = sum(a.a_costos for a in aplicaciones) + manejo + redondeo + penalidad
            a_capital = sum(a.a_capital for a in aplicaciones) + abono
            self.con.execute("UPDATE pagos_credito SET tipo = ?, a_capital = ?, a_costos = ?, abono_extra = ?, "
                             "a_manejo = ?, ciclo = ?, saldo_favor = ? WHERE id = ?",
                             (tipo, a_capital, a_costos, abono, manejo, ciclo, sin_aplicar, pago_id))
            if desde_reserva:
                self.con.execute("INSERT INTO reserva_movimientos (fecha, tipo, monto, pago_id, notas) "
                                 "VALUES (?, 'uso', ?, ?, ?)", (_iso(fecha), -monto, pago_id, f"Pago {p['nombre']}"))
        por_componente: dict[str, int] = defaultdict(int)
        for a in aplicaciones:
            for comp, valor in a.por_componente.items():
                por_componente[comp] += valor
        return {"pago_id": pago_id, "tipo": tipo, "a_costos": a_costos, "a_capital": a_capital,
                "abono_extra": abono, "anticipado": anticipado, "penalidad": penalidad,
                "sin_aplicar": sin_aplicar, "minimo": minimo, "mora_liquidada": mora_liquidada,
                "por_componente": dict(por_componente), "manejo": manejo, "segun_extracto": bool(ext)}

    def _extracto_del_pago(self, producto_id: int, fecha: date) -> sqlite3.Row | None:
        """Extracto cuyo ciclo cubre la fecha del pago (después del corte y hasta la fecha límite)."""
        ext = self._uno("SELECT * FROM extractos WHERE producto_id = ? AND fecha_corte < ? AND fecha_limite >= ? "
                        "ORDER BY fecha_corte DESC LIMIT 1", (producto_id, _iso(fecha), _iso(fecha)))
        if ext and self._valor("SELECT COUNT(*) FROM refinanciaciones WHERE producto_id = ? AND fecha > ?",
                               (producto_id, ext["fecha_corte"])):
            return None
        return ext

    # ------------------------------------------------------------ saldo a favor

    def saldo_a_favor(self, producto_id: int) -> int:
        """Lo pagado o devuelto que no se pudo aplicar a la deuda y aún no se ha usado."""
        return max(0, self._valor("SELECT SUM(saldo_favor) FROM pagos_credito WHERE producto_id = ?", (producto_id,))
                   - self._valor("SELECT SUM(monto) FROM pagos_credito WHERE producto_id = ? AND tipo = 'saldo_favor'",
                                 (producto_id,)))

    def _aplicar_saldo_favor(self, producto_id: int, fecha: date) -> dict | None:
        """Usa el saldo a favor del producto en la deuda pendiente (al registrar una deuda nueva)."""
        favor = self.saldo_a_favor(producto_id)
        if favor < credito.PESO or not self._cuotas_pendientes(producto_id=producto_id):
            return None
        try:
            return self.registrar_pago(producto_id, fecha, favor, notas="Saldo a favor aplicado", origen="saldo_favor")
        except ValueError:
            return None  # Se aplicará la próxima vez que haya deuda nueva.

    def _guardar_aplicaciones(self, pago_id: int, aplicaciones: list[credito.Aplicacion]) -> None:
        for a in aplicaciones:
            por = a.por_componente or {"capital": a.a_capital, "interes": a.a_costos}
            self.con.execute(
                "INSERT INTO pagos_aplicacion (pago_id, cuota_id, monto, a_costos, a_capital, a_interes, a_otros, "
                "a_mora, a_cobranza) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (pago_id, a.cuota_id, a.monto, a.a_costos, a.a_capital, por.get("interes", 0), por.get("otros", 0),
                 por.get("mora", 0), por.get("cobranza", 0)))
            sets = ", ".join(f"{PAGADO[comp]} = {PAGADO[comp]} + ?" for comp in por)
            self.con.execute(f"UPDATE cuotas SET pagado = pagado + ?, {sets} WHERE id = ?",
                             (a.monto, *por.values(), a.cuota_id))

    def _aplicar_abono(self, producto_id: int, pago_id: int, monto: int, despues_de: date, reducir: str,
                       credito_ids: list[int] | None = None, con_penalidad: bool = True) -> tuple[int, int]:
        """Abono a capital sobre las cuotas futuras sin pagos; devuelve (capital abonado, penalidad).

        Va primero a la deuda de mayor tasa. Si la oferta tiene penalidad por prepago,
        se descuenta del abono. Los cargos de las cuotas reemplazadas se conservan
        completos si la oferta dice que se mantienen; si no, cada cuota nueva lleva
        los cargos por cuota de antes.
        """
        if credito_ids is None:
            credito_ids = [f["id"] for f in self._todos(
                "SELECT id FROM creditos WHERE producto_id = ? AND estado = 'activo' ORDER BY tasa_ea DESC, id",
                (producto_id,))]
        aplicado = penalidades = 0
        for credito_id in credito_ids:
            disponible = monto - aplicado - penalidades
            if disponible <= 0:
                break
            futuras = [c for c in self._cuotas_pendientes(credito_id=credito_id)
                       if _fecha(c["fecha"]) > despues_de and c["pagado"] == 0]
            if not futuras:
                continue
            cr = self._uno("SELECT * FROM creditos WHERE id = ?", (credito_id,))
            cond = cond_mod.de_credito(cr)
            pct = float(cond["prepago"].get("penalidad_pct", 0)) if con_penalidad else 0.0
            saldo = sum(c["capital"] for c in futuras)
            abono = min(credito._pesos(credito._dec(disponible) / (1 + credito._dec(pct) / 100)), saldo)
            penalidad = credito._pesos(credito._dec(abono) * credito._dec(pct) / 100)
            primera = futuras[0]
            tasa = credito.tasa_periodica(cr["tasa_ea"], cr["periodicidad"] or "mensual")
            dia = cr["dia_pago"] or self._dia_ancla(cr["producto_id"], _fecha(primera["fecha"]))
            nuevo = credito.recalcular_tras_abono(
                cr["metodo"], saldo - abono, tasa, _fecha(primera["fecha"]), len(futuras),
                primera["capital"] + primera["interes"], primera["capital"], reducir, cr["periodicidad"] or "mensual",
                dia=dia)
            self._trasladar_cargos(futuras, nuevo, cond)
            self.con.executemany("UPDATE cuotas SET estado = 'reemplazada', reemplazada_por_pago = ? WHERE id = ?",
                                 [(pago_id, c["id"]) for c in futuras])
            if not nuevo and cond["cargos_prepago"] == "se_mantienen" and sum(c["otros"] for c in futuras):
                # Capital cancelado, pero los cargos siguen pendientes: quedan en una cuota de solo cargos.
                detalle = defaultdict(int)
                for c in futuras:
                    for nombre, valor in _detalle(c).items():
                        detalle[nombre] += valor
                nuevo = [credito.Cuota(1, _fecha(primera["fecha"]), 0, 0, sum(detalle.values()), 0, dict(detalle))]
            self._insertar_cuotas(credito_id, nuevo, desde_numero=primera["numero"], pago_id=pago_id)
            aplicado += abono
            penalidades += penalidad
        return aplicado, penalidades

    @staticmethod
    def _trasladar_cargos(viejas: list[sqlite3.Row], nuevas: list[credito.Cuota], cond: dict) -> None:
        """Pone en el cronograma recalculado los cargos de las cuotas reemplazadas.

        - Si la oferta dice que los cargos se mantienen al prepagar: el total pendiente
          de cada cargo se reparte en las cuotas nuevas.
        - Si se eliminan: los cargos sobre saldo se recalculan con el saldo nuevo; los
          repartidos (fianza, aval) se reducen en proporción al capital que queda, igual
          si se reduce cuota o plazo; los cargos fijos por cuota se cobran en cada cuota nueva.
        """
        if not nuevas:
            return
        mantener = cond["cargos_prepago"] == "se_mantienen"
        definidos = {c.nombre: c for c in cond_mod.cargos(cond)}
        totales: dict[str, int] = defaultdict(int)
        for c in viejas:
            for nombre, valor in _detalle(c).items():
                totales[nombre] += valor
        capital_viejo = sum(c["capital"] for c in viejas)
        capital_nuevo = sum(c.capital for c in nuevas)
        n = len(nuevas)
        for nombre, total in totales.items():
            cargo = definidos.get(nombre)
            if mantener:
                montos = credito.repartir(total, n)
            elif cargo and cargo.base == "pct_saldo":
                montos = [credito._pesos(cargo._con_iva(c.saldo_inicial * credito._dec(cargo.valor) / 100))
                          for c in nuevas]
            elif cargo and cargo.cobro == "prorrateado":
                restante = credito._pesos(credito._dec(total) * capital_nuevo / capital_viejo) if capital_viejo else 0
                montos = credito.repartir(restante, n)
            else:
                montos = [_detalle(viejas[0]).get(nombre, 0)] * n
            for c, monto in zip(nuevas, montos):
                if monto:
                    c.otros += monto
                    c.detalle[nombre] = c.detalle.get(nombre, 0) + monto

    def registrar_devolucion(self, credito_id: int, fecha: date, monto: int, reducir: str = "cuota",
                             notas: str = "") -> dict:
        """Devolución total o parcial de una compra financiada: reduce el capital de ese crédito.

        No es plata que salga del bolsillo ni un costo. Primero reduce las cuotas
        futuras (plazo o cuota); si queda valor, se aplica al capital de cuotas
        vencidas o del ciclo. Lo que exceda la deuda queda como saldo a favor.
        """
        if monto <= 0:
            raise ValueError("El valor de la devolución debe ser mayor que cero")
        cr = self._uno("SELECT * FROM creditos WHERE id = ?", (credito_id,))
        if cr is None or cr["estado"] != "activo":
            raise ValueError("La deuda no está activa")
        with self.con:
            pago_id = self.con.execute(
                "INSERT INTO pagos_credito (fecha, producto_id, monto, tipo, credito_id, notas) "
                "VALUES (?, ?, ?, 'devolucion', ?, ?)",
                (_iso(fecha), cr["producto_id"], monto, credito_id, notas or "Devolución de compra")).lastrowid
            abono, _ = self._aplicar_abono(cr["producto_id"], pago_id, monto, fecha, reducir, [credito_id],
                                           con_penalidad=False)
            restante = monto - abono
            aplicaciones = []
            if restante:
                cuotas = [self._cuota_pendiente(c) for c in self._cuotas_pendientes(credito_id=credito_id)]
                for c in cuotas:
                    c.orden = ("capital",)
                aplicaciones, restante = credito.aplicar_pago(cuotas, restante)
                self._guardar_aplicaciones(pago_id, aplicaciones)
            self._actualizar_estados(cr["producto_id"])
            a_capital = abono + sum(a.a_capital for a in aplicaciones)
            self.con.execute("UPDATE pagos_credito SET a_capital = ?, abono_extra = ?, saldo_favor = ? WHERE id = ?",
                             (a_capital, abono, restante, pago_id))
        return {"pago_id": pago_id, "a_capital": a_capital, "saldo_a_favor": restante}

    def pago_posible_duplicado(self, producto_id: int, fecha: date, monto: int) -> bool:
        return bool(self._valor("SELECT COUNT(*) FROM pagos_credito WHERE producto_id = ? AND fecha = ? AND monto = ? "
                                "AND tipo NOT IN ('cargo_inicial', 'devolucion', 'saldo_favor')",
                                (producto_id, _iso(fecha), monto)))

    def _actualizar_estados(self, producto_id: int) -> None:
        self.con.execute("UPDATE cuotas SET estado = CASE WHEN pagado >= capital + interes + otros + mora + cobranza "
                         "THEN 'pagada' ELSE 'pendiente' END WHERE estado IN ('pendiente', 'pagada') AND credito_id IN "
                         "(SELECT id FROM creditos WHERE producto_id = ?)", (producto_id,))
        self.con.execute("UPDATE creditos SET estado = CASE WHEN EXISTS (SELECT 1 FROM cuotas cu WHERE "
                         "cu.credito_id = creditos.id AND cu.estado = 'pendiente') THEN 'activo' ELSE 'pagado' END "
                         "WHERE producto_id = ? AND estado IN ('activo', 'pagado')", (producto_id,))

    def pagos(self, per: str | None = None, producto_id: int | None = None) -> list[sqlite3.Row]:
        sql = ("SELECT pa.*, p.nombre AS producto FROM pagos_credito pa "
               "JOIN productos_credito p ON p.id = pa.producto_id WHERE 1 = 1")
        params: tuple = ()
        if per:
            sql += " AND substr(pa.fecha, 1, 7) = ?"
            params += (per,)
        if producto_id is not None:
            sql += " AND pa.producto_id = ?"
            params += (producto_id,)
        return self._todos(sql + " ORDER BY pa.fecha DESC, pa.id DESC", params)

    def eliminar_pago(self, pago_id: int) -> None:
        pago = self._uno("SELECT * FROM pagos_credito WHERE id = ?", (pago_id,))
        if pago is None:
            return
        if self._valor("SELECT COUNT(*) FROM refinanciaciones WHERE pago_id = ?", (pago_id,)):
            raise ValueError("Este pago es parte de una refinanciación: elimina la refinanciación.")
        if pago["tipo"] == "cargo_inicial":
            raise ValueError("Es un cargo cobrado al comprar: elimina la compra.")
        ultimo = self._valor("SELECT MAX(id) FROM pagos_credito WHERE producto_id = ? "
                             "AND tipo NOT IN ('refinanciacion', 'cargo_inicial')", (pago["producto_id"],))
        if ultimo != pago_id:
            raise ValueError("Solo se puede eliminar el último pago de esta tarjeta/crédito.")
        if self._valor("SELECT COUNT(*) FROM refinanciaciones WHERE producto_id = ? AND fecha >= ?",
                       (pago["producto_id"], pago["fecha"])):
            raise ValueError("Hay una refinanciación posterior a este pago: elimínala primero.")
        with self.con:
            self.con.execute("DELETE FROM cuotas WHERE creada_por_pago = ?", (pago_id,))
            self.con.execute("UPDATE cuotas SET estado = 'pendiente', reemplazada_por_pago = NULL "
                             "WHERE reemplazada_por_pago = ?", (pago_id,))
            for a in self._todos("SELECT * FROM pagos_aplicacion WHERE pago_id = ?", (pago_id,)):
                self.con.execute(
                    "UPDATE cuotas SET pagado = pagado - ?, pagado_capital = pagado_capital - ?, "
                    "pagado_interes = pagado_interes - ?, pagado_otros = pagado_otros - ?, "
                    "pagado_mora = pagado_mora - ?, pagado_cobranza = pagado_cobranza - ? WHERE id = ?",
                    (a["monto"], a["a_capital"], a["a_interes"], a["a_otros"], a["a_mora"], a["a_cobranza"],
                     a["cuota_id"]))
            self._anular_mora_de_pago(pago_id)
            self._deshacer_ajustes(pago_id=pago_id)
            self._cambio("pago", pago_id, "eliminar", pago)
            self.con.execute("DELETE FROM pagos_credito WHERE id = ?", (pago_id,))
            self._actualizar_estados(pago["producto_id"])

    # ============================================================ refinanciación

    def deuda_para_refinanciar(self, producto_id: int, hoy: date | None = None,
                               credito_ids: list[int] | None = None) -> int:
        """Deuda total sugerida: pago total del extracto vigente o lo calculado por el cronograma.

        Con `credito_ids`, solo lo que cuesta cancelar hoy esas deudas.
        """
        hoy = hoy or date.today()
        if not credito_ids:
            return self.proximo_pago_producto(producto_id, hoy)["total"]
        pendientes = [c for c in self._cuotas_pendientes(producto_id=producto_id) if c["credito_id"] in credito_ids]
        limite = self._limite_ciclo(self.producto(producto_id), pendientes, hoy)
        mora = sum(f["monto"] for f in self._calcular_mora(producto_id, hoy) if f["credito_id"] in credito_ids)
        return self._total_para_cancelar(pendientes, limite, hoy) + mora

    def situacion_actual(self, producto_id: int, credito_ids: list[int] | None = None) -> dict:
        """Para comparar con una refinanciación: cómo se pagaría la deuda siguiendo el cronograma."""
        pendientes = self._cuotas_pendientes(producto_id=producto_id)
        if credito_ids:
            pendientes = [c for c in pendientes if c["credito_id"] in credito_ids]
            limite = self._limite_ciclo(self.producto(producto_id), pendientes, date.today())
            proximo = sum(self._pendiente(c) for c in pendientes if limite and _fecha(c["fecha"]) <= limite)
        else:
            proximo = self.proximo_pago_producto(producto_id, date.today())["minimo"]
        return {
            "proximo_pago": proximo,
            "meses": len({periodo(_fecha(c["fecha"])) for c in pendientes}),
            "costos": sum(self._pendiente(c) - self._capital_pendiente(c) for c in pendientes),
            "total": sum(self._pendiente(c) for c in pendientes),
            "ultima_fecha": _fecha(pendientes[-1]["fecha"]) if pendientes else None,
        }

    def simular_refinanciacion(self, producto_id: int, fecha: date, deuda_total: int, valor_pagado: int, n: int,
                               cuota: int | None, tasa_ea: float | None, saldo: int | None = None,
                               primera: date | None = None) -> credito.Refinanciacion:
        primera = primera or self.primera_fecha_pago(producto_id, fecha)
        return credito.analizar_refinanciacion(deuda_total, valor_pagado, n, primera, cuota=cuota, tasa_ea=tasa_ea,
                                               saldo=saldo, dia=self._dia_ancla(producto_id, primera))

    def registrar_refinanciacion(self, producto_id: int, fecha: date, r: credito.Refinanciacion,
                                 tipo: str = "refinanciacion", credito_ids: list[int] | None = None) -> int:
        """Refinanciación o acuerdo de pago (`tipo` = "acuerdo_pago").

        Reemplaza las deudas activas del producto, o solo las de `credito_ids`.
        """
        activas = [f["id"] for f in self._todos("SELECT id FROM creditos WHERE producto_id = ? AND estado = 'activo'",
                                                (producto_id,))]
        if credito_ids and any(i not in activas for i in credito_ids):
            raise ValueError("Elige deudas activas de esta tarjeta o crédito para organizar.")
        ids = list(credito_ids) if credito_ids else activas  # Puede estar vacío: deuda que solo está en el extracto.
        marcas = ", ".join("?" * len(ids)) or "NULL"
        with self.con:
            pago_id = None
            if r.valor_pagado > 0:
                pago_id = self.con.execute(
                    "INSERT INTO pagos_credito (fecha, producto_id, monto, tipo, a_costos, notas) "
                    "VALUES (?, ?, ?, 'refinanciacion', ?, 'Valor pagado para organizar la deuda')",
                    (_iso(fecha), producto_id, r.valor_pagado, r.valor_pagado)).lastrowid
            refi_id = self.con.execute(
                "INSERT INTO refinanciaciones (producto_id, fecha, deuda_total, valor_pagado, saldo, num_cuotas, "
                "cuota, tasa_ea, ea_implicita, pago_id, tipo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (producto_id, _iso(fecha), r.deuda_total, r.valor_pagado, r.saldo, r.n, r.cuota, r.tasa_ea_declarada,
                 r.ea_implicita, pago_id, tipo)).lastrowid
            self.con.execute(f"UPDATE cuotas SET estado = 'refinanciada' WHERE estado = 'pendiente' "
                             f"AND credito_id IN ({marcas})", ids)
            self.con.execute(f"UPDATE creditos SET estado = 'refinanciado', refinanciacion_id = ? "
                             f"WHERE id IN ({marcas})", (refi_id, *ids))
            dia = self._dia_ancla(producto_id, r.cronograma[0].fecha) if r.cronograma else None
            nuevo = self._crear_credito(producto_id, "refinanciacion", "Deuda organizada", fecha, r.saldo, r.n,
                                        credito.mv_a_ea(r.mv_usada), CUOTA_FIJA, r.cronograma, dia=dia)
            self.con.execute("UPDATE refinanciaciones SET credito_id = ? WHERE id = ?", (nuevo, refi_id))
        return refi_id

    def refinanciaciones(self, producto_id: int | None = None) -> list[sqlite3.Row]:
        sql = ("SELECT r.*, p.nombre AS producto FROM refinanciaciones r "
               "JOIN productos_credito p ON p.id = r.producto_id")
        if producto_id is not None:
            return self._todos(sql + " WHERE r.producto_id = ? ORDER BY r.fecha DESC", (producto_id,))
        return self._todos(sql + " ORDER BY r.fecha DESC")

    def eliminar_refinanciacion(self, refi_id: int) -> None:
        r = self._uno("SELECT * FROM refinanciaciones WHERE id = ?", (refi_id,))
        if r is None:
            return
        if r["credito_id"]:
            self._validar_credito_sin_movimientos(r["credito_id"])
        if self._valor("SELECT COUNT(*) FROM refinanciaciones WHERE producto_id = ? AND id > ?",
                       (r["producto_id"], refi_id)):
            raise ValueError("Hay una refinanciación posterior de esta tarjeta: elimínala primero.")
        with self.con:
            self._cambio("refinanciacion", refi_id, "eliminar", r)
            self.con.execute("DELETE FROM creditos WHERE id = ?", (r["credito_id"],))
            self.con.execute("UPDATE cuotas SET estado = 'pendiente' WHERE estado = 'refinanciada' AND credito_id IN "
                             "(SELECT id FROM creditos WHERE refinanciacion_id = ?)", (refi_id,))
            self.con.execute("UPDATE creditos SET estado = 'activo', refinanciacion_id = NULL "
                             "WHERE refinanciacion_id = ?", (refi_id,))
            self.con.execute("DELETE FROM refinanciaciones WHERE id = ?", (refi_id,))
            if r["pago_id"]:
                self.con.execute("DELETE FROM pagos_credito WHERE id = ?", (r["pago_id"],))
            self._actualizar_estados(r["producto_id"])

    # ============================================================ extractos

    def registrar_extracto(self, producto_id: int, fecha_corte: date, fecha_limite: date, capital_mes: int,
                           intereses: int, comisiones_avances: int = 0, comisiones_servicio: int = 0,
                           cargos_conversion: int = 0, abonos: int = 0, devoluciones: int = 0,
                           deuda_restante: int = 0) -> int:
        if fecha_limite <= fecha_corte:
            raise ValueError("La fecha límite de pago debe ser posterior a la fecha de corte")
        minimo = credito.pago_minimo_extracto(capital_mes, intereses, comisiones_avances, comisiones_servicio,
                                              cargos_conversion, abonos, devoluciones)
        with self.con:
            self.con.execute(
                "INSERT INTO extractos (producto_id, fecha_corte, fecha_limite, capital_mes, intereses, "
                "comisiones_avances, comisiones_servicio, cargos_conversion, abonos, devoluciones, pago_minimo, "
                "deuda_restante, pago_total) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(producto_id, fecha_corte) DO UPDATE SET fecha_limite = excluded.fecha_limite, "
                "capital_mes = excluded.capital_mes, intereses = excluded.intereses, "
                "comisiones_avances = excluded.comisiones_avances, comisiones_servicio = excluded.comisiones_servicio, "
                "cargos_conversion = excluded.cargos_conversion, abonos = excluded.abonos, "
                "devoluciones = excluded.devoluciones, pago_minimo = excluded.pago_minimo, "
                "deuda_restante = excluded.deuda_restante, pago_total = excluded.pago_total",
                (producto_id, _iso(fecha_corte), _iso(fecha_limite), capital_mes, intereses, comisiones_avances,
                 comisiones_servicio, cargos_conversion, abonos, devoluciones, minimo, deuda_restante,
                 minimo + deuda_restante))
            ext = self._uno("SELECT * FROM extractos WHERE producto_id = ? AND fecha_corte = ?",
                            (producto_id, _iso(fecha_corte)))
            self._conciliar_extracto(ext)
            self._actualizar_estados(producto_id)
            return ext["id"]

    def _conciliar_extracto(self, ext: sqlite3.Row) -> None:
        """Ajusta el interés de las cuotas del ciclo al interés real del extracto.

        El banco liquida el interés por días; el cronograma, por mes completo. Sin este
        ajuste, pagar el mínimo del extracto dejaría parte de la cuota «vencida» y con
        mora. Solo cambia cuotas pendientes del ciclo (después del corte y hasta la
        fecha límite) y guarda el valor anterior para poder deshacerlo.
        """
        self._deshacer_ajustes(extracto_id=ext["id"])
        cuotas = self._todos(
            "SELECT cu.* FROM cuotas cu JOIN creditos cr ON cr.id = cu.credito_id WHERE cr.producto_id = ? "
            "AND cr.estado IN ('activo', 'pagado') AND cu.estado IN ('pendiente', 'pagada') AND cu.fecha > ? "
            "AND cu.fecha <= ? ORDER BY cu.fecha, cu.id", (ext["producto_id"], ext["fecha_corte"], ext["fecha_limite"]))
        pendientes = [c for c in cuotas if c["estado"] == "pendiente"]
        if not pendientes:
            return
        objetivo = ext["intereses"] - sum(c["interes"] for c in cuotas if c["estado"] == "pagada")
        actual = sum(c["interes"] for c in pendientes)
        if objetivo < 0 or objetivo == actual:
            return
        base = [c["interes"] for c in pendientes] if actual else [c["capital"] for c in pendientes]
        if not sum(base):
            return
        acumulado = 0
        for i, c in enumerate(pendientes):
            valor = objetivo - acumulado if i == len(pendientes) - 1 else objetivo * base[i] // sum(base)
            acumulado += valor
            valor = max(valor, c["pagado_interes"])
            if valor != c["interes"]:
                self.con.execute("UPDATE cuotas SET interes = ? WHERE id = ?", (valor, c["id"]))
                self.con.execute("INSERT INTO ajustes_cuota (cuota_id, campo, antes, despues, motivo, extracto_id) "
                                 "VALUES (?, 'interes', ?, ?, 'extracto', ?)", (c["id"], c["interes"], valor, ext["id"]))

    def extractos(self, producto_id: int | None = None) -> list[sqlite3.Row]:
        sql = "SELECT e.*, p.nombre AS producto FROM extractos e JOIN productos_credito p ON p.id = e.producto_id"
        if producto_id is not None:
            return self._todos(sql + " WHERE e.producto_id = ? ORDER BY e.fecha_corte DESC", (producto_id,))
        return self._todos(sql + " ORDER BY e.fecha_corte DESC")

    def ultimo_extracto(self, producto_id: int) -> sqlite3.Row | None:
        return self._uno("SELECT * FROM extractos WHERE producto_id = ? ORDER BY fecha_corte DESC LIMIT 1",
                         (producto_id,))

    def extracto_vigente(self, producto_id: int, hoy: date) -> sqlite3.Row | None:
        """Último extracto cuya fecha límite no ha pasado y que no fue reemplazado por una refinanciación."""
        ext = self.ultimo_extracto(producto_id)
        if ext is None or _fecha(ext["fecha_limite"]) < hoy:
            return None
        if self._valor("SELECT COUNT(*) FROM refinanciaciones WHERE producto_id = ? AND fecha > ?",
                       (producto_id, ext["fecha_corte"])):
            return None
        return ext

    def eliminar_extracto(self, id_: int) -> None:
        ext = self._uno("SELECT * FROM extractos WHERE id = ?", (id_,))
        if ext is None:
            return
        with self.con:
            self._deshacer_ajustes(extracto_id=id_)
            self._cambio("extracto", id_, "eliminar", ext)
            self.con.execute("DELETE FROM extractos WHERE id = ?", (id_,))
            self._actualizar_estados(ext["producto_id"])

    # ============================================================ reserva (Cajita)

    def saldo_reserva(self, hasta: date | None = None) -> int:
        if hasta:
            return self._valor("SELECT SUM(monto) FROM reserva_movimientos WHERE fecha <= ?", (_iso(hasta),))
        return self._valor("SELECT SUM(monto) FROM reserva_movimientos")

    def movimiento_reserva(self, fecha: date, tipo: str, monto: int, notas: str = "") -> int:
        if monto <= 0:
            raise ValueError("El monto debe ser mayor que cero")
        if SIGNO_RESERVA[tipo] < 0 and self.saldo_reserva() < monto:
            raise ValueError(f"La reserva tiene {formato(max(0, self.saldo_reserva()))}: no alcanza para ese "
                             f"{'retiro' if tipo == 'retiro' else 'uso'}.")
        with self.con:
            return self.con.execute("INSERT INTO reserva_movimientos (fecha, tipo, monto, notas) VALUES (?, ?, ?, ?)",
                                    (_iso(fecha), tipo, SIGNO_RESERVA[tipo] * monto, notas)).lastrowid

    def movimientos_reserva(self) -> list[sqlite3.Row]:
        return self._todos("SELECT * FROM reserva_movimientos ORDER BY fecha DESC, id DESC")

    def eliminar_movimiento_reserva(self, id_: int) -> None:
        mov = self._uno("SELECT * FROM reserva_movimientos WHERE id = ?", (id_,))
        if mov and mov["pago_id"]:
            raise ValueError("Este movimiento viene de un pago de tarjeta: elimina el pago.")
        if mov and mov["compra_id"]:
            raise ValueError("Este movimiento viene del pago de un servicio: elimina esa compra en «Ingresos y "
                             "compras».")
        with self.con:
            self._cambio("reserva", id_, "eliminar", mov)
            self.con.execute("DELETE FROM reserva_movimientos WHERE id = ?", (id_,))

    def rendimiento_reserva_estimado(self) -> int:
        """Rendimiento mensual aproximado de la Cajita con el saldo actual."""
        tasa = self.config_num("tasa_cajita_ea")
        return round(max(0, self.saldo_reserva()) * credito.ea_a_mv(tasa)) if tasa else 0

    # ============================================================ cajas de ahorro

    def metas_ahorro(self, incluir_archivadas: bool = False) -> list[dict]:
        filtro = "" if incluir_archivadas else "WHERE m.estado != 'archivada'"
        filas = self._todos(
            "SELECT m.*, COALESCE((SELECT SUM(monto) FROM ahorro_movimientos a WHERE a.meta_id = m.id), 0) "
            f"AS ahorrado FROM metas_ahorro m {filtro} "
            "ORDER BY m.estado = 'archivada', m.estado = 'pausada', m.prioridad, "
            "COALESCE(m.fecha_objetivo, '9999-12-31'), m.id")
        return [dict(f) for f in filas]

    def meta_ahorro(self, id_: int) -> dict:
        m = next((m for m in self.metas_ahorro(True) if m["id"] == id_), None)
        if m is None:
            raise ValueError("La caja de ahorro no existe")
        return m

    def guardar_meta_ahorro(self, id_: int | None, nombre: str, tipo: str, objetivo: int,
                            fecha_objetivo: date | None = None, prioridad: int = 2, estado: str = "activa",
                            notas: str = "") -> int:
        if not nombre.strip():
            raise ValueError("Ponle un nombre a la caja")
        if objetivo <= 0:
            raise ValueError("La meta debe ser mayor que cero")
        if prioridad not in PESO_PRIORIDAD:
            raise ValueError("Prioridad inválida")
        datos = (nombre.strip(), tipo, objetivo, _iso(fecha_objetivo), prioridad, estado, notas)
        with self.con:
            if id_ is None:
                return self.con.execute(
                    "INSERT INTO metas_ahorro (nombre, tipo, objetivo, fecha_objetivo, prioridad, estado, notas, "
                    "creada) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", datos + (_iso(date.today()),)).lastrowid
            antes = self._uno("SELECT * FROM metas_ahorro WHERE id = ?", (id_,))
            self.con.execute("UPDATE metas_ahorro SET nombre = ?, tipo = ?, objetivo = ?, fecha_objetivo = ?, "
                             "prioridad = ?, estado = ?, notas = ? WHERE id = ?", datos + (id_,))
            self._cambio("meta_ahorro", id_, "editar", antes, dict(zip(
                ("nombre", "tipo", "objetivo", "fecha_objetivo", "prioridad", "estado", "notas"), datos)))
            return id_

    def eliminar_meta_ahorro(self, id_: int) -> None:
        m = self.meta_ahorro(id_)
        if m["ahorrado"] != 0:
            raise ValueError(f"La caja «{m['nombre']}» tiene {formato(m['ahorrado'])}: retíralos antes de "
                             "eliminarla, o archívala.")
        with self.con:
            self._cambio("meta_ahorro", id_, "eliminar", m)
            self.con.execute("DELETE FROM metas_ahorro WHERE id = ?", (id_,))

    def abonar_meta(self, meta_id: int, fecha: date, monto: int, externo: bool = False, notas: str = "") -> int:
        """Abono a una caja. `externo`: plata que ya tenías ahorrada (no sale del disponible)."""
        if monto <= 0:
            raise ValueError("El monto debe ser mayor que cero")
        self.meta_ahorro(meta_id)
        with self.con:
            return self.con.execute(
                "INSERT INTO ahorro_movimientos (meta_id, fecha, tipo, monto, externo, notas) "
                "VALUES (?, ?, 'abono', ?, ?, ?)", (meta_id, _iso(fecha), monto, int(externo), notas)).lastrowid

    def retirar_meta(self, meta_id: int, fecha: date, monto: int, notas: str = "",
                     compra: tuple[str, int | None] | None = None) -> int:
        """Saca plata de una caja (vuelve al disponible).

        `compra` = (descripción, categoría): además registra la compra en efectivo, para cuando
        el retiro es para comprar lo que se estaba ahorrando.
        """
        if monto <= 0:
            raise ValueError("El monto debe ser mayor que cero")
        m = self.meta_ahorro(meta_id)
        if m["ahorrado"] < monto:
            raise ValueError(f"La caja «{m['nombre']}» tiene {formato(max(0, m['ahorrado']))}: no alcanza.")
        with self.con:
            compra_id = None
            if compra:
                compra_id = self.con.execute(
                    "INSERT INTO compras (fecha, descripcion, categoria_id, monto, medio) "
                    "VALUES (?, ?, ?, ?, 'efectivo')", (_iso(fecha), compra[0] or m["nombre"], compra[1],
                                                       monto)).lastrowid
            return self.con.execute(
                "INSERT INTO ahorro_movimientos (meta_id, fecha, tipo, monto, compra_id, notas) "
                "VALUES (?, ?, 'retiro', ?, ?, ?)", (meta_id, _iso(fecha), -monto, compra_id, notas)).lastrowid

    def movimientos_ahorro(self, meta_id: int | None = None) -> list[sqlite3.Row]:
        sql = ("SELECT a.*, m.nombre AS meta FROM ahorro_movimientos a JOIN metas_ahorro m ON m.id = a.meta_id")
        if meta_id is not None:
            return self._todos(sql + " WHERE a.meta_id = ? ORDER BY a.fecha DESC, a.id DESC", (meta_id,))
        return self._todos(sql + " ORDER BY a.fecha DESC, a.id DESC")

    def eliminar_movimiento_ahorro(self, id_: int) -> None:
        """Elimina un abono o retiro (y la compra que registró el retiro, si la hay)."""
        mov = self._uno("SELECT * FROM ahorro_movimientos WHERE id = ?", (id_,))
        if mov is None:
            return
        if mov["tipo"] == "abono" and self._valor("SELECT SUM(monto) FROM ahorro_movimientos WHERE meta_id = ?",
                                                  (mov["meta_id"],)) < mov["monto"]:
            raise ValueError("Esa plata ya se retiró de la caja: elimina primero el retiro.")
        with self.con:
            self._cambio("ahorro", id_, "eliminar", mov)
            self.con.execute("DELETE FROM ahorro_movimientos WHERE id = ?", (id_,))
            if mov["compra_id"]:
                self.con.execute("DELETE FROM compras WHERE id = ?", (mov["compra_id"],))

    def total_ahorrado(self, hasta: date | None = None) -> int:
        if hasta:
            return self._valor("SELECT SUM(monto) FROM ahorro_movimientos WHERE fecha <= ?", (_iso(hasta),))
        return self._valor("SELECT SUM(monto) FROM ahorro_movimientos")

    # ------------------------------------------------------------ gastos previstos

    def gastos_previstos(self, per: str) -> list[sqlite3.Row]:
        return self._todos("SELECT * FROM gastos_previstos WHERE periodo = ? ORDER BY id", (per,))

    def guardar_gasto_previsto(self, id_: int | None, per: str, descripcion: str, monto: int) -> None:
        if not descripcion.strip():
            raise ValueError("Escribe qué gasto es")
        if monto <= 0:
            raise ValueError("El monto debe ser mayor que cero")
        with self.con:
            if id_ is None:
                self.con.execute("INSERT INTO gastos_previstos (periodo, descripcion, monto) VALUES (?, ?, ?)",
                                 (per, descripcion.strip(), monto))
            else:
                self.con.execute("UPDATE gastos_previstos SET periodo = ?, descripcion = ?, monto = ? WHERE id = ?",
                                 (per, descripcion.strip(), monto, id_))

    def eliminar_gasto_previsto(self, id_: int) -> None:
        with self.con:
            self.con.execute("DELETE FROM gastos_previstos WHERE id = ?", (id_,))

    # ------------------------------------------------------------ disponible, saldo a favor y patrimonio

    def saldo_disponible(self, hasta: date | None = None) -> int:
        """Plata libre en tu cuenta/bolsillo al final del día `hasta` (por defecto, hoy).

        = ingresos − salidas de bolsillo (compras en efectivo, cuotas iniciales, pagos de deuda)
          − lo apartado en la reserva (los pagos hechos desde la reserva no salen del bolsillo)
          − lo abonado a las cajas (salvo la plata que ya tenías ahorrada) + ajustes.
        """
        f = _iso(hasta or date.today())
        entro = self._valor("SELECT SUM(monto) FROM ingresos WHERE fecha <= ?", (f,))
        compras = self._valor("SELECT SUM(CASE WHEN medio = 'efectivo' THEN monto ELSE cuota_inicial END) "
                              "FROM compras WHERE fecha <= ?", (f,))
        pagos = self._valor("SELECT SUM(monto) FROM pagos_credito WHERE fecha <= ? "
                            "AND tipo NOT IN ('devolucion', 'saldo_favor')", (f,))
        reserva = self._valor("SELECT SUM(monto) FROM reserva_movimientos WHERE fecha <= ? "
                              "AND tipo != 'rendimiento'", (f,))
        cajas = self._valor("SELECT SUM(monto) FROM ahorro_movimientos WHERE fecha <= ? AND externo = 0", (f,))
        ajustes = self._valor("SELECT SUM(monto) FROM ajustes_disponible WHERE fecha <= ?", (f,))
        return entro - compras - pagos - reserva - cajas + ajustes

    def saldo_favor_mes(self, per: str) -> int:
        """Lo que quedó al cerrar el mes anterior a `per` (lo que se trae al mes)."""
        return self.saldo_disponible(inicio_periodo(per) - timedelta(days=1))

    def ajustar_disponible(self, fecha: date, saldo_real: int, notas: str = "") -> int:
        """Registra la diferencia para que el disponible en `fecha` sea `saldo_real`. Devuelve el ajuste."""
        diferencia = saldo_real - self.saldo_disponible(fecha)
        if diferencia:
            with self.con:
                self.con.execute("INSERT INTO ajustes_disponible (fecha, monto, notas) VALUES (?, ?, ?)",
                                 (_iso(fecha), diferencia, notas or "Ajuste para cuadrar con la cuenta"))
        return diferencia

    def flujo_mes(self, per: str) -> dict:
        """Cómo se movió el disponible en el mes: saldo a favor + entró − salió − ahorrado = disponible."""
        r = self.resumen_mes(per)
        params = (per,)
        reserva = self._valor("SELECT SUM(monto) FROM reserva_movimientos WHERE substr(fecha, 1, 7) = ? "
                              "AND tipo != 'rendimiento'", params)
        cajas = self._valor("SELECT SUM(monto) FROM ahorro_movimientos WHERE substr(fecha, 1, 7) = ? "
                            "AND externo = 0", params)
        ajustes = self._valor("SELECT SUM(monto) FROM ajustes_disponible WHERE substr(fecha, 1, 7) = ?", params)
        inicial = self.saldo_favor_mes(per)
        final = inicial + r["entro"] - r["salio"] - reserva - cajas + ajustes
        return {"saldo_favor": inicial, "entro": r["entro"], "salio": r["salio"], "a_reserva": reserva,
                "a_cajas": cajas, "ajustes": ajustes, "disponible": final, "resultado": final - inicial}

    def patrimonio(self, hasta: date | None = None, deuda: int | None = None) -> dict:
        """Lo que tienes (disponible + reserva + cajas) menos lo que debes."""
        hoy = hasta or date.today()
        disponible = self.saldo_disponible(hoy)
        reserva = self.saldo_reserva(hoy)
        cajas = self.total_ahorrado(hoy)
        deuda = self.deuda_total() if deuda is None else deuda
        return {"disponible": disponible, "reserva": reserva, "cajas": cajas, "deuda": deuda,
                "activos": disponible + reserva + cajas, "patrimonio": disponible + reserva + cajas - deuda}

    def historial_patrimonio(self, meses: int = 6, hoy: date | None = None) -> list[dict]:
        """Patrimonio al cierre de cada mes (el mes actual, a hoy). Más antiguo primero."""
        hoy = hoy or date.today()
        per = periodo(hoy)
        filas = []
        for k in range(meses - 1, -1, -1):
            p = periodo_siguiente(per, -k)
            if k == 0:
                fila = self.patrimonio(hoy)
            else:
                cierre = self._uno("SELECT deuda_total FROM cierres_mensuales WHERE periodo = ?", (p,))
                fin = fin_periodo(p)
                fila = self.patrimonio(fin, cierre["deuda_total"] if cierre else self.deuda_a_fecha(fin))
            fila["periodo"] = p
            filas.append(fila)
        return filas

    # ------------------------------------------------------------ plan de ahorro

    def metas_para_reparto(self) -> list[Meta]:
        return [Meta(id=m["id"], nombre=m["nombre"], objetivo=m["objetivo"], ahorrado=m["ahorrado"],
                     fecha_objetivo=_fecha(m["fecha_objetivo"]) if m["fecha_objetivo"] else None,
                     prioridad=m["prioridad"])
                for m in self.metas_ahorro() if m["estado"] == "activa"]

    def entrada_ahorro(self, per: str | None = None, hoy: date | None = None) -> EntradaAhorro:
        """Datos para calcular cuánto se puede ahorrar en el mes `per` (por defecto, el siguiente)."""
        hoy = hoy or date.today()
        per = per or periodo_siguiente(periodo(hoy))
        desde, hasta = inicio_periodo(per), fin_periodo(per)
        ingreso = self.ingreso_mensual_estimado(hoy)
        pagos = self.total_programado(desde, hasta)
        nivel = nivel_endeudamiento(ratio_endeudamiento(pagos, ingreso), self.config_plan())
        pct_ahorro, pct_abono, _ = self.config_plan().reparto[nivel]
        if self.deuda_total() == 0:
            pct_ahorro += pct_abono  # Sin deuda, el abono extra también va al ahorro.
        sig = periodo_siguiente(periodo(hoy))
        falta_reserva = max(0, self.meta_mes_adelantado(sig) - max(0, self.saldo_reserva()))
        return EntradaAhorro(
            periodo=per, ingreso=ingreso, pagos_deuda=pagos,
            servicios=sum(s["monto"] for s in self.servicios_pendientes(desde, hasta)),
            dia_a_dia=self.dia_a_dia_mensual(hoy),
            gastos_previstos=self._valor("SELECT SUM(monto) FROM gastos_previstos WHERE periodo = ?", (per,)),
            pct_ahorro=pct_ahorro, saldo_favor=max(0, self.saldo_favor_mes(periodo(hoy))),
            falta_reserva=falta_reserva,
            fechas_ingreso=fechas_pago_en_mes(desde.year, desde.month, self.dias_pago()) if self.fuentes("activa")
            else [],
        )

    def plan_ahorro(self, per: str | None = None, hoy: date | None = None
                    ) -> tuple[CapacidadAhorro, list[Asignacion]]:
        cap = capacidad_ahorro(self.entrada_ahorro(per, hoy))
        return cap, repartir(cap.sugerido, self.metas_para_reparto(), cap.entrada.periodo)

    # ============================================================ tasas legales

    def tasas_legales(self) -> list[sqlite3.Row]:
        return self._todos("SELECT * FROM tasas_legales ORDER BY desde DESC, modalidad")

    def guardar_tasa_legal(self, id_: int | None, modalidad: str, desde: date, hasta: date, usura_ea: float,
                           ibc_ea: float | None = None, notas: str = "") -> None:
        if hasta < desde:
            raise ValueError("La fecha final debe ser igual o posterior a la inicial")
        if usura_ea <= 0:
            raise ValueError("La tasa de usura debe ser mayor que cero")
        solapada = self._valor("SELECT COUNT(*) FROM tasas_legales WHERE modalidad = ? AND id IS NOT ? "
                               "AND desde <= ? AND hasta >= ?", (modalidad, id_, _iso(hasta), _iso(desde)))
        if solapada:
            raise ValueError("Ya hay una tasa registrada para esa modalidad en parte de ese periodo")
        datos = (modalidad, _iso(desde), _iso(hasta), ibc_ea, usura_ea, notas)
        with self.con:
            antes = self._uno("SELECT * FROM tasas_legales WHERE id = ?", (id_,)) if id_ is not None else None
            self._cambio("tasa_legal", id_, "editar" if antes else "crear", antes,
                         dict(zip(("modalidad", "desde", "hasta", "ibc_ea", "usura_ea", "notas"), datos)))
            if id_ is None:
                self.con.execute("INSERT INTO tasas_legales (modalidad, desde, hasta, ibc_ea, usura_ea, notas) "
                                 "VALUES (?, ?, ?, ?, ?, ?)", datos)
            else:
                self.con.execute("UPDATE tasas_legales SET modalidad = ?, desde = ?, hasta = ?, ibc_ea = ?, "
                                 "usura_ea = ?, notas = ? WHERE id = ?", datos + (id_,))

    def eliminar_tasa_legal(self, id_: int) -> None:
        with self.con:
            self._cambio("tasa_legal", id_, "eliminar", self._uno("SELECT * FROM tasas_legales WHERE id = ?", (id_,)))
            self.con.execute("DELETE FROM tasas_legales WHERE id = ?", (id_,))

    def usura_vigente(self, fecha: date, modalidad: str = "consumo") -> float | None:
        """Usura certificada para la fecha y modalidad; si no hay registro, la de Configuración (si existe)."""
        fila = self._uno("SELECT usura_ea FROM tasas_legales WHERE modalidad = ? AND desde <= ? AND hasta >= ? "
                         "ORDER BY desde DESC LIMIT 1", (modalidad, _iso(fecha), _iso(fecha)))
        if fila:
            return fila["usura_ea"]
        respaldo = self.config_num("tasa_usura_ea")
        return respaldo or None

    # ============================================================ mora y cobranza

    def _tasa_mora(self, cond: dict, fecha: date) -> float:
        """Tasa moratoria pactada, limitada a la usura del periodo; sin tasa pactada, la usura."""
        usura = self.usura_vigente(fecha, cond.get("modalidad_legal", "consumo"))
        pactada = cond["mora"].get("tasa_ea")
        if pactada is None:
            return usura or 0.0
        return min(float(pactada), usura) if usura else float(pactada)

    def _calcular_mora(self, producto_id: int | None, hasta: date, credito_id: int | None = None) -> list[dict]:
        """Intereses de mora y gastos de cobranza aún no liquidados hasta `hasta` (no guarda nada)."""
        filas = []
        grupos: dict[int, list[sqlite3.Row]] = defaultdict(list)
        for c in self._cuotas_pendientes(producto_id=producto_id, credito_id=credito_id):
            grupos[c["credito_id"]].append(c)
        for cid, cuotas in grupos.items():
            cond = cond_mod.de_credito(cuotas[0])
            vencidas = [c for c in cuotas if _fecha(c["fecha"]) < hasta and self._pendiente(c) > 0]
            for c in vencidas:
                capital = self._capital_pendiente(c)
                desde = max(_fecha(c["fecha"]), _fecha(c["mora_hasta"])) if c["mora_hasta"] else _fecha(c["fecha"])
                for a, b in _tramos_mensuales(desde, hasta):
                    tasa = self._tasa_mora(cond, a)
                    monto = credito.interes_mora(capital, tasa, (b - a).days)
                    if monto:
                        filas.append({"tipo": "mora", "credito_id": cid, "cuota_id": c["id"], "clave": f"{c['id']}:{a}",
                                      "desde": a, "hasta": b, "base": capital, "tasa_ea": tasa, "monto": monto})
            if not vencidas:
                continue
            antigua = vencidas[0]
            inicio = self._inicio_episodio_mora(cid, _fecha(antigua["fecha"]))
            dias = (hasta - inicio).days
            vencido = sum(self._pendiente(c) for c in vencidas)
            for i, regla in enumerate(cond_mod.reglas_cobranza(cond)):
                for k in range(regla.periodos(dias)):
                    clave = f"r{i}:{_iso(inicio)}:{k}"
                    if self._uno("SELECT 1 FROM cargos_mora WHERE credito_id = ? AND tipo = 'cobranza' AND clave = ?",
                                 (cid, clave)):
                        continue
                    filas.append({"tipo": "cobranza", "credito_id": cid, "cuota_id": antigua["id"], "clave": clave,
                                  "desde": inicio, "hasta": hasta, "base": vencido, "tasa_ea": None,
                                  "monto": regla.monto(vencido)})
        return filas

    def _inicio_episodio_mora(self, credito_id: int, inicio: date) -> date:
        """Fecha en que empezó el atraso continuo que incluye a la cuota que venció en `inicio`.

        Una cuota anterior que se terminó de pagar después de `inicio` seguía vencida
        cuando esta venció: es el mismo episodio (la cobranza «única» no se repite).
        """
        while True:
            previa = self._uno(
                "SELECT cu.fecha FROM cuotas cu WHERE cu.credito_id = ? AND cu.fecha < ? AND cu.estado = 'pagada' "
                "AND (SELECT MAX(pc.fecha) FROM pagos_aplicacion pa JOIN pagos_credito pc ON pc.id = pa.pago_id "
                "WHERE pa.cuota_id = cu.id) > ? ORDER BY cu.fecha LIMIT 1", (credito_id, _iso(inicio), _iso(inicio)))
            if previa is None:
                return inicio
            inicio = _fecha(previa["fecha"])

    def _revertir_mora_posterior(self, producto_id: int, fecha: date) -> None:
        """Antes de un pago con fecha anterior a una mora ya liquidada, deshace esa mora.

        Solo se deshace la liquidada con «Liquidar mora a hoy» y aún no pagada; así la
        mora se vuelve a calcular hasta la fecha real del pago. Si la liquidó un pago
        posterior, hay que registrar los pagos en orden.
        """
        filas = self._todos(
            "SELECT cm.*, pc.fecha AS fecha_pago FROM cargos_mora cm JOIN creditos cr ON cr.id = cm.credito_id "
            "LEFT JOIN pagos_credito pc ON pc.id = cm.pago_id WHERE cr.producto_id = ? AND cm.hasta > ?",
            (producto_id, _iso(fecha)))
        if not filas:
            return
        for f in filas:
            if f["pago_id"] is not None:
                raise ValueError(f"El pago del {f['fecha_pago']} ya liquidó mora después de esta fecha. Elimina los "
                                 "pagos posteriores y regístralos en orden de fecha.")
        por_cuota: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for f in filas:
            por_cuota[f["cuota_id"]][f["tipo"]] += f["monto"]
        for cuota_id, tipos in por_cuota.items():
            cu = self._uno("SELECT * FROM cuotas WHERE id = ?", (cuota_id,))
            if any(cu[t] - cu[PAGADO[t]] < monto for t, monto in tipos.items()):
                raise ValueError("La mora liquidada después de esta fecha ya fue pagada: elimina los pagos "
                                 "posteriores y regístralos en orden de fecha.")
        for f in filas:
            self.con.execute(f"UPDATE cuotas SET {f['tipo']} = {f['tipo']} - ? WHERE id = ?", (f["monto"], f["cuota_id"]))
            self.con.execute("DELETE FROM cargos_mora WHERE id = ?", (f["id"],))
        for cuota_id in por_cuota:
            ultimo = self._uno("SELECT MAX(hasta) AS h FROM cargos_mora WHERE cuota_id = ? AND tipo = 'mora'",
                               (cuota_id,))
            self.con.execute("UPDATE cuotas SET mora_hasta = ? WHERE id = ?", (ultimo["h"], cuota_id))

    def _liquidar_mora(self, producto_id: int | None, hasta: date, pago_id: int | None = None,
                       credito_id: int | None = None) -> int:
        """Guarda la mora y cobranza pendientes de liquidar; devuelve el total liquidado."""
        total = 0
        for f in self._calcular_mora(producto_id, hasta, credito_id):
            cur = self.con.execute(
                "INSERT OR IGNORE INTO cargos_mora (credito_id, cuota_id, tipo, clave, desde, hasta, base, tasa_ea, "
                "monto, pago_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f["credito_id"], f["cuota_id"], f["tipo"], f["clave"], _iso(f["desde"]), _iso(f["hasta"]), f["base"],
                 f["tasa_ea"], f["monto"], pago_id))
            if cur.rowcount:
                self.con.execute(f"UPDATE cuotas SET {f['tipo']} = {f['tipo']} + ? WHERE id = ?",
                                 (f["monto"], f["cuota_id"]))
                total += f["monto"]
        for c in self._cuotas_pendientes(producto_id=producto_id, credito_id=credito_id):
            if _fecha(c["fecha"]) < hasta and (not c["mora_hasta"] or c["mora_hasta"] < _iso(hasta)):
                self.con.execute("UPDATE cuotas SET mora_hasta = ? WHERE id = ?", (_iso(hasta), c["id"]))
        return total

    def liquidar_mora(self, hasta: date, producto_id: int | None = None) -> int:
        with self.con:
            return self._liquidar_mora(producto_id, hasta)

    def _anular_mora_de_pago(self, pago_id: int) -> None:
        """Deshace la mora y cobranza liquidadas al registrar un pago que se elimina."""
        for f in self._todos("SELECT * FROM cargos_mora WHERE pago_id = ?", (pago_id,)):
            self.con.execute(f"UPDATE cuotas SET {f['tipo']} = {f['tipo']} - ? WHERE id = ?", (f["monto"], f["cuota_id"]))
        cuotas = {f["cuota_id"] for f in self._todos("SELECT cuota_id FROM cargos_mora WHERE pago_id = ?", (pago_id,))}
        self.con.execute("DELETE FROM cargos_mora WHERE pago_id = ?", (pago_id,))
        for cuota_id in cuotas:
            ultimo = self._uno("SELECT MAX(hasta) AS h FROM cargos_mora WHERE cuota_id = ? AND tipo = 'mora'",
                               (cuota_id,))
            self.con.execute("UPDATE cuotas SET mora_hasta = ? WHERE id = ?", (ultimo["h"], cuota_id))

    def estado_mora(self, hoy: date | None = None) -> list[dict]:
        """Cuotas vencidas con días de mora, lo pendiente, la mora liquidada y la que se causaría a hoy."""
        hoy = hoy or date.today()
        nuevas: dict[int, int] = defaultdict(int)
        for f in self._calcular_mora(None, hoy):
            nuevas[f["cuota_id"]] += f["monto"]
        nombres = {p["id"]: p["nombre"] for p in self.productos(False)}
        filas = []
        for c in self._cuotas_pendientes():
            if _fecha(c["fecha"]) >= hoy or self._pendiente(c) <= 0:
                continue
            filas.append({"cuota": c, "producto": nombres.get(c["producto_id"], ""),
                          "descripcion": c["credito_descripcion"], "dias": (hoy - _fecha(c["fecha"])).days,
                          "capital": self._capital_pendiente(c), "pendiente": self._pendiente(c),
                          "mora_liquidada": max(0, c["mora"] - c["pagado_mora"]),
                          "cobranza_liquidada": max(0, c["cobranza"] - c["pagado_cobranza"]),
                          "por_liquidar": nuevas.get(c["id"], 0)})
        return filas

    # ============================================================ costo de un crédito

    def condiciones_credito(self, credito_id: int) -> dict:
        return cond_mod.de_credito(self._uno("SELECT * FROM creditos WHERE id = ?", (credito_id,)))

    def costo_credito(self, credito_id: int) -> credito.CostoFinanciacion:
        """Costo total con el cronograma vigente (incluye mora y cobranza liquidadas como cargos)."""
        cr = self._uno("SELECT * FROM creditos WHERE id = ?", (credito_id,))
        cond = cond_mod.de_credito(cr)
        cuotas = []
        for c in self.cronograma_credito(credito_id):
            if c["estado"] == "refinanciada" and not c["pagado"]:
                continue
            detalle = _detalle(c)
            if c["mora"]:
                detalle["Intereses de mora"] = c["mora"]
            if c["cobranza"]:
                detalle["Gastos de cobranza"] = c["cobranza"]
            cuotas.append(credito.Cuota(c["numero"], _fecha(c["fecha"]), c["capital"], c["interes"],
                                        c["otros"] + c["mora"] + c["cobranza"], 0, detalle))
        capital = sum(c.capital for c in cuotas)
        precio_financiado = (cr["cuota_inicial"] or 0) + capital if cr["origen"] == "compra" else None
        # Lo devuelto deja de ser parte de la compra: se descuenta del precio de contado.
        devuelto = self._valor("SELECT SUM(monto) FROM pagos_credito WHERE credito_id = ? AND tipo = 'devolucion'",
                               (credito_id,))
        precio_contado = max(0, cr["precio_contado"] - devuelto) if cr["precio_contado"] else None
        return credito.costo_financiacion(cuotas, _fecha(cr["fecha"]), capital, cond_mod.tasa_ea(cond),
                                          precio_contado, precio_financiado, cr["cuota_inicial"] or 0,
                                          cr["cargos_iniciales"] or 0, cond_mod.cargos(cond))

    def alertas_usura(self) -> list[dict]:
        """Deudas activas cuya tasa (pactada, según la cuota o con cargos marcados como interés) supera la usura.

        Compara con la usura registrada para la fecha del crédito. No hace afirmaciones
        legales: solo compara las cifras registradas.
        """
        alertas = []
        for d in self.creditos():
            cr = d["credito"]
            cond = cond_mod.de_credito(cr)
            usura = self.usura_vigente(_fecha(cr["fecha"]), cond.get("modalidad_legal", "consumo"))
            if not usura:
                continue
            pactada = cond_mod.tasa_ea(cond)
            segun_cuota = cond.get("tasa_segun_cuota_ea") or 0.0
            con_cargos = self.costo_credito(cr["id"]).tasa_ea_interes or 0.0
            if pactada > usura:
                motivo, valor = "tasa pactada", pactada
            elif segun_cuota > usura:
                motivo, valor = "tasa según el valor de la cuota", segun_cuota
            elif con_cargos > usura + 0.01:
                motivo, valor = "intereses más cargos que según tu contrato cuentan como interés", con_cargos
            else:
                continue
            alertas.append({"credito": cr, "producto": cr["producto"], "motivo": motivo, "tasa": valor,
                            "usura": usura})
        return alertas

    def creditos_terminados(self, per: str) -> list[dict]:
        """Deudas que se terminaron de pagar en el mes `per`."""
        filas = self._todos(
            "SELECT cr.id, cr.descripcion, p.nombre AS producto, (SELECT MAX(pc.fecha) FROM pagos_credito pc "
            "WHERE pc.id IN (SELECT pa.pago_id FROM pagos_aplicacion pa JOIN cuotas cu ON cu.id = pa.cuota_id "
            "WHERE cu.credito_id = cr.id UNION SELECT cu.reemplazada_por_pago FROM cuotas cu "
            "WHERE cu.credito_id = cr.id)) AS fin FROM creditos cr JOIN productos_credito p ON p.id = cr.producto_id "
            "WHERE cr.estado = 'pagado'")
        return [dict(f) for f in filas if f["fin"] and f["fin"][:7] == per]

    # ============================================================ saldos históricos

    def deuda_a_fecha(self, fecha: date, producto_id: int | None = None, credito_id: int | None = None) -> int:
        """Capital que se debía al final del día `fecha`, reconstruido con el historial de pagos.

        Cuenta las cuotas que existían en esa fecha (creadas antes y no reemplazadas
        por un abono ni refinanciadas todavía) menos el capital que se les había aplicado.
        """
        f = _iso(fecha)
        sql = (
            "SELECT COALESCE(SUM(cu.capital - COALESCE((SELECT SUM(pa.a_capital) FROM pagos_aplicacion pa "
            "JOIN pagos_credito pc ON pc.id = pa.pago_id WHERE pa.cuota_id = cu.id AND pc.fecha <= :f), 0)), 0) "
            "FROM cuotas cu JOIN creditos cr ON cr.id = cu.credito_id "
            "WHERE cr.fecha <= :f "
            "AND (cu.creada_por_pago IS NULL OR (SELECT fecha FROM pagos_credito WHERE id = cu.creada_por_pago) <= :f) "
            "AND (cu.reemplazada_por_pago IS NULL "
            "     OR (SELECT fecha FROM pagos_credito WHERE id = cu.reemplazada_por_pago) > :f) "
            "AND (cu.estado != 'refinanciada' "
            "     OR (SELECT r.fecha FROM refinanciaciones r WHERE r.id = cr.refinanciacion_id) > :f)")
        params: dict = {"f": f}
        if producto_id is not None:
            sql += " AND cr.producto_id = :p"
            params["p"] = producto_id
        if credito_id is not None:
            sql += " AND cr.id = :c"
            params["c"] = credito_id
        return self._valor(sql, params)

    # ============================================================ resúmenes

    def resumen_mes(self, per: str) -> dict:
        entro = self._valor("SELECT SUM(monto) FROM ingresos WHERE substr(fecha, 1, 7) = ?", (per,))
        efectivo = self._valor("SELECT SUM(monto) FROM compras WHERE medio = 'efectivo' AND substr(fecha, 1, 7) = ?",
                               (per,))
        tarjeta = self._valor("SELECT SUM(monto) FROM compras WHERE medio = 'tarjeta' AND substr(fecha, 1, 7) = ?",
                              (per,))
        pagos = self._valor("SELECT SUM(monto) FROM pagos_credito WHERE substr(fecha, 1, 7) = ? "
                            "AND tipo NOT IN ('devolucion', 'saldo_favor')", (per,))
        costo = self._valor("SELECT SUM(a_costos) FROM pagos_credito WHERE substr(fecha, 1, 7) = ? "
                            "AND tipo != 'devolucion'", (per,))
        devoluciones = self._valor("SELECT SUM(a_capital) FROM pagos_credito WHERE substr(fecha, 1, 7) = ? "
                                   "AND tipo = 'devolucion'", (per,))
        iniciales = self._valor("SELECT SUM(cuota_inicial) FROM compras WHERE medio = 'tarjeta' "
                                "AND substr(fecha, 1, 7) = ?", (per,))
        efectivo += iniciales  # La cuota inicial de una compra a crédito sale del bolsillo.
        tarjeta -= iniciales + devoluciones
        categorias = self._todos(
            "SELECT COALESCE(ca.nombre, 'Sin categoría') AS categoria, "
            "SUM(CASE WHEN co.medio = 'efectivo' THEN co.monto ELSE co.cuota_inicial END) AS efectivo, "
            "SUM(CASE WHEN co.medio = 'tarjeta' THEN co.monto - co.cuota_inicial ELSE 0 END) AS tarjeta "
            "FROM compras co LEFT JOIN categorias ca ON ca.id = co.categoria_id "
            "WHERE substr(co.fecha, 1, 7) = ? GROUP BY 1 ORDER BY SUM(co.monto) DESC", (per,))
        return {"entro": entro, "compras_efectivo": efectivo, "pagos_credito": pagos, "salio": efectivo + pagos,
                "compras_tarjeta": tarjeta, "costo_deuda": costo, "por_categoria": categorias}

    def historial(self, meses: int = 12, hoy: date | None = None) -> list[dict]:
        """Resumen de los últimos meses (más antiguo primero) con el % de ingreso que se fue en deuda."""
        per = periodo(hoy or date.today())
        filas = []
        for k in range(meses - 1, -1, -1):
            p = periodo_siguiente(per, -k)
            r = self.resumen_mes(p)
            r["periodo"] = p
            r["ratio"] = (r["pagos_credito"] / r["entro"]) if r["entro"] else None
            cierre = self._uno("SELECT * FROM cierres_mensuales WHERE periodo = ?", (p,))
            r["deuda_total"] = cierre["deuda_total"] if cierre else (self.deuda_total() if k == 0 else None)
            filas.append(r)
        return filas

    def dia_a_dia_mensual(self, hoy: date | None = None) -> int:
        """Promedio mensual de compras en efectivo (sin servicios) de los últimos 3 meses con datos."""
        per = periodo(hoy or date.today())
        totales = []
        for k in range(1, 7):
            total = self._valor("SELECT SUM(monto) FROM compras WHERE medio = 'efectivo' AND servicio_id IS NULL "
                                "AND substr(fecha, 1, 7) = ?", (periodo_siguiente(per, -k),))
            if total:
                totales.append(total)
            if len(totales) == 3:
                break
        if totales:
            return round(sum(totales) / len(totales))
        return round(self.config_num("dia_a_dia_estimado") * 100)

    def generar_cierre(self, hoy: date | None = None) -> None:
        """Guarda la deuda y la reserva al cierre de cada mes anterior que aún no tenga foto.

        La deuda se reconstruye al último día del mes con el historial de pagos, así que
        también se completan los meses en que no se abrió la app (hasta 36 meses atrás).
        """
        hoy = hoy or date.today()
        anterior = periodo_siguiente(periodo(hoy), -1)
        primera = self._uno("SELECT MIN(f) AS f FROM (SELECT MIN(fecha) AS f FROM creditos "
                            "UNION ALL SELECT MIN(fecha) FROM ingresos UNION ALL SELECT MIN(fecha) FROM compras)")
        if not primera or not primera["f"]:
            return
        per = max(periodo(_fecha(primera["f"])), periodo_siguiente(anterior, -35))
        with self.con:
            while per <= anterior:
                if not self._uno("SELECT 1 FROM cierres_mensuales WHERE periodo = ?", (per,)):
                    fin = fin_periodo(per)
                    self.con.execute("INSERT INTO cierres_mensuales (periodo, deuda_total, reserva, creado) "
                                     "VALUES (?, ?, ?, ?)", (per, self.deuda_a_fecha(fin), self.saldo_reserva(fin),
                                                             _iso(hoy)))
                per = periodo_siguiente(per)

    # ============================================================ plan

    def meta_mes_adelantado(self, per: str) -> int:
        """Lo que debe tener la reserva para el mes `per`: cuotas de deuda + servicios de ese mes."""
        desde, hasta = inicio_periodo(per), fin_periodo(per)
        return self.total_programado(desde, hasta) + sum(s["monto"] for s in self.servicios_pendientes(desde, hasta))

    def entrada_plan(self, fecha: date, monto: int, incluir_esperadas: bool = False,
                     tipo: str = "ordinario") -> EntradaPlan:
        """Datos para repartir un ingreso recibido el `fecha`.

        Un ingreso ordinario que llega pocos días antes de su fecha de pago (fin de semana, festivo)
        se toma como el de esa fecha. Cubre lo que vence desde que llegó hasta el día anterior al
        siguiente ingreso; lo que vence el mismo día del siguiente ingreso se paga con ese ingreso.
        """
        dias = self.dias_pago()
        efectiva = fecha_pago_correspondiente(fecha, dias) if tipo == "ordinario" else fecha
        proximo = proxima_fecha_pago(efectiva, dias)
        restantes = 1 + sum(1 for f in fechas_pago_en_mes(efectiva.year, efectiva.month, dias) if f > efectiva)
        sig = periodo_siguiente(periodo(efectiva))
        antes = proximo - timedelta(days=1)
        nombres = {p["id"]: p["nombre"] for p in self.productos(False)}
        detalle = [Vencimiento(v["fecha"], nombres.get(v["producto_id"], "Crédito"), v["monto"], "credito")
                   for v in self.pagos_programados(None, antes) if v["monto"] > 0]
        detalle += [Vencimiento(s["fecha"], s["servicio"]["nombre"], s["monto"], "servicio")
                    for s in self.servicios_pendientes(fecha, antes)]
        detalle.sort(key=lambda v: (v.fecha, v.concepto))
        return EntradaPlan(
            fecha=fecha, ingreso=monto, proximo_ingreso=proximo, ingresos_restantes_mes=restantes,
            ingreso_mensual=self.ingreso_mensual_estimado(fecha, incluir_esperadas),
            ingresos_por_mes=len(dias),
            pagos_credito_antes_proximo=sum(v.monto for v in detalle if v.tipo == "credito"),
            pagos_credito_meta=self.total_programado(proximo, fin_periodo(sig)),
            pagos_mes_siguiente=self.total_programado(inicio_periodo(sig), fin_periodo(sig)),
            servicios_antes_proximo=sum(v.monto for v in detalle if v.tipo == "servicio"),
            dia_a_dia_mensual=self.dia_a_dia_mensual(fecha),
            saldo_reserva=max(0, self.saldo_reserva()),
            servicios_meta=sum(s["monto"] for s in self.servicios_pendientes(proximo, fin_periodo(sig))),
            fecha_efectiva=efectiva if efectiva != fecha else None,
            detalle=detalle,
        )

    def recomendacion_pagos(self, abono_total: int, hoy: date | None = None) -> list[dict]:
        """Mínimo, recomendado y total de cada tarjeta/crédito, repartiendo el abono extra del plan."""
        hoy = hoy or date.today()
        filas = [d for d in self.deuda_productos(hoy) if d["minimo"] or d["total"]]
        if self.config().get("estrategia") == "bola_de_nieve":
            orden = sorted(filas, key=lambda d: d["saldo"])
        else:
            orden = sorted(filas, key=lambda d: -d["producto"]["tasa_ea"])
        restante = abono_total
        for d in orden:
            extra = min(restante, max(0, d["total"] - d["minimo"]))
            d["recomendado"] = d["minimo"] + extra
            restante -= extra
        return orden
