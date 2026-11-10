"""Conexión SQLite, esquema, ubicación de los datos y respaldos.

Los montos se guardan como enteros en centavos y las fechas como texto ISO (AAAA-MM-DD).
"""

import os
import sqlite3
import zipfile
from datetime import date, datetime
from pathlib import Path

# Tipos: tarjeta de crédito, cupo de crédito (Addi, Sistecrédito, almacenes) y préstamo.
TABLA_PRODUCTOS = """
CREATE TABLE IF NOT EXISTS {nombre} (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL,
    entidad TEXT NOT NULL DEFAULT '',
    tipo TEXT NOT NULL DEFAULT 'tarjeta' CHECK (tipo IN ('tarjeta', 'cupo', 'prestamo')),
    cupo INTEGER NOT NULL DEFAULT 0,
    tasa_ea REAL NOT NULL DEFAULT 0,
    dia_corte INTEGER NOT NULL DEFAULT 1,
    dia_pago INTEGER NOT NULL DEFAULT 15,
    cuota_manejo INTEGER NOT NULL DEFAULT 0,
    interes_una_cuota INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1
);
"""

ESQUEMA = """
CREATE TABLE IF NOT EXISTS configuracion (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    grupo TEXT NOT NULL DEFAULT 'necesidad' CHECK (grupo IN ('necesidad', 'deseo')),
    activa INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS fuentes_ingreso (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL,
    monto_mensual INTEGER NOT NULL,
    dias_pago TEXT NOT NULL,
    variable INTEGER NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'activa' CHECK (estado IN ('activa', 'esperada', 'inactiva'))
);

CREATE TABLE IF NOT EXISTS ingresos (
    id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL,
    fuente_id INTEGER REFERENCES fuentes_ingreso(id) ON DELETE SET NULL,
    monto INTEGER NOT NULL CHECK (monto > 0),
    tipo TEXT NOT NULL DEFAULT 'ordinario' CHECK (tipo IN ('ordinario', 'extraordinario')),
    descripcion TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS servicios (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL,
    categoria_id INTEGER REFERENCES categorias(id),
    monto_estimado INTEGER NOT NULL,
    dia_vencimiento INTEGER NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS compras (
    id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL,
    descripcion TEXT NOT NULL DEFAULT '',
    categoria_id INTEGER REFERENCES categorias(id),
    monto INTEGER NOT NULL CHECK (monto > 0),
    medio TEXT NOT NULL CHECK (medio IN ('efectivo', 'tarjeta')),
    producto_id INTEGER REFERENCES productos_credito(id),
    num_cuotas INTEGER,
    servicio_id INTEGER REFERENCES servicios(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS refinanciaciones (
    id INTEGER PRIMARY KEY,
    producto_id INTEGER NOT NULL REFERENCES productos_credito(id),
    fecha TEXT NOT NULL,
    deuda_total INTEGER NOT NULL,
    valor_pagado INTEGER NOT NULL,
    saldo INTEGER NOT NULL,
    num_cuotas INTEGER NOT NULL,
    cuota INTEGER NOT NULL,
    tasa_ea REAL,
    ea_implicita REAL,
    credito_id INTEGER,
    pago_id INTEGER
);

CREATE TABLE IF NOT EXISTS creditos (
    id INTEGER PRIMARY KEY,
    producto_id INTEGER NOT NULL REFERENCES productos_credito(id),
    compra_id INTEGER REFERENCES compras(id) ON DELETE CASCADE,
    origen TEXT NOT NULL CHECK (origen IN ('compra', 'deuda_existente', 'refinanciacion')),
    descripcion TEXT NOT NULL DEFAULT '',
    fecha TEXT NOT NULL,
    monto INTEGER NOT NULL,
    num_cuotas INTEGER NOT NULL,
    tasa_ea REAL NOT NULL,
    metodo TEXT NOT NULL CHECK (metodo IN ('abono_constante', 'cuota_fija')),
    estado TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo', 'pagado', 'refinanciado')),
    refinanciacion_id INTEGER REFERENCES refinanciaciones(id)
);

CREATE TABLE IF NOT EXISTS pagos_credito (
    id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL,
    producto_id INTEGER NOT NULL REFERENCES productos_credito(id),
    monto INTEGER NOT NULL CHECK (monto > 0),
    tipo TEXT NOT NULL,
    a_capital INTEGER NOT NULL DEFAULT 0,
    a_costos INTEGER NOT NULL DEFAULT 0,
    abono_extra INTEGER NOT NULL DEFAULT 0,
    desde_reserva INTEGER NOT NULL DEFAULT 0,
    notas TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cuotas (
    id INTEGER PRIMARY KEY,
    credito_id INTEGER NOT NULL REFERENCES creditos(id) ON DELETE CASCADE,
    numero INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    capital INTEGER NOT NULL,
    interes INTEGER NOT NULL,
    otros INTEGER NOT NULL DEFAULT 0,
    pagado INTEGER NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente', 'pagada', 'refinanciada', 'reemplazada')),
    creada_por_pago INTEGER REFERENCES pagos_credito(id),
    reemplazada_por_pago INTEGER REFERENCES pagos_credito(id)
);

CREATE TABLE IF NOT EXISTS pagos_aplicacion (
    pago_id INTEGER NOT NULL REFERENCES pagos_credito(id) ON DELETE CASCADE,
    cuota_id INTEGER NOT NULL REFERENCES cuotas(id) ON DELETE CASCADE,
    monto INTEGER NOT NULL,
    a_costos INTEGER NOT NULL,
    a_capital INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS extractos (
    id INTEGER PRIMARY KEY,
    producto_id INTEGER NOT NULL REFERENCES productos_credito(id),
    fecha_corte TEXT NOT NULL,
    fecha_limite TEXT NOT NULL,
    capital_mes INTEGER NOT NULL DEFAULT 0,
    intereses INTEGER NOT NULL DEFAULT 0,
    comisiones_avances INTEGER NOT NULL DEFAULT 0,
    comisiones_servicio INTEGER NOT NULL DEFAULT 0,
    cargos_conversion INTEGER NOT NULL DEFAULT 0,
    abonos INTEGER NOT NULL DEFAULT 0,
    devoluciones INTEGER NOT NULL DEFAULT 0,
    pago_minimo INTEGER NOT NULL,
    deuda_restante INTEGER NOT NULL DEFAULT 0,
    pago_total INTEGER NOT NULL,
    UNIQUE (producto_id, fecha_corte)
);

CREATE TABLE IF NOT EXISTS reserva_movimientos (
    id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('aporte', 'uso', 'rendimiento', 'retiro')),
    monto INTEGER NOT NULL,
    pago_id INTEGER REFERENCES pagos_credito(id) ON DELETE CASCADE,
    notas TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cierres_mensuales (
    periodo TEXT PRIMARY KEY,
    deuda_total INTEGER NOT NULL,
    reserva INTEGER NOT NULL,
    creado TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_ingresos_fecha ON ingresos(fecha);
CREATE INDEX IF NOT EXISTS ix_compras_fecha ON compras(fecha);
CREATE INDEX IF NOT EXISTS ix_cuotas_credito ON cuotas(credito_id, estado);
CREATE INDEX IF NOT EXISTS ix_cuotas_fecha ON cuotas(fecha);
CREATE INDEX IF NOT EXISTS ix_pagos_fecha ON pagos_credito(fecha);

-- Tasas legales certificadas por periodo y modalidad (IBC y usura). Las ingresa el usuario.
CREATE TABLE IF NOT EXISTS tasas_legales (
    id INTEGER PRIMARY KEY,
    modalidad TEXT NOT NULL DEFAULT 'consumo',
    desde TEXT NOT NULL,
    hasta TEXT NOT NULL,
    ibc_ea REAL,
    usura_ea REAL NOT NULL,
    notas TEXT NOT NULL DEFAULT ''
);

-- Intereses de mora y gastos de cobranza liquidados (uno por tramo o periodo: evita cobros duplicados).
CREATE TABLE IF NOT EXISTS cargos_mora (
    id INTEGER PRIMARY KEY,
    credito_id INTEGER NOT NULL REFERENCES creditos(id) ON DELETE CASCADE,
    cuota_id INTEGER NOT NULL REFERENCES cuotas(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL CHECK (tipo IN ('mora', 'cobranza')),
    clave TEXT NOT NULL,
    desde TEXT NOT NULL,
    hasta TEXT NOT NULL,
    base INTEGER NOT NULL DEFAULT 0,
    tasa_ea REAL,
    monto INTEGER NOT NULL,
    pago_id INTEGER REFERENCES pagos_credito(id) ON DELETE CASCADE,
    UNIQUE (credito_id, tipo, clave)
);

-- Cambios que la app hace sobre una cuota ya creada (interés conciliado con el extracto o
-- interés causado al cancelar antes): guardan el valor anterior para poder deshacerlos.
CREATE TABLE IF NOT EXISTS ajustes_cuota (
    id INTEGER PRIMARY KEY,
    cuota_id INTEGER NOT NULL REFERENCES cuotas(id) ON DELETE CASCADE,
    campo TEXT NOT NULL,
    antes INTEGER NOT NULL,
    despues INTEGER NOT NULL,
    motivo TEXT NOT NULL CHECK (motivo IN ('extracto', 'prepago')),
    pago_id INTEGER,
    extracto_id INTEGER
);

-- Cajas de ahorro: una por objetivo (viaje, consola, fondo de emergencia...).
CREATE TABLE IF NOT EXISTS metas_ahorro (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'otro',
    objetivo INTEGER NOT NULL CHECK (objetivo > 0),
    fecha_objetivo TEXT,
    prioridad INTEGER NOT NULL DEFAULT 2 CHECK (prioridad IN (1, 2, 3)),
    estado TEXT NOT NULL DEFAULT 'activa' CHECK (estado IN ('activa', 'pausada', 'archivada')),
    creada TEXT NOT NULL,
    notas TEXT NOT NULL DEFAULT ''
);

-- Abonos (+) y retiros (-) de cada caja. `externo` = plata que ya estaba ahorrada fuera de la app:
-- no se descuenta del disponible.
CREATE TABLE IF NOT EXISTS ahorro_movimientos (
    id INTEGER PRIMARY KEY,
    meta_id INTEGER NOT NULL REFERENCES metas_ahorro(id) ON DELETE CASCADE,
    fecha TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('abono', 'retiro')),
    monto INTEGER NOT NULL,
    externo INTEGER NOT NULL DEFAULT 0,
    compra_id INTEGER REFERENCES compras(id) ON DELETE SET NULL,
    notas TEXT NOT NULL DEFAULT ''
);

-- Gastos puntuales que sabes que vienen en un mes (regalo, matrícula, SOAT...).
CREATE TABLE IF NOT EXISTS gastos_previstos (
    id INTEGER PRIMARY KEY,
    periodo TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    monto INTEGER NOT NULL CHECK (monto > 0)
);

-- Ajustes del disponible (lo que hay en tu cuenta/bolsillo) para que cuadre con la realidad.
CREATE TABLE IF NOT EXISTS ajustes_disponible (
    id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL,
    monto INTEGER NOT NULL,
    notas TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS ix_ahorro_meta ON ahorro_movimientos(meta_id, fecha);

-- Historial de cambios de productos, condiciones y tasas, y de lo que se elimina.
CREATE TABLE IF NOT EXISTS historial_cambios (
    id INTEGER PRIMARY KEY,
    creado TEXT NOT NULL,
    entidad TEXT NOT NULL,
    entidad_id INTEGER,
    accion TEXT NOT NULL,
    antes TEXT,
    despues TEXT
);
"""

