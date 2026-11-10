"""Cálculos de crédito: tasas, cronogramas, cargos, mora, costo total, refinanciación y pagos.

Todas las funciones son puras: reciben números (montos en centavos) y devuelven
resultados, sin tocar la base de datos ni la interfaz. Los montos de dinero se
calculan con Decimal y se redondean a pesos enteros con redondeo comercial
(0,5 hacia arriba). Las tasas se exponen como float (no son dinero).
"""

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, getcontext

from .fechas import sumar_meses

getcontext().prec = 34

ABONO_CONSTANTE = "abono_constante"  # Tarjetas: capital fijo + interés sobre saldo (cuota decreciente).
CUOTA_FIJA = "cuota_fija"            # Préstamos, cupos y refinanciaciones: cuota constante (método francés).

# Periodicidad de las cuotas: periodos por año y separación entre cuotas.
PERIODOS_ANIO = {"mensual": 12, "quincenal": 24, "semanal": 52}
DIAS_PERIODO = {"quincenal": 15, "semanal": 7}

# Modalidad en que se expresa una tasa: efectiva anual, mes vencido o nominal anual mes vencido.
MODALIDADES_TASA = ("EA", "MV", "NAMV")

# Componentes de una cuota y orden contractual de aplicación de pagos por defecto.
COMPONENTES = ("cobranza", "mora", "otros", "interes", "capital")

MAX_CUOTAS = 600
PESO = 100  # Centavos por peso: los cronogramas se redondean a pesos enteros.


def _dec(valor) -> Decimal:
    return valor if isinstance(valor, Decimal) else Decimal(repr(valor)) if isinstance(valor, float) else Decimal(valor)


def _pesos(centavos) -> int:
    """Redondea un monto en centavos a pesos enteros (0,5 hacia arriba)."""
    return int((_dec(centavos) / PESO).quantize(Decimal(1), rounding=ROUND_HALF_UP)) * PESO


