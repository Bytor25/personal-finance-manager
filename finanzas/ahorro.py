"""Cajas de ahorro: cuánto se puede ahorrar el mes siguiente y cómo repartirlo entre las metas.

Reglas:
  1. Capacidad del mes = ingreso estimado − (pagos de deuda + servicios + día a día + gastos previstos).
  2. Ahorro sugerido = capacidad × % de ahorro del nivel de endeudamiento (el mismo del Plan del
     ingreso). Si no hay deuda, también se suma el % de abono extra (no hay a qué abonar).
  3. Saldo a favor del mes anterior: lo que sobre después de completar la reserva del mes
     adelantado se puede mover a las cajas (una sola vez).
  4. Reparto entre metas (orden: prioridad, fecha objetivo):
       a. Las metas con fecha reciben la cuota mensual que necesitan para llegar a tiempo.
       b. Lo que sobra se reparte por peso de prioridad (alta 3, media 2, baja 1) sin pasar
          de lo que le falta a cada meta.
"""

from dataclasses import dataclass, field
from datetime import date

from .fechas import inicio_periodo, periodo, periodo_siguiente

PESO_PRIORIDAD = {1: 3, 2: 2, 3: 1}
PESO = 100          # Centavos en un peso: los abonos sugeridos van en pesos enteros.
MIL = 1000 * PESO   # El ahorro sugerido del mes se redondea hacia abajo a miles.
NOMBRE_PRIORIDAD = {1: "Alta", 2: "Media", 3: "Baja"}
TIPOS_META = {
    "viaje": "✈️ Viaje", "tecnologia": "🎮 Consola / tecnología", "juego": "🕹️ Juego",
    "personal": "👟 Personal", "hogar": "🏠 Hogar", "estudio": "📚 Estudio",
    "emergencia": "🛟 Fondo de emergencia", "otro": "🎯 Otro",
}


@dataclass
class Meta:
    id: int
    nombre: str
    objetivo: int
    ahorrado: int
    fecha_objetivo: date | None = None
    prioridad: int = 2

    @property
    def falta(self) -> int:
        return max(0, self.objetivo - self.ahorrado)

    @property
    def progreso(self) -> float:
        return min(1.0, self.ahorrado / self.objetivo) if self.objetivo > 0 else 1.0


@dataclass
class Asignacion:
    meta: Meta
    mensual: int = 0                    # Lo sugerido para esta caja cada mes.
    necesaria: int | None = None        # Cuota mensual para llegar a la fecha objetivo.
    meses: int | None = None            # Meses para completarla con `mensual`.
    periodo_estimado: str | None = None  # Mes en que se completaría ('2027-03').

    @property
    def a_tiempo(self) -> bool | None:
        if self.meta.fecha_objetivo is None or self.periodo_estimado is None:
            return None
        return self.periodo_estimado <= periodo(self.meta.fecha_objetivo)


def meses_hasta(desde_periodo: str, fecha_objetivo: date) -> int:
    """Aportes mensuales posibles desde `desde_periodo` hasta el mes de la fecha objetivo (mínimo 1)."""
    inicio = inicio_periodo(desde_periodo)
    n = (fecha_objetivo.year - inicio.year) * 12 + fecha_objetivo.month - inicio.month + 1
    return max(1, n)


def _techo(a: int, b: int) -> int:
    return -(-a // b)


def repartir(monto: int, metas: list[Meta], desde_periodo: str) -> list[Asignacion]:
    """Reparte `monto` (un mes de ahorro) entre las metas que aún no se completan."""
    abiertas = sorted((m for m in metas if m.falta > 0),
                      key=lambda m: (m.prioridad, m.fecha_objetivo or date.max, m.id))
    asignaciones = {m.id: Asignacion(m) for m in abiertas}
    restante = max(0, monto)

    # a. Cuota necesaria de las metas con fecha.
    for m in abiertas:
        if m.fecha_objetivo is None:
            continue
        a = asignaciones[m.id]
        a.necesaria = _techo(_techo(m.falta, meses_hasta(desde_periodo, m.fecha_objetivo)), PESO) * PESO
        a.mensual = min(a.necesaria, restante)
        restante -= a.mensual

    # b. El resto por peso de prioridad, sin pasar de lo que falta.
    while restante > 0:
        candidatas = [m for m in abiertas if asignaciones[m.id].mensual < m.falta]
        if not candidatas:
            break
        pesos = sum(PESO_PRIORIDAD[m.prioridad] for m in candidatas)
        repartido = 0
        for m in candidatas:
            a = asignaciones[m.id]
            parte = restante * PESO_PRIORIDAD[m.prioridad] // pesos // PESO * PESO
            parte = min(parte, m.falta - a.mensual)
            a.mensual += parte
            repartido += parte
        if repartido == 0:  # Quedan pesos sueltos por la división: van a la primera en el orden.
            m = candidatas[0]
            parte = min(restante, m.falta - asignaciones[m.id].mensual)
            asignaciones[m.id].mensual += parte
            repartido = parte
        restante -= repartido

    for a in asignaciones.values():
        if a.mensual > 0:
            a.meses = _techo(a.meta.falta, a.mensual)
            a.periodo_estimado = periodo_siguiente(desde_periodo, a.meses - 1)
    return [asignaciones[m.id] for m in abiertas]


@dataclass
class EntradaAhorro:
    periodo: str                 # Mes que se planea (normalmente el siguiente).
    ingreso: int                 # Ingreso mensual estimado.
    pagos_deuda: int             # Cuotas y mínimos de tarjetas/créditos de ese mes.
    servicios: int
    dia_a_dia: int
    gastos_previstos: int
    pct_ahorro: float            # Fracción del excedente para ahorrar (según el nivel).
    saldo_favor: int             # Lo que sobró del mes anterior.
    falta_reserva: int           # Lo que falta en la reserva para el pago del mes siguiente.
    fechas_ingreso: list[date] = field(default_factory=list)  # Días de pago del mes planeado.


@dataclass
class CapacidadAhorro:
    entrada: EntradaAhorro
    gastos: int                  # Todo lo comprometido del mes.
    capacidad: int               # Ingreso − gastos (puede ser negativo).
    sugerido: int                # Lo recomendado para las cajas ese mes.
    extra_saldo_favor: int       # Del saldo a favor, lo que se puede mover a las cajas.
    por_fecha: list[tuple[date, int]]  # Cuánto apartar en cada día de pago.

    @property
    def deficit(self) -> int:
        return max(0, -self.capacidad)


def capacidad_ahorro(e: EntradaAhorro) -> CapacidadAhorro:
    gastos = e.pagos_deuda + e.servicios + e.dia_a_dia + e.gastos_previstos
    capacidad = e.ingreso - gastos
    sugerido = max(0, int(capacidad * e.pct_ahorro) // MIL * MIL)
    extra = max(0, e.saldo_favor - e.falta_reserva)
    por_fecha = []
    if e.fechas_ingreso and sugerido:
        n = len(e.fechas_ingreso)
        base = sugerido // n // PESO * PESO
        sobra = sugerido - base * n
        por_fecha = [(f, base + (sobra if i == n - 1 else 0)) for i, f in enumerate(e.fechas_ingreso)]
    return CapacidadAhorro(entrada=e, gastos=gastos, capacidad=capacidad, sugerido=sugerido,
                           extra_saldo_favor=extra, por_fecha=por_fecha)
