"""Gráficas interactivas (flet-charts): tooltips al pasar el mouse y se adaptan al ancho."""

import math

import flet as ft
import flet_charts as fch

from ..dinero import formato
from ..fechas import nombre_periodo
from .componentes import ayuda, tarjeta, titulo_seccion
from .tema import AMARILLO, GRIS, MORADO, NARANJA, PALETA_PRODUCTOS, ROJO, VERDE, c

ALTO = 260


def pesos_corto(centavos: float) -> str:
    valor = centavos / 100
    if abs(valor) >= 1_000_000:
        return f"${valor / 1_000_000:.1f}M".replace(".", ",")
    if abs(valor) >= 1_000:
        return f"${valor / 1_000:.0f}k"
    return f"${valor:.0f}"


def _mes_corto(per: str) -> str:
    nombre = nombre_periodo(per)
    partes = nombre.split()
    return f"{partes[0][:3]} {partes[-1][-2:]}" if len(partes) >= 2 else nombre


def _escala(maximo: float, minimo: float = 0) -> tuple[float, float, float]:
    """Límites y paso «redondos» para el eje Y."""
    rango = max(maximo - minimo, 1)
    paso = 10 ** math.floor(math.log10(rango / 4))
    for m in (1, 2, 2.5, 5, 10):
        if rango / (paso * m) <= 5:
            paso *= m
            break
    return math.floor(minimo / paso) * paso, math.ceil(maximo / paso) * paso, paso


def _eje_y(minimo: float, maximo: float, paso: float, formato_valor=pesos_corto) -> fch.ChartAxis:
    etiquetas = []
    v = minimo
    while v <= maximo + paso / 2:
        etiquetas.append(fch.ChartAxisLabel(value=v, label=ft.Text(formato_valor(v), size=10, color=GRIS)))
        v += paso
    return fch.ChartAxis(labels=etiquetas, label_size=52)


def _eje_x(etiquetas: list[str]) -> fch.ChartAxis:
    return fch.ChartAxis(labels=[fch.ChartAxisLabel(value=i, label=ft.Container(
        ft.Text(t, size=10, color=GRIS), padding=ft.Padding.only(top=6))) for i, t in enumerate(etiquetas)],
        label_size=28)


def _leyenda(items: list[tuple[str, tuple]]) -> ft.Row:
    return ft.Row([ft.Row([ft.Container(width=10, height=10, bgcolor=c(col), border_radius=3),
                           ft.Text(t, size=11, color=GRIS)], spacing=4, tight=True) for t, col in items],
                  wrap=True, spacing=14)


def _vacio(mensaje: str) -> ft.Container:
    return ft.Container(ft.Text(mensaje, color=GRIS), height=ALTO / 2, alignment=ft.Alignment.CENTER)


def _marco(titulo: str, cuerpo: ft.Control, leyenda: ft.Control | None = None, nota: str = "",
           col=None) -> ft.Container:
    hijos = [titulo_seccion(titulo)]
    if leyenda:
        hijos.append(leyenda)
    hijos.append(cuerpo)
    if nota:
        hijos.append(ayuda(nota))
    return tarjeta(*hijos, col=col or {"xs": 12, "lg": 6}, espacio=10)


def _lineas_grilla(paso: float) -> fch.ChartGridLines:
    return fch.ChartGridLines(interval=paso, color=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE), dash_pattern=[3, 3])


# ---------------------------------------------------------------- gráficas

