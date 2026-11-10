"""Plan dinámico: cómo repartir cada ingreso según la deuda y el pago del mes siguiente.

Cada ingreso cubre lo que vence desde que llega hasta el día anterior al próximo
ingreso (lo que vence el mismo día del próximo ingreso se paga con ese ingreso).

Reglas (en orden):
  A. Pagos de crédito que vencen antes del próximo ingreso.
  B. Servicios que vencen antes del próximo ingreso.
     A y B se pagan primero con la reserva (Cajita); lo que falte sale de este ingreso.
  C. Gastos del día a día (promedio mensual / ingresos por mes).
  D. Reserva "mes adelantado": se aparta lo necesario para tener cubiertos los
     pagos de crédito y los servicios que vencen desde el próximo ingreso hasta el
     fin del mes siguiente, repartido entre los ingresos que quedan este mes.
     Si no alcanza, se aparta todo lo posible (etapa "construyendo reserva").
  E. Excedente (si queda): se reparte entre ahorro, abono extra a deuda y libre
     según el nivel de endeudamiento.
"""

from dataclasses import dataclass, field
from datetime import date

from .dinero import formato

SANO, MODERADO, ALTO, CRITICO = "sano", "moderado", "alto", "critico"
NIVELES = (SANO, MODERADO, ALTO, CRITICO)
NOMBRE_NIVEL = {SANO: "Sano", MODERADO: "Moderado", ALTO: "Alto", CRITICO: "Crítico"}
MENSAJE_NIVEL = {
    SANO: "Tu nivel de deuda es manejable.",
    MODERADO: "Evita nuevas compras a cuotas.",
    ALTO: "No uses la tarjeta y prioriza pagar la deuda.",
    CRITICO: "Más de la mitad de tu ingreso se va en deuda: evalúa organizar la deuda o una compra de cartera.",
}


@dataclass
class ConfigPlan:
    # Límites superiores (fracción del ingreso) de sano, moderado y alto.
    umbrales: tuple[float, float, float] = (0.20, 0.35, 0.50)
    # Reparto del excedente por nivel: (ahorro, abono extra a deuda, libre).
    reparto: dict[str, tuple[float, float, float]] = field(default_factory=lambda: {
        SANO: (0.30, 0.20, 0.50),
        MODERADO: (0.25, 0.35, 0.40),
        ALTO: (0.15, 0.60, 0.25),
        CRITICO: (0.10, 0.90, 0.00),
    })


def nivel_endeudamiento(ratio: float, config: ConfigPlan) -> str:
    sano, moderado, alto = config.umbrales
    if ratio < sano:
        return SANO
    if ratio < moderado:
        return MODERADO
    if ratio < alto:
        return ALTO
    return CRITICO


def ratio_endeudamiento(pagos_mes: int, ingreso_mensual: int) -> float:
    if ingreso_mensual <= 0:
        return 1.0 if pagos_mes > 0 else 0.0
    return pagos_mes / ingreso_mensual


@dataclass
class EntradaPlan:
    fecha: date
    ingreso: int
    proximo_ingreso: date
    ingresos_restantes_mes: int        # Incluye el ingreso actual.
    ingreso_mensual: int               # Estimado, para el % de endeudamiento.
    ingresos_por_mes: int
    pagos_credito_antes_proximo: int   # Pendientes que vencen antes del próximo ingreso (incluye vencidos).
    pagos_credito_meta: int            # Pendientes desde el próximo ingreso hasta el fin del mes siguiente.
    pagos_mes_siguiente: int           # Para el % de endeudamiento.
    servicios_antes_proximo: int
    dia_a_dia_mensual: int
    saldo_reserva: int
    servicios_meta: int = 0            # Servicios desde el próximo ingreso hasta el fin del mes siguiente.
    fecha_efectiva: date | None = None  # Fecha de pago a la que corresponde (si llegó unos días antes).
    detalle: list["Vencimiento"] = field(default_factory=list)  # Lo que cubre este ingreso, con fechas.

    @property
    def cubre_hasta(self) -> date:
        return date.fromordinal(self.proximo_ingreso.toordinal() - 1)

    @property
    def meta_reserva(self) -> int:
        return self.pagos_credito_meta + self.servicios_meta