# Columnas agregadas después de la primera versión: (tabla, columna, definición).
COLUMNAS_NUEVAS = [
    ("productos_credito", "condiciones", "TEXT"),               # Plantilla de condiciones (JSON)
    ("creditos", "condiciones", "TEXT"),                        # Fotografía de la oferta aceptada (JSON)
    ("creditos", "precio_contado", "INTEGER"),
    ("creditos", "cuota_inicial", "INTEGER NOT NULL DEFAULT 0"),
    ("creditos", "cargos_iniciales", "INTEGER NOT NULL DEFAULT 0"),
    ("creditos", "periodicidad", "TEXT NOT NULL DEFAULT 'mensual'"),
    ("cuotas", "mora", "INTEGER NOT NULL DEFAULT 0"),
    ("cuotas", "cobranza", "INTEGER NOT NULL DEFAULT 0"),
    ("cuotas", "mora_hasta", "TEXT"),
    ("cuotas", "detalle", "TEXT"),                              # Cargos de la cuota por nombre (JSON)
    ("cuotas", "pagado_capital", "INTEGER NOT NULL DEFAULT 0"),
    ("cuotas", "pagado_interes", "INTEGER NOT NULL DEFAULT 0"),
    ("cuotas", "pagado_otros", "INTEGER NOT NULL DEFAULT 0"),
    ("cuotas", "pagado_mora", "INTEGER NOT NULL DEFAULT 0"),
    ("cuotas", "pagado_cobranza", "INTEGER NOT NULL DEFAULT 0"),
    ("pagos_aplicacion", "a_interes", "INTEGER NOT NULL DEFAULT 0"),
    ("pagos_aplicacion", "a_otros", "INTEGER NOT NULL DEFAULT 0"),
    ("pagos_aplicacion", "a_mora", "INTEGER NOT NULL DEFAULT 0"),
    ("pagos_aplicacion", "a_cobranza", "INTEGER NOT NULL DEFAULT 0"),
    ("pagos_credito", "canal", "TEXT NOT NULL DEFAULT ''"),
    ("pagos_credito", "credito_id", "INTEGER"),                 # Devoluciones: crédito al que se aplican
    ("refinanciaciones", "tipo", "TEXT NOT NULL DEFAULT 'refinanciacion'"),
    ("compras", "cuota_inicial", "INTEGER NOT NULL DEFAULT 0"),
    ("compras", "pago_parcial", "INTEGER NOT NULL DEFAULT 0"),  # Pago de servicio que deja saldo pendiente
    ("reserva_movimientos", "compra_id", "INTEGER REFERENCES compras(id) ON DELETE CASCADE"),  # Servicio pagado con la reserva
    ("creditos", "dia_pago", "INTEGER"),                        # Día de pago pactado (ancla de las fechas)
    ("pagos_credito", "a_manejo", "INTEGER NOT NULL DEFAULT 0"),  # Cuota de manejo / comisiones del ciclo cubiertas
    ("pagos_credito", "ciclo", "TEXT"),                         # Fecha límite del ciclo al que se aplicó el pago
    ("pagos_credito", "saldo_favor", "INTEGER NOT NULL DEFAULT 0"),  # Lo que no se pudo aplicar (queda a favor)
]