def en_que_gaste(por_categoria, col=None) -> ft.Container:
    """Barras horizontales (efectivo + tarjeta) por categoría: se leen bien a cualquier ancho."""
    filas = list(por_categoria)[:8]
    if not filas:
        return _marco("¿En qué gasté?", _vacio("Sin compras este mes"), col=col)
    maximo = max((f["efectivo"] or 0) + (f["tarjeta"] or 0) for f in filas) or 1
    controles = []
    for f in filas:
        efectivo, tarjeta_ = f["efectivo"] or 0, f["tarjeta"] or 0
        total = efectivo + tarjeta_
        resto = max(0, maximo - total)
        partes = []
        if efectivo:
            partes.append(ft.Container(bgcolor=c(VERDE), expand=efectivo, height=12,
                                       tooltip=f"Efectivo / débito: {formato(efectivo)}"))
        if tarjeta_:
            partes.append(ft.Container(bgcolor=c(MORADO), expand=tarjeta_, height=12,
                                       tooltip=f"Tarjeta: {formato(tarjeta_)}"))
        if resto:
            partes.append(ft.Container(expand=resto, height=12))
        controles.append(ft.Column([
            ft.Row([ft.Text(f["categoria"], size=13, expand=True), ft.Text(formato(total), size=13,
                                                                            weight=ft.FontWeight.W_600)]),
            ft.Container(ft.Row(partes, spacing=0), border_radius=6, clip_behavior=ft.ClipBehavior.HARD_EDGE,
                         bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)),
        ], spacing=4, tight=True))
    return _marco("¿En qué gasté?", ft.Column(controles, spacing=10, tight=True),
                  _leyenda([("Efectivo / débito", VERDE), ("Tarjeta de crédito", MORADO)]), col=col)


def entro_salio(filas: list[dict], col=None) -> ft.Container:
    if not any(f["entro"] or f["salio"] for f in filas):
        return _marco("Entró vs. salió de mi bolsillo", _vacio("Aún no hay movimientos"), col=col)
    minimo, maximo, paso = _escala(max(max(f["entro"], f["salio"]) for f in filas))
    grupos = [fch.BarChartGroup(x=i, rods=[
        fch.BarChartRod(from_y=0, to_y=f["entro"], width=10, color=c(VERDE), border_radius=3,
                        tooltip=f"{nombre_periodo(f['periodo'])}\nEntró {formato(f['entro'])}"),
        fch.BarChartRod(from_y=0, to_y=f["salio"], width=10, color=c(NARANJA), border_radius=3,
                        tooltip=f"Salió {formato(f['salio'])}")], spacing=4) for i, f in enumerate(filas)]
    grafica = fch.BarChart(groups=grupos, height=ALTO, min_y=minimo, max_y=maximo, interactive=True,
                           left_axis=_eje_y(minimo, maximo, paso), bottom_axis=_eje_x([_mes_corto(f["periodo"])
                                                                                       for f in filas]),
                           horizontal_grid_lines=_lineas_grilla(paso), animation=ft.Animation(400))
    return _marco("Entró vs. salió de mi bolsillo", grafica, _leyenda([("Entró", VERDE), ("Salió", NARANJA)]),
                  col=col)


def proyeccion(datos: dict[str, dict[str, int]], ingreso_mensual: int, col=None) -> ft.Container:
    titulo = "¿Cuándo termino de pagar? (próximos 12 meses)"
    periodos = list(datos)
    productos = sorted({p for fila in datos.values() for p in fila})
    if not productos:
        return _marco(titulo, _vacio("No hay cuotas pendientes"), col=col)
    colores = {p: PALETA_PRODUCTOS[i % len(PALETA_PRODUCTOS)] for i, p in enumerate(productos)}
    totales = [sum(datos[p].values()) for p in periodos]
    techo = max(max(totales), ingreso_mensual * 0.5 if ingreso_mensual else 0)
    minimo, maximo, paso = _escala(techo)
    grupos = []
    for i, per in enumerate(periodos):
        base, pilas = 0, []
        for prod in productos:
            v = datos[per].get(prod, 0)
            if v:
                pilas.append(fch.BarChartRodStackItem(from_y=base, to_y=base + v, color=c(colores[prod])))
                base += v
        detalle = "\n".join(f"{p}: {formato(datos[per][p])}" for p in productos if datos[per].get(p))
        pct = f"\n{base / ingreso_mensual * 100:.0f} % del ingreso" if ingreso_mensual and base else ""
        grupos.append(fch.BarChartGroup(x=i, rods=[fch.BarChartRod(
            from_y=0, to_y=base, width=18, stack_items=pilas, border_radius=4, color=c(MORADO),
            tooltip=f"{nombre_periodo(per)} · {formato(base)}{pct}\n{detalle}" if base else nombre_periodo(per))]))
    grafica = fch.BarChart(groups=grupos, height=ALTO, min_y=minimo, max_y=maximo, interactive=True,
                           left_axis=_eje_y(minimo, maximo, paso), bottom_axis=_eje_x([_mes_corto(p) for p in periodos]),
                           horizontal_grid_lines=_lineas_grilla(paso), animation=ft.Animation(400))
    nota = ""
    if ingreso_mensual:
        nota = (f"Referencia: 20 % de tu ingreso = {formato(round(ingreso_mensual * .2))} · 35 % = "
                f"{formato(round(ingreso_mensual * .35))} · 50 % = {formato(round(ingreso_mensual * .5))}. "
                "Pasa el mouse por una barra para ver el detalle.")
    return _marco(titulo, grafica, _leyenda([(p, colores[p]) for p in productos]), nota, col=col)