@dataclass
class Vencimiento:
    fecha: date
    concepto: str
    monto: int
    tipo: str  # credito | servicio


@dataclass
class Partida:
    clave: str
    concepto: str
    monto: int
    nota: str = ""


@dataclass
class Plan:
    entrada: EntradaPlan
    nivel: str
    ratio: float
    partidas: list[Partida]
    desde_reserva: int
    reserva_despues: int
    meta_reserva: int
    al_dia: bool
    deficit: int

    def monto(self, clave: str) -> int:
        return sum(p.monto for p in self.partidas if p.clave == clave)

    @property
    def progreso_reserva(self) -> float:
        if self.meta_reserva <= 0:
            return 1.0
        return min(1.0, self.reserva_despues / self.meta_reserva)


def calcular_plan(e: EntradaPlan, config: ConfigPlan | None = None) -> Plan:
    config = config or ConfigPlan()
    ratio = ratio_endeudamiento(e.pagos_mes_siguiente, e.ingreso_mensual)
    nivel = nivel_endeudamiento(ratio, config)
    partidas: list[Partida] = []

    # A y B. Lo que vence antes del próximo ingreso: primero con la reserva, luego con el ingreso.
    reserva_credito = min(e.saldo_reserva, e.pagos_credito_antes_proximo)
    reserva_servicios = min(e.saldo_reserva - reserva_credito, e.servicios_antes_proximo)
    desde_reserva = reserva_credito + reserva_servicios
    credito_ingreso = e.pagos_credito_antes_proximo - reserva_credito
    servicios_ingreso = e.servicios_antes_proximo - reserva_servicios
    reserva = e.saldo_reserva - desde_reserva
    if e.pagos_credito_antes_proximo:
        nota = f"Tomar {formato(reserva_credito)} de la reserva" if reserva_credito else ""
        partidas.append(Partida("credito", "Pagos de tarjetas/créditos antes del próximo ingreso",
                                credito_ingreso, nota))
    nota = f"Tomar {formato(reserva_servicios)} de la reserva" if reserva_servicios else ""
    partidas.append(Partida("servicios", "Servicios que vencen antes del próximo ingreso", servicios_ingreso, nota))

    # C. Día a día.
    dia_a_dia = round(e.dia_a_dia_mensual / max(1, e.ingresos_por_mes))
    partidas.append(Partida("dia_a_dia", "Gastos del día a día", dia_a_dia,
                            "Promedio de tus últimos meses"))

    disponible = e.ingreso - credito_ingreso - servicios_ingreso - dia_a_dia
    deficit = max(0, -disponible)
    disponible = max(0, disponible)

    # D. Reserva mes adelantado.
    meta = e.meta_reserva
    falta = max(0, meta - reserva)
    aporte_ideal = -(-falta // max(1, e.ingresos_restantes_mes))  # Redondeo hacia arriba.
    aporte = min(aporte_ideal, disponible)
    al_dia = aporte == aporte_ideal  # Tras este ingreso, la reserva queda con lo del mes siguiente.
    nota = "" if aporte == aporte_ideal else "Construyendo reserva: se aparta todo lo posible"
    partidas.append(Partida("reserva", "Apartar en la Cajita para deudas y servicios del mes siguiente", aporte,
                            nota))
    disponible -= aporte
    reserva += aporte

    # E. Excedente.
    pct_ahorro, pct_abono, _ = config.reparto[nivel]
    ahorro = round(disponible * pct_ahorro)
    abono = round(disponible * pct_abono)
    libre = disponible - ahorro - abono
    partidas.append(Partida("ahorro", "Ahorro (cajas de ahorro / fondo de emergencia)", ahorro,
                            "" if ahorro or not deficit and disponible else "No alcanza después de lo obligatorio"))
    partidas.append(Partida("abono", "Abono extra a la deuda", abono))
    partidas.append(Partida("libre", "Libre", libre))

    return Plan(entrada=e, nivel=nivel, ratio=ratio, partidas=partidas, desde_reserva=desde_reserva,
                reserva_despues=reserva, meta_reserva=meta, al_dia=al_dia, deficit=deficit)