CATEGORIAS_INICIALES = [
    ("Vivienda", "necesidad"), ("Servicios", "necesidad"), ("Comida", "necesidad"),
    ("Mercado", "necesidad"), ("Transporte", "necesidad"), ("Salud", "necesidad"),
    ("Educación", "necesidad"), ("Seguridad social", "necesidad"),
    ("Ropa", "deseo"), ("Entretenimiento", "deseo"), ("Suscripciones", "deseo"),
    ("Tecnología", "deseo"), ("Restaurantes", "deseo"), ("Regalos", "deseo"), ("Otros", "deseo"),
]

CONFIG_INICIAL = {
    "umbral_sano": "20",
    "umbral_moderado": "35",
    "umbral_alto": "50",
    "reparto_sano": "30,20,50",
    "reparto_moderado": "25,35,40",
    "reparto_alto": "15,60,25",
    "reparto_critico": "10,90,0",
    "estrategia": "avalancha",
    "tasa_cajita_ea": "0",
    "tasa_usura_ea": "0",
    "dia_a_dia_estimado": "0",
    "dias_alerta": "7",
    "ultimo_vacuum": "",
}

RESPALDOS_DIARIOS = 7
RESPALDOS_MENSUALES = 12


def carpeta_datos() -> Path:
    """Documentos/Finanzas, o la carpeta de la variable de entorno FINANZAS_DATOS."""
    if os.environ.get("FINANZAS_DATOS"):
        carpeta = Path(os.environ["FINANZAS_DATOS"])
    else:
        documentos = Path.home() / "Documents"
        carpeta = (documentos if documentos.exists() else Path.home()) / "Finanzas"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def conectar(ruta: Path | str | None = None, multihilo: bool = False) -> sqlite3.Connection:
    """Abre (y migra) la base. `multihilo` permite usarla desde los hilos de eventos de la interfaz Flet."""
    ruta = ruta or carpeta_datos() / "finanzas.db"
    con = sqlite3.connect(ruta, detect_types=0, check_same_thread=not multihilo)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    inicializar(con)
    return con