def _centavos(valor) -> int:
    return int(_dec(valor).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass
class Cuota:
    numero: int
    fecha: date
    capital: int
    interes: int
    otros: int = 0
    saldo_inicial: int = 0
    detalle: dict[str, int] = field(default_factory=dict)  # Cargos que forman `otros`, por nombre.

    @property
    def total(self) -> int:
        return self.capital + self.interes + self.otros

    @property
    def saldo_final(self) -> int:
        return self.saldo_inicial - self.capital


# ---------------------------------------------------------------- tasas

def ea_a_mv(tasa_ea_pct: float) -> float:
    """Tasa efectiva anual en % (30.0) -> tasa mes vencido como fracción (0.02210)."""
    return float((1 + _dec(tasa_ea_pct) / 100) ** (Decimal(1) / 12) - 1)


def mv_a_ea(mv: float) -> float:
    """Tasa mes vencido como fracción -> tasa efectiva anual en %."""
    return float(((1 + _dec(mv)) ** 12 - 1) * 100)


def a_ea(valor_pct: float, modalidad: str) -> float:
    """Convierte una tasa en % expresada en E.A., M.V. o N.A.M.V. a E.A. en %."""
    if modalidad == "EA":
        return float(valor_pct)
    if modalidad == "MV":
        return mv_a_ea(_dec(valor_pct) / 100)
    if modalidad == "NAMV":
        return mv_a_ea(_dec(valor_pct) / 100 / 12)
    raise ValueError(f"Modalidad de tasa desconocida: {modalidad}")


def tasa_periodica(tasa_ea_pct: float, periodicidad: str = "mensual") -> float:
    """Tasa efectiva del periodo de pago (fracción) a partir de la E.A.: (1 + EA)^(1/p) − 1."""
    p = PERIODOS_ANIO[periodicidad]
    return float((1 + _dec(tasa_ea_pct) / 100) ** (Decimal(1) / p) - 1)


def fecha_cuota(primera: date, k: int, periodicidad: str = "mensual", dia: int | None = None) -> date:
    """Fecha de la cuota k (desde 0) según la periodicidad.

    `dia` es el día de pago pactado (ancla). Si no se indica, se usa el día de la
    primera cuota. El ancla evita que una primera cuota ajustada a fin de febrero
    (28) arrastre todas las siguientes al 28: con `dia=31` las cuotas quedan el
    28-feb, 31-mar, 30-abr...
    """
    if periodicidad == "mensual":
        return sumar_meses(primera, k, primera.day if dia is None else dia)
    return primera + timedelta(days=DIAS_PERIODO[periodicidad] * k)


# ---------------------------------------------------------------- cronogramas

def cronograma_abono_constante(saldo: int, mv: float, primera: date, n: int | None = None,
                               capital_fijo: int | None = None, periodicidad: str = "mensual",
                               dia: int | None = None) -> list[Cuota]:
    """Tarjeta de crédito: capital igual cada periodo e interés sobre el saldo pendiente.

    Se indica `n` (número de cuotas) o `capital_fijo` (para recalcular tras un
    abono conservando el capital por cuota y reduciendo el plazo). `mv` es la tasa
    efectiva del periodo.
    """
    if saldo <= 0:
        return []
    if capital_fijo is None:
        if not n or n < 1:
            raise ValueError("Número de cuotas inválido")
        capital_fijo = math.ceil(saldo / n / PESO) * PESO
    else:
        n = math.ceil(saldo / capital_fijo)
    tasa = _dec(mv)
    cuotas = []
    for k in range(1, n + 1):
        capital = saldo if k == n else min(capital_fijo, saldo)
        cuotas.append(Cuota(k, fecha_cuota(primera, k - 1, periodicidad, dia), capital, _pesos(saldo * tasa),
                            saldo_inicial=saldo))
        saldo -= capital
        if saldo <= 0:
            break
    return cuotas


def valor_cuota_fija(saldo: int, n: int, mv: float) -> int:
    if n < 1:
        raise ValueError("Número de cuotas inválido")
    tasa = _dec(mv)
    if tasa == 0:
        return math.ceil(saldo / n / PESO) * PESO
    return _pesos(saldo * tasa / (1 - (1 + tasa) ** -n))


def cronograma_cuota_fija(saldo: int, mv: float, primera: date, n: int | None = None,
                          cuota: int | None = None, periodicidad: str = "mensual",
                          dia: int | None = None) -> list[Cuota]:
    """Cuota constante (método francés); la última se ajusta para cerrar el saldo.

    Se indica `n`, `cuota` o ambos. Solo con `cuota` el plazo es el necesario
    para pagar el saldo (sirve para "reducir plazo" tras un abono).
    """
    if saldo <= 0:
        return []
    if cuota is None:
        cuota = valor_cuota_fija(saldo, n, mv)
    tasa = _dec(mv)
    if _pesos(saldo * tasa) >= cuota:
        raise ValueError("La cuota no alcanza a cubrir los intereses: la deuda nunca se pagaría")
    limite = n or MAX_CUOTAS
    cuotas = []
    for k in range(1, limite + 1):
        interes = _pesos(saldo * tasa)
        capital = cuota - interes
        if capital >= saldo or k == limite:
            capital = saldo
        cuotas.append(Cuota(k, fecha_cuota(primera, k - 1, periodicidad, dia), capital, interes,
                            saldo_inicial=saldo))
        saldo -= capital
        if saldo <= 0:
            break
    return cuotas


def generar_cronograma(metodo: str, saldo: int, mv: float, primera: date, n: int | None = None,
                       cuota: int | None = None, periodicidad: str = "mensual",
                       dia: int | None = None) -> list[Cuota]:
    if metodo == ABONO_CONSTANTE:
        return cronograma_abono_constante(saldo, mv, primera, n=n, periodicidad=periodicidad, dia=dia)
    return cronograma_cuota_fija(saldo, mv, primera, n=n, cuota=cuota, periodicidad=periodicidad, dia=dia)


def saldo_tras_cuotas(metodo: str, valor: int, n: int, mv: float, pagadas: int) -> int:
    """Capital pendiente de una compra de `valor` a `n` cuotas después de pagar `pagadas` cuotas."""
    if not 0 <= pagadas < n:
        raise ValueError("Las cuotas ya pagadas deben ser menos que el total de cuotas")
    cronograma = generar_cronograma(metodo, valor, mv, date.today(), n=n)
    return sum(c.capital for c in cronograma[pagadas:])


def tasa_implicita_mv(saldo: int, n: int, cuota: int) -> float | None:
    """Tasa del periodo que hace que `n` cuotas de `cuota` paguen exactamente `saldo`.

    Devuelve None si la cuota es tan baja que ni sin intereses alcanza.
    """
    if saldo <= 0 or n < 1 or cuota * n < saldo:
        return None
    if cuota * n == saldo:
        return 0.0

    def valor_presente(i: float) -> float:
        return cuota * (1 - (1 + i) ** -n) / i

    bajo, alto = 1e-9, 1.0
    while valor_presente(alto) > saldo:
        alto *= 2
    for _ in range(200):
        medio = (bajo + alto) / 2
        if valor_presente(medio) > saldo:
            bajo = medio
        else:
            alto = medio
    return (bajo + alto) / 2


def recalcular_tras_abono(metodo: str, saldo: int, mv: float, primera: date, cuotas_restantes: int,
                          cuota_actual: int, capital_por_cuota: int, reducir: str = "plazo",
                          periodicidad: str = "mensual", dia: int | None = None) -> list[Cuota]:
    """Nuevo cronograma de un crédito después de un abono extraordinario a capital.

    `saldo` ya debe tener descontado el abono. `reducir` es "plazo" (misma
    cuota, menos periodos; ahorra más intereses) o "cuota" (mismos periodos, cuota menor).
    """
    if saldo <= 0:
        return []
    if reducir == "cuota":
        return generar_cronograma(metodo, saldo, mv, primera, n=max(1, cuotas_restantes), periodicidad=periodicidad,
                                  dia=dia)
    if metodo == ABONO_CONSTANTE:
        return cronograma_abono_constante(saldo, mv, primera, capital_fijo=max(1, capital_por_cuota),
                                          periodicidad=periodicidad, dia=dia)
    return cronograma_cuota_fija(saldo, mv, primera, cuota=cuota_actual, periodicidad=periodicidad, dia=dia)


def interes_causado(capital: int, tasa_periodo: float, dias: int, dias_periodo: int) -> int:
    """Interés corriente causado en `dias` de un periodo de `dias_periodo` días.

    capital × ((1 + i)^(días / días del periodo) − 1). Se usa al cancelar antes del
    vencimiento cuando el contrato cobra solo el interés causado.
    """
    if capital <= 0 or dias <= 0 or tasa_periodo <= 0 or dias_periodo <= 0:
        return 0
    dias = min(dias, dias_periodo)
    factor = (1 + _dec(tasa_periodo)) ** (_dec(dias) / _dec(dias_periodo)) - 1
    return _pesos(capital * factor)


# ---------------------------------------------------------------- cargos (fianza, aval, seguro, ...)

@dataclass
class Cargo:
    """Cargo adicional de un crédito, tal como lo define la oferta aceptada.

    base:  "pct_capital" (% del capital financiado), "fijo" (centavos) o
           "pct_saldo" (% del saldo al inicio de cada periodo; solo por cuota).
    cobro: "inicial" (se paga al comprar), "prorrateado" (el total se reparte en
           las cuotas) o "por_cuota" (el valor se cobra en cada cuota).
    es_interes: el usuario lo marca si, según su contrato, cuenta como interés
           (solo se usa para comparar contra los límites legales; la app no lo decide).
    """
    nombre: str
    base: str
    valor: float
    cobro: str = "prorrateado"
    iva_pct: float = 0.0
    tipo: str = "otro"  # fianza | aval | seguro | administracion | estudio | otro
    es_interes: bool = False

    @classmethod
    def desde_dict(cls, d: dict) -> "Cargo":
        return cls(nombre=d.get("nombre", "Cargo"), base=d.get("base", "fijo"), valor=float(d.get("valor", 0)),
                   cobro=d.get("cobro", "prorrateado"), iva_pct=float(d.get("iva_pct", 0)),
                   tipo=d.get("tipo", "otro"), es_interes=bool(d.get("es_interes", False)))

    def como_dict(self) -> dict:
        return {"nombre": self.nombre, "base": self.base, "valor": self.valor, "cobro": self.cobro,
                "iva_pct": self.iva_pct, "tipo": self.tipo, "es_interes": self.es_interes}

    def _con_iva(self, monto) -> Decimal:
        return _dec(monto) * (1 + _dec(self.iva_pct) / 100)

    def total_sobre(self, capital: int) -> int:
        """Valor total con IVA para cargos de base fija o % del capital (en centavos)."""
        if self.base == "fijo":
            base = _dec(self.valor)
        elif self.base == "pct_capital":
            base = capital * _dec(self.valor) / 100
        else:
            raise ValueError(f"El cargo «{self.nombre}» sobre saldo solo puede cobrarse por cuota")
        return _pesos(self._con_iva(base))


def repartir(total: int, n: int) -> list[int]:
    """Reparte `total` en `n` partes en pesos enteros; la última cierra la diferencia.

    Si el redondeo hacia arriba de las partes dejaría la última negativa (totales
    pequeños en muchas cuotas), las partes se redondean hacia abajo.
    """
    if n <= 0:
        return []
    parte = _pesos(Decimal(total) / n)
    if total - parte * (n - 1) < 0:
        parte = (total // n // PESO) * PESO
    return [parte] * (n - 1) + [total - parte * (n - 1)]


def aplicar_cargos(cronograma: list[Cuota], capital: int, cargos: list[Cargo]) -> int:
    """Suma los cargos a las cuotas (en `otros` y `detalle`) y devuelve el total de cargos iniciales."""
    iniciales = 0
    n = len(cronograma)
    for cargo in cargos:
        if cargo.cobro == "inicial":
            iniciales += cargo.total_sobre(capital)
            continue
        if cargo.cobro == "prorrateado":
            montos = repartir(cargo.total_sobre(capital), n)
        elif cargo.base == "pct_saldo":
            montos = [_pesos(cargo._con_iva(c.saldo_inicial * _dec(cargo.valor) / 100)) for c in cronograma]
        else:
            montos = [cargo.total_sobre(capital)] * n
        for c, monto in zip(cronograma, montos):
            if monto:
                c.otros += monto
                c.detalle[cargo.nombre] = c.detalle.get(cargo.nombre, 0) + monto
    return iniciales


# ---------------------------------------------------------------- mora y cobranza

def interes_mora(capital_vencido: int, tasa_mora_ea: float, dias: int) -> int:
    """Interés moratorio sobre capital vencido: capital × ((1 + EA)^(días/365) − 1)."""
    if capital_vencido <= 0 or dias <= 0 or tasa_mora_ea <= 0:
        return 0
    factor = (1 + _dec(tasa_mora_ea) / 100) ** (_dec(dias) / 365) - 1
    return _pesos(capital_vencido * factor)


@dataclass
class ReglaCobranza:
    """Gasto de cobranza: desde cierto día de mora, valor fijo o % de lo vencido, más IVA.

    frecuencia: "unica" (una vez por episodio de mora) o "mensual" (una vez por cada
    30 días de mora a partir de `desde_dias`).
    """
    desde_dias: int
    base: str  # "fijo" (centavos) | "pct_vencido"
    valor: float
    iva_pct: float = 0.0
    frecuencia: str = "unica"

    @classmethod
    def desde_dict(cls, d: dict) -> "ReglaCobranza":
        return cls(int(d.get("desde_dias", 1)), d.get("base", "fijo"), float(d.get("valor", 0)),
                   float(d.get("iva_pct", 0)), d.get("frecuencia", "unica"))

    def como_dict(self) -> dict:
        return {"desde_dias": self.desde_dias, "base": self.base, "valor": self.valor, "iva_pct": self.iva_pct,
                "frecuencia": self.frecuencia}

    def periodos(self, dias_mora: int) -> int:
        """Cuántas veces corresponde cobrarla con `dias_mora` días de atraso."""
        if dias_mora < self.desde_dias:
            return 0
        return 1 if self.frecuencia == "unica" else 1 + (dias_mora - self.desde_dias) // 30

    def monto(self, vencido: int) -> int:
        base = _dec(self.valor) if self.base == "fijo" else vencido * _dec(self.valor) / 100
        return _pesos(base * (1 + _dec(self.iva_pct) / 100))


# ---------------------------------------------------------------- costo total y tasa efectiva

def tasa_efectiva_flujos(flujos: list[tuple[date, int]]) -> float | None:
    """Tasa efectiva anual (%) implícita en flujos de caja irregulares (XIRR, base 365).

    Convención: lo recibido es positivo y lo pagado negativo. Devuelve None si los
    flujos no cambian de signo.
    """
    if not flujos or all(m >= 0 for _, m in flujos) or all(m <= 0 for _, m in flujos):
        return None
    t0 = min(f for f, _ in flujos)

    def vpn(tasa: float) -> float:
        return sum(m / (1 + tasa) ** ((f - t0).days / 365) for f, m in flujos)

    bajo, alto = -0.99, 1.0
    signo_bajo = vpn(bajo) > 0
    while (vpn(alto) > 0) == signo_bajo and alto < 1e6:
        alto *= 2
    if (vpn(alto) > 0) == signo_bajo:
        return None
    for _ in range(300):
        medio = (bajo + alto) / 2
        if (vpn(medio) > 0) == signo_bajo:
            bajo = medio
        else:
            alto = medio
    return (bajo + alto) / 2 * 100


@dataclass
class CostoFinanciacion:
    precio_contado: int
    precio_financiado: int
    cuota_inicial: int
    capital: int
    intereses: int
    cargos_cuotas: int
    cargos_iniciales: int
    total_cuotas: int
    num_cuotas: int
    tasa_ea_contractual: float
    tasa_ea_efectiva: float | None
    cargos_como_interes: int = 0
    # Tasa E.A. de intereses + cargos marcados "cuenta como interés" (para comparar con la usura).
    tasa_ea_interes: float | None = None

    @property
    def total_cargos(self) -> int:
        return self.cargos_cuotas + self.cargos_iniciales

    @property
    def total_pagado(self) -> int:
        return self.cuota_inicial + self.cargos_iniciales + self.total_cuotas

    @property
    def diferencia(self) -> int:
        """Lo que pagas de más frente a comprar de contado."""
        return self.total_pagado - self.precio_contado

    @property
    def costo_financiero(self) -> int:
        """Intereses + cargos del crédito."""
        return self.intereses + self.total_cargos

    @property
    def costo_comercial(self) -> int:
        """Sobreprecio del producto por comprarlo financiado (precio financiado − precio de contado)."""
        return self.precio_financiado - self.precio_contado

    @property
    def incremento_pct(self) -> float:
        return self.diferencia / self.precio_contado * 100 if self.precio_contado else 0.0


def costo_financiacion(cronograma: list[Cuota], fecha_compra: date, capital: int, tasa_ea: float,
                       precio_contado: int | None = None, precio_financiado: int | None = None,
                       cuota_inicial: int = 0, cargos_iniciales: int = 0,
                       cargos: list[Cargo] | None = None) -> CostoFinanciacion:
    """Costo total de una compra financiada y su tasa efectiva real por flujos de caja.

    Los flujos son: en la fecha de compra recibes el producto (precio de contado) y
    pagas la cuota inicial y los cargos iniciales; luego pagas cada cuota en su fecha.
    """
    precio_financiado = precio_financiado or capital + cuota_inicial
    precio_contado = precio_contado or precio_financiado
    flujos = [(fecha_compra, precio_contado - cuota_inicial - cargos_iniciales)]
    flujos += [(c.fecha, -c.total) for c in cronograma]
    nombres_interes = {c.nombre for c in (cargos or []) if c.es_interes}
    como_interes = sum(m for c in cronograma for n, m in c.detalle.items() if n in nombres_interes)
    iniciales_interes = sum(c.total_sobre(capital) for c in (cargos or [])
                            if c.es_interes and c.cobro == "inicial" and c.base != "pct_saldo")
    flujos_interes = [(fecha_compra, capital - iniciales_interes)]
    flujos_interes += [(c.fecha, -(c.capital + c.interes + sum(m for n, m in c.detalle.items()
                                                                if n in nombres_interes))) for c in cronograma]
    hay_interes = any(c.interes for c in cronograma) or como_interes or iniciales_interes
    return CostoFinanciacion(
        precio_contado=precio_contado, precio_financiado=precio_financiado, cuota_inicial=cuota_inicial,
        capital=capital, intereses=sum(c.interes for c in cronograma), cargos_cuotas=sum(c.otros for c in cronograma),
        cargos_iniciales=cargos_iniciales, total_cuotas=sum(c.total for c in cronograma), num_cuotas=len(cronograma),
        tasa_ea_contractual=tasa_ea, tasa_ea_efectiva=tasa_efectiva_flujos(flujos), cargos_como_interes=como_interes,
        tasa_ea_interes=tasa_efectiva_flujos(flujos_interes) if hay_interes else 0.0)


# ---------------------------------------------------------------- ofertas (simulación y comparación)

@dataclass
class Oferta:
    """Condiciones reales de una alternativa de financiación de una compra."""
    nombre: str
    precio_contado: int
    cuota_inicial: int = 0
    precio_financiado: int | None = None   # Si el almacén cobra más caro el producto financiado.
    num_cuotas: int = 1
    tasa: float = 0.0
    modalidad_tasa: str = "EA"
    periodicidad: str = "mensual"
    sistema: str = CUOTA_FIJA
    cargos: list[Cargo] = field(default_factory=list)
    primera_cuota: date | None = None
    fecha: date | None = None

    def simular(self) -> tuple[list[Cuota], CostoFinanciacion]:
        fecha = self.fecha or date.today()
        precio = self.precio_financiado or self.precio_contado
        capital = precio - self.cuota_inicial
        if capital < 0:
            raise ValueError(f"{self.nombre}: la cuota inicial supera el precio")
        tasa_ea = a_ea(self.tasa, self.modalidad_tasa)
        if capital == 0:
            cronograma: list[Cuota] = []
        else:
            primera = self.primera_cuota or (sumar_meses(fecha, 1) if self.periodicidad == "mensual"
                                             else fecha_cuota(fecha, 1, self.periodicidad))
            dia = None if self.primera_cuota else fecha.day
            cronograma = generar_cronograma(self.sistema, capital, tasa_periodica(tasa_ea, self.periodicidad),
                                            primera, n=self.num_cuotas, periodicidad=self.periodicidad, dia=dia)
        iniciales = aplicar_cargos(cronograma, capital, self.cargos)
        return cronograma, costo_financiacion(cronograma, fecha, capital, tasa_ea, self.precio_contado, precio,
                                              self.cuota_inicial, iniciales, self.cargos)


def comparar_ofertas(ofertas: list[Oferta]) -> list[tuple[Oferta, list[Cuota], CostoFinanciacion]]:
    return [(o, *o.simular()) for o in ofertas]


# ---------------------------------------------------------------- refinanciación

@dataclass
class Refinanciacion:
    deuda_total: int
    valor_pagado: int
    saldo: int
    n: int
    cuota: int
    tasa_ea_declarada: float | None
    mv_usada: float
    ea_implicita: float | None
    cronograma: list[Cuota]
    advertencias: list[str] = field(default_factory=list)

    @property
    def total_cuotas(self) -> int:
        return sum(c.total for c in self.cronograma)

    @property
    def intereses_cuotas(self) -> int:
        return sum(c.interes for c in self.cronograma)

    @property
    def total_pagar(self) -> int:
        return self.valor_pagado + self.total_cuotas

    @property
    def costo_total(self) -> int:
        """Lo que cuesta organizar la deuda: lo pagado para refinanciar + intereses de las cuotas."""
        return self.valor_pagado + self.intereses_cuotas

    @property
    def ultima_fecha(self) -> date | None:
        return self.cronograma[-1].fecha if self.cronograma else None


def analizar_refinanciacion(deuda_total: int, valor_pagado: int, n: int, primera: date,
                            cuota: int | None = None, tasa_ea: float | None = None,
                            saldo: int | None = None, dia: int | None = None) -> Refinanciacion:
    """Analiza una refinanciación ("organizar deuda") con los datos que muestra el banco.

    - `valor_pagado` cubre intereses y comisiones pendientes, no capital: el saldo
      refinanciado es `deuda_total − valor_pagado`, salvo que se indique `saldo`.
    - Si se conoce la cuota, el cronograma usa la tasa implícita en ella (así cuadra
      con lo que cobra el banco) y se compara con la tasa declarada.
    - Si solo se conoce la tasa, la cuota se calcula con cuota fija.
    """
    if n < 1:
        raise ValueError("El número de cuotas debe ser al menos 1")
    if cuota is None and tasa_ea is None:
        raise ValueError("Indica el valor de la cuota o la tasa E.A.")
    saldo = deuda_total - valor_pagado if saldo is None else saldo
    if saldo <= 0:
        raise ValueError("El saldo a refinanciar debe ser mayor que cero")

    advertencias = []
    mv_declarada = ea_a_mv(tasa_ea) if tasa_ea is not None else None
    mv_implicita = tasa_implicita_mv(saldo, n, cuota) if cuota else None

    if cuota is not None and mv_implicita is None:
        advertencias.append("La cuota × número de cuotas es menor que el saldo: revisa los datos. "
                            "El cronograma se calculó con la tasa declarada.")
        if mv_declarada is None:
            raise ValueError("La cuota no alcanza a pagar el saldo y no hay tasa para recalcular")
        cuota = None

    if cuota is None:
        mv = mv_declarada
        cuota = valor_cuota_fija(saldo, n, mv)
    else:
        mv = mv_implicita
        if mv_declarada is not None and abs(mv_implicita - mv_declarada) > 0.0005:
            implicita = f"{mv_a_ea(mv_implicita):.2f}".replace(".", ",")
            declarada = f"{tasa_ea:.2f}".replace(".", ",")
            advertencias.append(
                f"La cuota equivale a una tasa de {implicita} % E.A., distinta de la {declarada} % E.A. "
                "declarada. Puede incluir seguros u otros cargos, o el saldo refinanciado es distinto "
                "al calculado.")

    cronograma = cronograma_cuota_fija(saldo, mv, primera, n=n, cuota=cuota, dia=dia)
    return Refinanciacion(
        deuda_total=deuda_total, valor_pagado=valor_pagado, saldo=saldo, n=n, cuota=cuota,
        tasa_ea_declarada=tasa_ea, mv_usada=mv,
        ea_implicita=mv_a_ea(mv_implicita) if mv_implicita is not None else None,
        cronograma=cronograma, advertencias=advertencias)


# ---------------------------------------------------------------- pagos

@dataclass
class CuotaPendiente:
    id: int
    fecha: date
    capital: int
    interes: int
    otros: int
    pagado: int
    tasa_mv: float = 0.0
    mora: int = 0
    cobranza: int = 0
    # Pagado por componente; si es None se deduce de `pagado` cubriendo primero costos (registros antiguos).
    pagado_por: dict[str, int] | None = None
    orden: tuple[str, ...] = COMPONENTES

    @property
    def total(self) -> int:
        return self.capital + self.interes + self.otros + self.mora + self.cobranza

    @property
    def pendiente(self) -> int:
        return max(0, self.total - self.pagado)

    def pendiente_por(self) -> dict[str, int]:
        montos = {"capital": self.capital, "interes": self.interes, "otros": self.otros, "mora": self.mora,
                  "cobranza": self.cobranza}
        if self.pagado_por is not None:
            return {k: max(0, v - self.pagado_por.get(k, 0)) for k, v in montos.items()}
        restante = self.pagado
        pendientes = {}
        for k in ("cobranza", "mora", "interes", "otros", "capital"):
            cubierto = min(restante, montos[k])
            pendientes[k] = montos[k] - cubierto
            restante -= cubierto
        return pendientes


@dataclass
class Aplicacion:
    cuota_id: int
    monto: int
    a_costos: int   # Todo lo que no es capital: intereses, cargos, mora y cobranza.
    a_capital: int
    por_componente: dict[str, int] = field(default_factory=dict)


def aplicar_pago(cuotas: list[CuotaPendiente], monto: int, hasta: date | None = None
                 ) -> tuple[list[Aplicacion], int]:
    """Reparte un pago entre las cuotas pendientes, de la más antigua a la más nueva.

    Dentro de cada cuota se cubren los componentes en el orden contractual de esa
    cuota (por defecto: cobranza, mora, cargos, intereses y capital). Si se indica
    `hasta`, solo se cubren cuotas que vencen en esa fecha o antes. Devuelve las
    aplicaciones y el sobrante (que se puede usar como abono a capital).
    """
    aplicaciones = []
    restante = monto
    for c in sorted(cuotas, key=lambda c: (c.fecha, c.id)):
        if restante <= 0:
            break
        if hasta is not None and c.fecha > hasta:
            break
        if c.pendiente <= 0:
            continue
        pendientes = c.pendiente_por()
        por = {}
        for comp in c.orden:
            cubierto = min(restante, pendientes.get(comp, 0))
            if cubierto:
                por[comp] = cubierto
                restante -= cubierto
        if por:
            a_capital = por.get("capital", 0)
            total = sum(por.values())
            aplicaciones.append(Aplicacion(c.id, total, total - a_capital, a_capital, por))
    return aplicaciones, restante


# ---------------------------------------------------------------- extracto

def pago_minimo_extracto(capital_mes: int, intereses: int, comisiones_avances: int = 0,
                         comisiones_servicio: int = 0, cargos_conversion: int = 0,
                         abonos: int = 0, devoluciones: int = 0) -> int:
    """Pago mínimo como lo calcula el extracto (validado con extractos de Nu)."""
    return (capital_mes + intereses + comisiones_avances + comisiones_servicio
            + cargos_conversion - abonos - devoluciones)


def interes_si_paga_minimo(deuda_restante: int, tasa_ea: float) -> int:
    """Intereses aproximados del mes siguiente sobre lo que queda debiendo tras el mínimo."""
    return _pesos(deuda_restante * _dec(ea_a_mv(tasa_ea)))