def historial(filas: list[dict], col=None) -> ft.Container:
    titulo = "¿Cuánto me cuesta la deuda?"
    if not any(f["costo_deuda"] or f["pagos_credito"] for f in filas):
        return _marco(titulo, _vacio("Aún no hay pagos registrados"), col=col)
    minimo, maximo, paso = _escala(max(f["costo_deuda"] for f in filas) or 1)
    grupos = []
    for i, f in enumerate(filas):
        ratio = f["ratio"]
        color = ROJO if ratio is not None and ratio >= .5 else NARANJA if ratio is not None and ratio >= .35 else \
            AMARILLO if ratio is not None and ratio >= .2 else VERDE if ratio is not None else MORADO
        pct = f"\n{ratio * 100:.0f} % del ingreso se fue en deuda" if ratio is not None else ""
        grupos.append(fch.BarChartGroup(x=i, rods=[fch.BarChartRod(
            from_y=0, to_y=f["costo_deuda"], width=16, color=c(color), border_radius=4,
            tooltip=f"{nombre_periodo(f['periodo'])}\nIntereses y cargos: {formato(f['costo_deuda'])}{pct}")]))
    grafica = fch.BarChart(groups=grupos, height=ALTO, min_y=minimo, max_y=maximo, interactive=True,
                           left_axis=_eje_y(minimo, maximo, paso),
                           bottom_axis=_eje_x([_mes_corto(f["periodo"]) for f in filas]),
                           horizontal_grid_lines=_lineas_grilla(paso), animation=ft.Animation(400))
    return _marco(titulo, grafica, _leyenda([("< 20 % del ingreso", VERDE), ("20–35 %", AMARILLO),
                                            ("35–50 %", NARANJA), ("≥ 50 %", ROJO)]),
                  "Altura = intereses y cargos pagados. Color = qué parte de tu ingreso se fue en deuda ese mes.",
                  col=col)


def patrimonio(filas: list[dict], col=None) -> ft.Container:
    titulo = "Patrimonio al cierre de cada mes (lo que tienes − lo que debes)"
    if not any(f["activos"] or f["deuda"] for f in filas):
        return _marco(titulo, _vacio("Aún no hay movimientos"), col=col)
    valores = [f["patrimonio"] for f in filas]
    minimo, maximo, paso = _escala(max(max(valores), 0), min(min(valores), 0))
    puntos = [fch.LineChartDataPoint(x=i, y=v, tooltip=f"{nombre_periodo(f['periodo'])}\n{formato(v)}")
              for i, (f, v) in enumerate(zip(filas, valores))]
    serie = fch.LineChartData(points=puntos, curved=True, color=c(MORADO), stroke_width=3,
                              point=fch.ChartCirclePoint(radius=4, color=c(MORADO)),
                              below_line_bgcolor=ft.Colors.with_opacity(0.12, c(MORADO)), prevent_curve_over_shooting=True)
    grafica = fch.LineChart(data_series=[serie], height=ALTO, min_y=minimo, max_y=maximo, min_x=-0.3,
                            max_x=len(filas) - 0.7, interactive=True, left_axis=_eje_y(minimo, maximo, paso),
                            bottom_axis=_eje_x([_mes_corto(f["periodo"]) for f in filas]),
                            horizontal_grid_lines=_lineas_grilla(paso), animation=ft.Animation(400))
    return _marco(titulo, grafica, col=col or {"xs": 12})