def inicializar(con: sqlite3.Connection) -> None:
    con.executescript(ESQUEMA + TABLA_PRODUCTOS.format(nombre="productos_credito"))
    _migrar_productos(con)
    _migrar_columnas(con)
    for clave, valor in CONFIG_INICIAL.items():
        con.execute("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES (?, ?)", (clave, valor))
    if con.execute("SELECT COUNT(*) FROM categorias").fetchone()[0] == 0:
        con.executemany("INSERT INTO categorias (nombre, grupo) VALUES (?, ?)", CATEGORIAS_INICIALES)
    con.commit()


def _migrar_productos(con: sqlite3.Connection) -> None:
    """Bases creadas antes de los cupos de crédito no aceptan el tipo 'cupo': se reconstruye la tabla."""
    sql = con.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'productos_credito'").fetchone()[0]
    if "'cupo'" in sql:
        return
    con.commit()
    con.execute("PRAGMA foreign_keys = OFF")
    try:
        con.executescript("BEGIN;" + TABLA_PRODUCTOS.format(nombre="productos_nueva")
                          + "INSERT INTO productos_nueva SELECT * FROM productos_credito;"
                            "DROP TABLE productos_credito;"
                            "ALTER TABLE productos_nueva RENAME TO productos_credito;"
                            "COMMIT;")
    except sqlite3.Error:
        con.rollback()
        raise
    finally:
        con.execute("PRAGMA foreign_keys = ON")


