"""Utilidades de fechas: meses, días de pago y ciclos de facturación."""

import calendar
from datetime import date, timedelta

FIN_DE_MES = 0  # Día de pago especial: último día del mes (30/31, 28/29 en febrero).


def ultimo_dia(anio: int, mes: int) -> int:
    return calendar.monthrange(anio, mes)[1]


def fecha_con_dia(anio: int, mes: int, dia: int) -> date:
    """Fecha del mes con el día indicado, ajustada al último día si no existe.

    `dia = FIN_DE_MES` significa último día del mes.
    """
    ultimo = ultimo_dia(anio, mes)
    if dia == FIN_DE_MES or dia > ultimo:
        dia = ultimo
    return date(anio, mes, dia)


def sumar_meses(fecha: date, meses: int, dia: int | None = None) -> date:
    """Suma meses conservando el día (o `dia` si se indica), ajustando a fin de mes."""
    total = fecha.year * 12 + (fecha.month - 1) + meses
    anio, mes = divmod(total, 12)
    return fecha_con_dia(anio, mes + 1, fecha.day if dia is None else dia)


def periodo(fecha: date) -> str:
    """'2026-11' para cualquier fecha de noviembre de 2026."""
    return f"{fecha.year:04d}-{fecha.month:02d}"


def inicio_periodo(per: str) -> date:
    anio, mes = map(int, per.split("-"))
    return date(anio, mes, 1)


def fin_periodo(per: str) -> date:
    anio, mes = map(int, per.split("-"))
    return date(anio, mes, ultimo_dia(anio, mes))


def periodo_siguiente(per: str, n: int = 1) -> str:
    return periodo(sumar_meses(inicio_periodo(per), n))


def nombre_periodo(per: str) -> str:
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    anio, mes = map(int, per.split("-"))
    return f"{meses[mes - 1]} {anio}"


def parsear_dias_pago(texto: str) -> list[int]:
    """'15,30' -> [15, FIN_DE_MES]. Los días 30 y 31 se toman como fin de mes."""
    dias = []
    for parte in texto.replace(";", ",").split(","):
        parte = parte.strip().lower()
        if not parte:
            continue
        if parte in ("fin", "ultimo", "último"):
            dias.append(FIN_DE_MES)
            continue
        d = int(parte)
        if not 1 <= d <= 31:
            raise ValueError(f"Día de pago inválido: {d}")
        dias.append(FIN_DE_MES if d >= 30 else d)
    return sorted(set(dias), key=lambda d: 99 if d == FIN_DE_MES else d)


def fechas_pago_en_mes(anio: int, mes: int, dias: list[int]) -> list[date]:
    return sorted({fecha_con_dia(anio, mes, d) for d in dias})


def proxima_fecha_pago(desde: date, dias: list[int]) -> date:
    """Primera fecha de pago estrictamente posterior a `desde`."""
    for k in range(0, 3):
        ref = sumar_meses(desde.replace(day=1), k)
        for f in fechas_pago_en_mes(ref.year, ref.month, dias):
            if f > desde:
                return f
    return desde + timedelta(days=30)


ANTICIPO_MAXIMO = 5  # Días que puede adelantarse un pago (fin de semana, festivo) y seguir siendo el mismo.


def fecha_pago_correspondiente(recibido: date, dias: list[int], anticipo: int = ANTICIPO_MAXIMO) -> date:
    """Fecha de pago programada a la que corresponde un ingreso.

    Si el sueldo del 30 llega el 28 (fin de semana o festivo), corresponde al 30: así el
    plan lo reparte hasta el ingreso siguiente (el 15) y no solo hasta dentro de 2 días.
    Si no hay una fecha de pago en los próximos `anticipo` días, es la fecha en que llegó.
    """
    siguiente = recibido if any(f == recibido for f in fechas_pago_en_mes(recibido.year, recibido.month, dias))         else proxima_fecha_pago(recibido, dias)
    return siguiente if (siguiente - recibido).days <= anticipo else recibido


def fecha_primera_cuota(compra: date, dia_corte: int, dia_pago: int) -> date:
    """Fecha límite de pago del extracto donde aparece una compra con tarjeta.

    La compra entra en el corte de su mes si se hace ese día o antes; si no, en
    el corte del mes siguiente. El pago vence el `dia_pago` posterior al corte.
    """
    corte = fecha_con_dia(compra.year, compra.month, dia_corte)
    if compra > corte:
        corte = sumar_meses(corte, 1, dia_corte)
    pago = fecha_con_dia(corte.year, corte.month, dia_pago)
    if pago <= corte:
        pago = sumar_meses(pago, 1, dia_pago)
    return pago