def respaldar(con: sqlite3.Connection, carpeta: Path, hoy: date | None = None) -> Path | None:
    """Crea el respaldo del día (si no existe) y borra los que sobran.

    Se conservan los últimos 7 respaldos diarios y el primero de cada uno de los
    últimos 12 meses.
    """
    hoy = hoy or date.today()
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"finanzas_{hoy.isoformat()}.zip"
    creado = None
    if not destino.exists():
        temporal = carpeta / "respaldo_temporal.db"
        copia = sqlite3.connect(temporal)
        con.backup(copia)
        copia.close()
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(temporal, "finanzas.db")
        temporal.unlink()
        creado = destino
    _rotar_respaldos(carpeta)
    return creado


def _migrar_columnas(con: sqlite3.Connection) -> None:
    """Agrega las columnas nuevas sin tocar los datos existentes.

    Al crear las columnas de pago por componente, reparte lo ya pagado como lo hacía
    la versión anterior: primero intereses y cargos, luego capital.
    """
    nuevas = []
    for tabla, columna, definicion in COLUMNAS_NUEVAS:
        existentes = {f[1] for f in con.execute(f"PRAGMA table_info({tabla})")}
        if columna not in existentes:
            con.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
            nuevas.append((tabla, columna))
    if ("cuotas", "pagado_capital") in nuevas:
        con.execute("UPDATE cuotas SET pagado_interes = MIN(pagado, interes), "
                    "pagado_otros = MIN(MAX(pagado - interes, 0), otros), "
                    "pagado_capital = MAX(pagado - interes - otros, 0)")
    if ("pagos_aplicacion", "a_interes") in nuevas:
        con.execute("UPDATE pagos_aplicacion SET a_interes = MIN(a_costos, "
                    "(SELECT interes FROM cuotas WHERE cuotas.id = pagos_aplicacion.cuota_id)), "
                    "a_otros = a_costos - MIN(a_costos, "
                    "(SELECT interes FROM cuotas WHERE cuotas.id = pagos_aplicacion.cuota_id))")
    con.commit()


def respaldar_archivo(ruta: Path, carpeta: Path) -> None:
    """Respaldo del día de una base existente, sin abrirla con el esquema (antes de migrarla)."""
    if not ruta.exists():
        return
    con = sqlite3.connect(ruta)
    try:
        respaldar(con, carpeta)
    finally:
        con.close()


def _rotar_respaldos(carpeta: Path) -> None:
    respaldos = sorted(carpeta.glob("finanzas_????-??-??.zip"), reverse=True)
    conservar = set(respaldos[:RESPALDOS_DIARIOS])
    primeros_de_mes: dict[str, Path] = {}
    for r in respaldos:  # De más nuevo a más viejo: el último asignado es el primero del mes.
        primeros_de_mes[r.stem[10:17]] = r
    for mes in sorted(primeros_de_mes, reverse=True)[:RESPALDOS_MENSUALES]:
        conservar.add(primeros_de_mes[mes])
    for r in respaldos:
        if r not in conservar:
            r.unlink()


def mantenimiento(con: sqlite3.Connection, carpeta_respaldos: Path) -> None:
    """Respaldo diario y compactación mensual (VACUUM)."""
    respaldar(con, carpeta_respaldos)
    fila = con.execute("SELECT valor FROM configuracion WHERE clave = 'ultimo_vacuum'").fetchone()
    ultimo = fila["valor"] if fila else ""
    hoy = date.today()
    if not ultimo or (hoy - datetime.strptime(ultimo, "%Y-%m-%d").date()).days >= 30:
        con.execute("VACUUM")
        con.execute("UPDATE configuracion SET valor = ? WHERE clave = 'ultimo_vacuum'", (hoy.isoformat(),))
        con.commit()
