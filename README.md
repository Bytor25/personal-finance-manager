# Finanzas Personales

Aplicación de escritorio para Windows (Python + SQLite) para registrar ingresos, compras, servicios y créditos, ver el nivel de endeudamiento y obtener un **plan para repartir cada ingreso**, con la meta de **tener ahorrado un mes por adelantado** el pago de las deudas.

**Contexto:** Colombia · pesos colombianos (COP) · tasas en E.A. / M.V. · pensada para tarjetas tipo Nu y reserva en una Cajita.

> Documento vivo: registra cómo funciona la app, cómo calcula y qué falta por validar. Cuando algo se vea raro al usarla, se anota en la sección 9 y se corrige.

---

## 1. Cómo usarla

### Abrir
`dist\Finanzas\Finanzas.exe` (se puede crear un acceso directo). Los datos se guardan en `Documentos\Finanzas\finanzas.db`.

### Primeros pasos (una sola vez)
1. **Configuración → Ingresos:** agrega tu fuente de ingreso con lo que recibes **al mes** y los **días de pago** (`15,30` quincenal, `30` mensual). Un ingreso que aún no es seguro (ej. freelance) se marca como **Esperado**.
2. **Configuración → Parámetros:** tasa de la Cajita (% E.A.) y, si quieres, un estimado de gasto del día a día al mes.
3. **Tarjetas y deudas → + Tarjeta / crédito:** elige el tipo:

   | Tipo | Ejemplos | Qué pide | Cómo calcula las cuotas |
   |---|---|---|---|
   | Tarjeta de crédito | Nu, Visa, tarjeta Agaval | Tasa E.A., día de corte, día límite de pago, cupo, cuota de manejo | Capital fijo + intereses; la primera cuota según el corte |
   | Cupo de crédito | Addi, Sistecrédito, crédito de almacén (ej. Chevignon) | Cupo (editable si es variable; 0 = sin cupo fijo) y tasa E.A. (0 si es sin intereses) | Cuota fija; cada compra vence en su propio día, la primera un mes después de la compra |
   | Préstamo | Libre inversión, vehículo | Tasa E.A. y día de pago | Cuota fija |

   Si el almacén te da una tarjeta con fecha de corte y extracto, regístrala como **tarjeta**.
4. Lo que ya debes, regístralo de una de estas formas:
   - **+ Cuotas que ya tenía:** una vez por cada compra a cuotas o préstamo que ya venía corriendo (ver "Cuotas que ya tenía" abajo).
   - **🧩 Organizar deuda:** si refinanciaste la deuda de la tarjeta (ver sección 4.5).
5. **Servicios:** arriendo, luz, internet, celular, salud/pensión… con su día de vencimiento.

### Cuotas que ya tenía
Selecciona la tarjeta o el cupo en la tabla y presiona **+ Cuotas que ya tenía**. Se copian los datos que muestra la app del banco o del cupo para cada compra:

| Campo | De dónde sale | Ejemplo |
|---|---|---|
| Valor original | Valor de la compra | 1.200.000 |
| Número total de cuotas | La N de "cuota n de N" | 12 |
| Cuotas que ya pagaste | Si dice "cuota 5 de 12" y esa aún no la pagas → 4 | 4 |
| Fecha de la próxima cuota | Ver abajo | 17/11/2026 |
| Tasa E.A. | La de la compra; 0 si es sin intereses | 28,5 |
| Valor de la cuota *(opcional)* | Solo en cuota fija; ajusta el cronograma a ella | |
| Saldo pendiente *(opcional)* | Si la app lo muestra; si no, se calcula | |
| Cargo fijo por cuota *(opcional)* | Aval, fianza o costo de plataforma | |

**Fecha de la próxima cuota:** la fecha en la que vas a pagar la siguiente cuota de esa compra, en formato `AAAA-MM-DD` o `DD/MM/AAAA`.
- **Tarjeta:** es la **fecha límite de pago** del extracto en el que te la cobran. La app sugiere el próximo día límite de pago; si ya pagaste la cuota de este mes, pon la del mes siguiente.
- **Cupo (Addi, Sistecrédito, almacén):** cada compra tiene su propia fecha; mírala en la app del cupo.
- Las demás cuotas se ubican mes a mes desde esa fecha.

Al guardar, la app muestra saldo, cuotas que faltan, próxima y última cuota para compararlas con la app del banco. Si escribiste el valor de la cuota y equivale a una tasa distinta de la que pusiste, lo avisa (puede incluir seguros u otros cargos).

### Uso diario
| Cuándo | Dónde | Qué hacer |
|---|---|---|
| Compras algo | Ingresos y compras → **+ Compra** | Eliges cómo pagaste. A crédito (tarjeta o cupo), indicas las cuotas y se crea el cronograma. Opcional: tasa de esa compra (0 = sin intereses), fecha de la primera cuota y cargo fijo por cuota. Si la compra supera el cupo disponible, la app avisa y pregunta si registrarla igual. |
| Te pagan | Ingresos y compras → **+ Ingreso**, luego **Plan del ingreso** | El plan dice cuánto apartar, cuánto pagar a cada tarjeta y cuánto queda libre. |
| Apartas en la Cajita | Plan del ingreso → **Apartar en la reserva** (o Reserva → + Aporte) | |
| Ahorras para algo | Ahorros (cajas) → **Abonar** o **Repartir un abono entre cajas** (o Plan del ingreso → Abonar a mis cajas) | |
| Empieza el mes | Ahorros (cajas) | Agrega los **gastos previstos** del mes y mira cuánto y cuándo ahorrar. Si traes saldo a favor, muévelo a las cajas. |
| Pagas un servicio | Servicios → **✓ Marcar pagado** | |
| Pagas la tarjeta | Tarjetas y deudas → **💸 Registrar pago** | Marca si salió de la reserva. Si pagas más del mínimo, eliges si reduce plazo o cuota. |
| Llega el extracto | Tarjetas y deudas → **📄 Registrar extracto** | Copias el resumen; la app calcula mínimo y total para que los compares. |

---

## 2. Cómo se ve la información

Toda la app responde **cuatro preguntas**:

| Pregunta | Qué incluye |
|---|---|
| 💵 **¿Cuánto entró?** | Ingresos del mes |
| 👛 **¿Cuánto salió de mi bolsillo?** | Compras en efectivo/débito + pagos a tarjetas y créditos |
| 🛒 **¿En qué gasté?** | Todas las compras por categoría: verde efectivo, morado tarjeta |
| 💳 **¿Cuánto debo?** | Saldo de capital de tarjetas y créditos, y lo que toca pagar el próximo mes |

Además, Inicio muestra el **saldo a favor**: cada mes nuevo las cifras del mes arrancan en **$0**, pero lo que sobró del mes anterior aparece como "💰 Saldo a favor" y se suma a lo que entre.

| Cifra | Cálculo |
|---|---|
| 💰 **Saldo a favor** | Lo que quedó disponible al cerrar el mes anterior |
| ✅ **¿Cuánto me queda?** | Saldo a favor + entró − salió − lo apartado en la reserva y en las cajas (+ ajustes) |
| 🐷 **¿Cuánto tengo ahorrado?** | Cajas de ahorro + reserva (Cajita) |
| 📊 **Patrimonio** | Disponible + reserva + cajas − deuda |

**Regla de la tarjeta:** comprar con tarjeta no saca plata del bolsillo, aumenta lo que debes. Pagarla sí saca plata y disminuye lo que debes. Lo único que realmente se pierde son los **intereses y cargos**, que aparecen como **"Costo de la deuda"**. Ninguna compra se cuenta dos veces.

### Pantallas
| Pantalla | Contenido |
|---|---|
| Inicio | Las 4 preguntas del mes, medidor de endeudamiento, progreso del mes adelantado, alertas (pagos vencidos, pagos próximos con los días de anticipación de Configuración, cupo > 70 %, usura por deuda, saldo a favor, reserva negativa, pago menor al mínimo, deudas terminadas), gráficas "¿En qué gasté?" y "Entró vs. salió". |
| Ingresos y compras | Listado por mes, formulario único de compra. |
| Servicios | Pagos recurrentes y si ya se pagaron este mes. |
| Tarjetas y deudas | Por tarjeta: tasa, saldo, uso del cupo, próximo pago (mínimo / total / intereses si pagas solo el mínimo). Deudas activas con su cronograma, pagos, extractos, deudas organizadas. Gráficas "¿Cuándo termino de pagar?" y "¿Cuánto me cuesta la deuda?". |
| Plan del ingreso | Reparto de un ingreso real o simulado y cuánto pagar a cada tarjeta. |
| Reserva (Cajita) | Saldo, meta del mes siguiente, rendimiento estimado, movimientos. |
| Ahorros (cajas) | Cajas por objetivo (viaje, consola, juego, personal, fondo de emergencia…), cuánto y cuándo ahorrar el mes elegido, gastos previstos del mes, saldo a favor, patrimonio y su gráfica de 6 meses. |
| Configuración | Fuentes de ingreso, parámetros del plan, categorías, carpeta de datos y exportación a Excel. |

---

## 3. Datos y almacenamiento

- **SQLite**: un solo archivo, sin servidor, gratis, incluido en Python. Excel solo como **exportación de lectura** (Configuración → Datos).
- **Montos en centavos (enteros)** para no tener errores de redondeo. Los cronogramas se redondean a **pesos enteros**; los extractos conservan centavos.
- **No hay una tabla por mes:** todo tiene fecha y el mes se filtra. Al abrir la app en un mes nuevo se guarda un **cierre** del mes anterior (deuda total y reserva).
- **Respaldos:** cada día que se abre la app se crea `respaldos\finanzas_AAAA-MM-DD.zip`. Se conservan 7 diarios + el primero de cada mes durante 12 meses. Compactación (`VACUUM`) mensual.
- **Espacio:** la base ocupa ~100 KB vacía y menos de 1 MB por año de uso; cada respaldo pesa pocos KB. El ejecutable ocupa ~90 MB.

---

## 4. Cálculos

Código en [finanzas/credito.py](finanzas/credito.py) y [finanzas/plan.py](finanzas/plan.py) (funciones puras con tests).

### 4.1 Tasas
```
M.V. = (1 + E.A.)^(1/12) − 1        ej.: 27 % E.A. ≈ 2,01 % M.V.
```

### 4.2 Compras con tarjeta: abono constante a capital
```
capital de cada cuota = valor / número de cuotas   (fijo)
interés del mes       = saldo pendiente × M.V.     (baja cada mes)
```
- La **primera cuota** vence en el día de pago siguiente al corte en que entra la compra (compra después del corte → mes siguiente).
- **1 cuota:** sin intereses, salvo que la tarjeta esté configurada para cobrarlos.
- Ejemplo: $1.200.000 a 12 cuotas, 27 % E.A. → primera cuota $124.141, última $102.012, intereses $156.919.

### 4.3 Cupos, préstamos y deudas organizadas: cuota fija (método francés)
```
cuota = saldo × i / (1 − (1 + i)^−n)      i = tasa M.V.   (con tasa 0: valor / n)
```
La última cuota se ajusta para cerrar el saldo exacto.

**Fechas de las cuotas:** cada crédito guarda su **día de pago pactado** (día de la compra en cupos; día límite de pago en tarjetas y préstamos). Si ese día no existe en el mes, la cuota va al último día, pero el mes siguiente vuelve al día pactado: compra el 31-ene → 28-feb, 31-mar, 30-abr. El cargo fijo por cuota (aval, fianza, plataforma) se suma a cada cuota y cuenta como "Costo de la deuda".
- **Cupos:** la primera cuota vence un mes después de la compra (o la fecha que indiques). Como cada compra vence en un día distinto, el **próximo pago** de un cupo reúne todas las cuotas que vencen en ese mes.
- Ejemplo Addi: $300.000 a 3 cuotas sin intereses con $5.000 de cargo → 3 cuotas de $105.000.

### 4.3.1 Cuotas que ya tenía
```
cuotas que faltan = total de cuotas − cuotas ya pagadas
saldo pendiente   = capital de las cuotas que faltan en el cronograma original   (o el que muestre la app)
```
Ejemplo: $1.200.000 a 12 cuotas en tarjeta, "cuota 5 de 12" → 4 pagadas, saldo $800.000, cuotas numeradas de la 5 a la 12.

### 4.4 Pagos a la tarjeta
1. Se cubren primero las cuotas **vencidas** y las del **ciclo actual** (próxima fecha límite), intereses antes que capital.
2. La cuota de manejo (o las comisiones del extracto) se cubre con lo que sobra del ciclo, **una sola vez por ciclo** aunque hagas varios pagos.
3. Lo que sobra es un **abono extraordinario a capital**: va a la deuda de mayor tasa de esa tarjeta y recalcula su cronograma reduciendo **plazo** (misma cuota, menos meses) o **cuota** (mismos meses).
4. El pago se clasifica como: **mínimo**, **más del mínimo**, **total** o **⚠ menor al mínimo** (alerta de mora). Si hay un extracto vigente, se compara con su mínimo y su total.
5. Si se marca "desde la reserva", se descuenta de la Cajita (no se permite si la reserva no alcanza).
5b. Lo que no se puede aplicar (ya no hay deuda) queda como **saldo a favor** del producto y se usa solo en la próxima deuda que registres ahí.
6. Solo se puede eliminar el **último** pago de cada tarjeta (deshace cuotas, abono y reserva).

### 4.5 Organizar deuda (refinanciación)
Datos que pide (los muestra la app del banco): **deuda total antes**, **valor pagado para refinanciar** (intereses y comisiones), **número de cuotas**, **valor de la cuota** y/o **tasa E.A.**, fecha de la primera cuota.

| Resultado | Cómo se calcula |
|---|---|
| Saldo refinanciado | deuda total − valor pagado (o el que indiques) |
| Tasa según la cuota | Se despeja la tasa que hace que *n* cuotas de ese valor paguen el saldo (bisección). Si difiere de la E.A. declarada en más de 0,05 pp M.V., avisa (posibles seguros/cargos). |
| Cronograma | Cuota fija con la tasa de la cuota (cuadra con lo que cobra el banco); si solo hay tasa, se calcula la cuota. |
| Total a pagar | valor pagado + suma de cuotas |
| Costo de organizar la deuda | valor pagado + intereses de las cuotas |
| Comparación | Próximo pago, meses e intereses que faltan "como estoy" (deudas registradas de esa tarjeta) vs. "organizada", con veredicto. |

Al registrarla: el valor pagado queda como pago (todo a "Costo de la deuda"), las deudas anteriores de la tarjeta quedan como **refinanciadas** (no se borran) y se crea la deuda organizada. Se puede deshacer si aún no tiene pagos.

### 4.6 Extracto
```
pago mínimo = capital del mes + intereses + comisiones + cargos por conversión − abonos − devoluciones
pago total  = pago mínimo + deuda restante
```
Validado con extractos reales de Nu. Mientras no pase la fecha límite, **el mínimo del extracto reemplaza al del cronograma** (menos lo ya pagado desde el corte), porque es el dato real del banco. Un extracto anterior a una refinanciación se ignora.

**Conciliación de intereses:** al registrar el extracto, el interés de las cuotas del ciclo (después del corte y hasta la fecha límite) se ajusta al interés del extracto, que el banco calcula por días. Así, pagar el mínimo del extracto deja la cuota al día y no genera mora falsa. El ajuste queda guardado (`ajustes_cuota`) y se deshace al eliminar el extracto.

### 4.7 Intereses si pagas solo el mínimo
`(total − mínimo) × M.V.`: intereses aproximados que se generan el mes siguiente sobre lo que quedas debiendo.

### 4.8 Plan del ingreso
Para cada ingreso (real o simulado). Cada ingreso cubre **desde el día en que llega hasta el día anterior al próximo ingreso**; lo que vence el mismo día del próximo ingreso se paga con ese ingreso. Un sueldo que llega hasta 5 días antes de su fecha (fin de semana, festivo) se toma como el de esa fecha: el del 30 que llega el 28 cubre hasta el 14 del mes siguiente. Las primas y bonos (extraordinarios) no se corren.

Ejemplo (pagos el 15 y el 30, servicios el 5, 7, 10 y 15): el sueldo del 30 paga lo del 5, 7 y 10; lo del 15 lo paga el sueldo del 15. El plan muestra la lista «Lo que paga este ingreso» con cada pago, su fecha y si sale de la reserva o del ingreso.

| Paso | Regla |
|---|---|
| A. Deuda inmediata | Pagos de tarjetas/créditos que vencen **antes del próximo ingreso** (incluye vencidos). |
| B. Servicios | Los que vencen desde la fecha del ingreso hasta antes del próximo ingreso y no se han pagado (de un pago parcial, solo lo que falta). A y B se toman primero de la reserva (primero las deudas, luego los servicios); lo que falte, de este ingreso. |
| C. Día a día | Promedio mensual de compras en efectivo (sin servicios) de los últimos 3 meses con datos ÷ ingresos por mes. Sin historial, usa el estimado de Configuración. |
| D. Reserva (mes adelantado) | Meta = pagos de deuda **y servicios** desde el próximo ingreso hasta el **fin del mes siguiente**. Aporte = (meta − reserva) ÷ ingresos que quedan en el mes. Si no alcanza, se aparta todo lo posible ("construyendo reserva"). |
| E. Excedente | Si queda algo después de lo obligatorio, se reparte entre ahorro, abono extra a deuda y libre según el nivel de endeudamiento. |
| Déficit | Si A + B + C superan el ingreso, se muestra cuánto falta. |

**Nivel de endeudamiento** = pagos de deuda del mes siguiente ÷ ingreso mensual estimado (fuentes activas; las esperadas solo si se marca la casilla).

| Nivel | % | Ahorro | Abono extra | Libre |
|---|---|---|---|---|
| 🟢 Sano | < 20 % | 30 % | 20 % | 50 % |
| 🟡 Moderado | 20–35 % | 25 % | 35 % | 40 % |
| 🟠 Alto | 35–50 % | 15 % | 60 % | 25 % |
| 🔴 Crítico | ≥ 50 % | 10 % | 90 % | 0 % |

Umbrales y porcentajes son configurables. El **abono extra** se asigna por **avalancha** (mayor tasa primero) o **bola de nieve** (menor saldo primero).

### 4.9 Ahorros (cajas)
Cada objetivo es una **caja** con meta, fecha objetivo opcional y prioridad (alta, media, baja).

**¿Cuánto puedo ahorrar en el mes?** (por defecto el mes siguiente; se puede cambiar arriba)

| Paso | Regla |
|---|---|
| Lo que te queda | Ingreso mensual estimado − cuotas y mínimos de tarjetas de ese mes − servicios − día a día − **gastos previstos** de ese mes |
| Ahorro sugerido | Lo que te queda × % de ahorro del nivel de endeudamiento (tabla de 4.8). **Sin deuda**, se suma también el % de abono extra. Se redondea hacia abajo a miles. |
| Cuándo | El sugerido se divide entre tus días de pago del mes (ej. 15 y 30). |
| Saldo a favor | Lo que sobró el mes anterior, menos lo que falte en la reserva del mes adelantado, se puede mover a las cajas (botón). |

**Reparto entre cajas** (sugerido mensual y botón "Repartir un abono"): primero las cajas con fecha reciben lo que necesitan al mes para llegar a tiempo (falta ÷ meses hasta la fecha); el resto se reparte por prioridad (pesos 3, 2, 1) sin pasar de lo que le falta a cada una. La columna "¿Cuándo?" es el mes en que se completa abonando el sugerido (⚠ si no llega a la fecha).

**Disponible** = ingresos − compras en efectivo y cuotas iniciales − pagos a deudas − lo apartado en la reserva (los pagos hechos desde la reserva no salen del bolsillo; el rendimiento no cuenta) − abonos a cajas + **ajustes**. Si no cuadra con tu cuenta, "Ajustar mi disponible" guarda la diferencia.

- **Abono "ya lo tenía ahorrado":** plata ahorrada antes de usar la app; no se descuenta del disponible.
- **Retirar / usar:** la plata vuelve al disponible. Si marcas "lo usé para comprar", se registra la compra en efectivo (aparece en "¿En qué gasté?") y el disponible no cambia. Eliminar ese retiro elimina también la compra.
- **Pausada:** no recibe ahorro sugerido. **Archivada:** cumplida, se oculta.
- En el **Plan del ingreso**, "Abonar … a mis cajas" reparte la partida de ahorro entre las cajas.

---

## 4B. Módulo de financiación (Addi, Sistecrédito, almacenes, entidades)

### Condiciones de cada operación
Ninguna tasa ni cargo está fijo en el código. Cada tarjeta o cupo tiene una **plantilla de condiciones** (Tarjetas y deudas → **⚙ Condiciones**), y cada compra guarda una **fotografía** de la oferta aceptada (formulario de compra → "condiciones propias"). Cambiar la plantilla después **no altera** los créditos existentes.

| Grupo | Datos |
|---|---|
| Acreedor | Tipo (entidad financiera, plataforma de crédito, almacén directo, almacén con tercero), nombre, NIT, entidad que financia |
| Tasa | Valor y modalidad original (E.A., M.V., N.A.M.V.), modalidad legal (consumo, bajo monto, microcrédito) |
| Cuotas | Sistema (cuota fija / capital fijo), periodicidad (mensual, quincenal, semanal), número de cuotas |
| Compra | Precio de contado, precio financiado (valor de la compra), cuota inicial |
| Cargos | Fianza/aval (% del capital + IVA; al inicio, repartido o en cada cuota), seguro fijo o % del saldo, administración, estudio de crédito, otros por cuota o iniciales |
| Prepago | Si los cargos se siguen debiendo al pagar antes; penalidad (normalmente 0) |
| Mora | Tasa pactada (vacío = usura del periodo; nunca la supera), gastos de cobranza (desde el día N, fijo o % de lo vencido, + IVA, una vez o cada 30 días) |
| Pagos | Orden contractual de aplicación (ej. cobranza → mora → cargos → intereses → capital) |
| Vigencia | Fecha desde la que rigen esas condiciones |

### Fórmulas
```
Tasas:      i_m = (1 + i_EA)^(1/12) − 1      i_EA = (1 + i_m)^12 − 1      i_m = NAMV / 12
Periodo:    i_p = (1 + i_EA)^(1/p) − 1        p = 12 mensual, 24 quincenal, 52 semanal
Cuota fija: C = P · i_p / (1 − (1 + i_p)^−n)   (con i_p = 0: P / n; la última cuota cierra el saldo)
Capital fijo: capital = P / n; interés = saldo × i_p
Cargo % capital (con IVA) = P × % × (1 + IVA);  repartido = total / n;  % saldo = saldo inicial del periodo × %
Mora:       capital vencido × ((1 + tasa_mora_EA)^(días/365) − 1), por tramos mensuales (la usura cambia cada mes)
Tasa efectiva real (XIRR): tasa r tal que Σ flujo_t / (1 + r)^(días_t/365) = 0
            flujos: +(precio de contado − cuota inicial − cargos iniciales) el día de compra; −cuota en cada fecha
Costo:      total pagado = cuota inicial + cargos iniciales + Σ cuotas
            diferencia vs. contado = total pagado − precio de contado
            costo financiero = intereses + cargos;  costo comercial = precio financiado − precio de contado
```
Dinero en **Decimal**, guardado en centavos enteros y redondeado a pesos con **redondeo comercial** (0,5 hacia arriba). Las tasas solo se usan como factores.

### Pagos
| Caso | Cómo se registra |
|---|---|
| Cuota completa / mínimo | Registrar pago |
| Pago parcial | Registrar pago por menos: se aplica en el orden contractual y queda marcado "menor al mínimo" |
| Abono a capital | Lo que sobra del ciclo reduce plazo o cuota de la deuda más cara (con penalidad si la oferta la tiene) |
| Anticipar cuotas | Opción "Anticipa las cuotas siguientes completas" |
| Cancelar todo | Pagar el **Total**: incluye los cargos que la oferta mantiene al pagar antes. Si en las condiciones marcas "solo se cobra el interés de los días corridos", la cuota del ciclo lleva el interés causado: capital × ((1 + i)^(días / días del periodo) − 1) |
| Pago atrasado | Se liquida la mora hasta la fecha del pago antes de aplicarlo |
| Pago con fecha anterior | Si la mora se había liquidado con "Liquidar mora a hoy" después de esa fecha (y no se ha pagado), se deshace y se recalcula hasta la fecha real del pago. Si la liquidó un pago posterior, la app pide registrar los pagos en orden |
| Canal | PSE, app, corresponsal, efectivo… (queda en el historial) |
| Duplicado | Aviso si ya hay un pago igual el mismo día; se corrige eliminando el último pago (deshace todo su efecto, incluida la mora liquidada) |
| Devolución de compra | Deudas activas → **↩ Devolución**: reduce el capital de esa deuda; no cuenta como plata que sale ni como costo |
| Acuerdo de pago | Organizar deuda → marcar "Es un acuerdo de pago" |
| Organizar una sola compra | Organizar deuda → "Deudas que se organizan": todas o una deuda específica |
| Saldo a favor | Se muestra en la tabla de tarjetas y en las alertas; se aplica solo a la siguiente deuda del producto |

### Mora y cobranza
- Pestaña **Mora y cobranza**: cuotas vencidas, días de mora, capital vencido, mora y cobranza liquidadas y lo que se causaría a hoy.
- La mora se **liquida** (se guarda) al registrar un pago o con "Liquidar mora a hoy". Cada tramo y cada periodo de cobranza tiene una clave única: **no se cobra dos veces**.
- La cobranza "una vez" se cobra una vez por **episodio de atraso continuo**: si pagas la cuota vencida más antigua pero otra sigue vencida, sigue siendo el mismo atraso y no se vuelve a cobrar.
- **Cargos al abonar a capital:** si los cargos "se eliminan" al prepagar, el seguro sobre saldo se recalcula con el saldo nuevo y la fianza/aval repartida baja en proporción al capital que queda (igual si reduces cuota o plazo). Si "se mantienen", el total pendiente se reparte en las cuotas nuevas.
- **Tasas legales** (Configuración → Tasas legales): IBC y usura por modalidad y periodo, ingresados desde la certificación de la Superintendencia Financiera. Sin una tasa registrada para la fecha (ni usura de respaldo), la app **no calcula mora** en lugar de inventar una tasa.

### Marco legal (referencia, no asesoría)
La app ayuda a revisar las condiciones frente a la Ley 45 de 1990 (límites de intereses), la Ley 1480 de 2011 (información al consumidor), la Ley 2439 de 2024 cuando aplique, el IBC y la usura certificados, y el derecho al prepago. **No hace afirmaciones legales automáticas**: si un cargo cuenta como interés lo marca el usuario según su contrato ("cuenta como interés"), y las alertas solo comparan cifras registradas.

**Alerta de usura por deuda (Inicio):** compara con la usura registrada para la fecha de cada deuda (1) la tasa pactada, (2) la tasa equivalente al valor de la cuota y (3) la tasa de intereses + cargos marcados "cuenta como interés" (por flujos). El cronograma de cada deuda muestra esas tasas.

### Comparar financiación
Tarjetas y deudas → **⚖ Comparar financiación**: un mismo precio con hasta 4 alternativas (contado, Addi, Sistecrédito, almacén…), cada una con sus condiciones reales. Muestra cuota inicial, cuotas, valor de cuota, intereses, cargos, total pagado, diferencia e incremento frente al contado, costo comercial, tasa contractual y **costo efectivo** (tasa real por flujos).

---

## 5. Estructura

```
finanzas/
├── main.py                 # Punto de entrada
├── construir.bat           # Tests + genera dist\Finanzas\Finanzas.exe
├── requirements.txt
├── assets/finanzas.ico
├── finanzas/
│   ├── dinero.py           # Centavos ↔ "$1.750.905", tasas
│   ├── fechas.py           # Meses, días de pago, ciclo de facturación
│   ├── credito.py          # Tasas, cronogramas, cargos, mora, costo/XIRR, ofertas, pagos (puro, Decimal)
│   ├── condiciones.py      # Plantilla y fotografía de condiciones (JSON) de cada crédito
│   ├── plan.py             # Reparto del ingreso (puro)
│   ├── ahorro.py           # Capacidad de ahorro y reparto entre cajas (puro)
│   ├── db.py               # Esquema SQLite, ubicación de datos, respaldos
│   ├── repositorio.py      # Reglas de negocio sobre la base
│   ├── exportar.py         # Excel de solo lectura
│   ├── campos.py           # Definición de formularios, común a las dos interfaces
│   ├── ui_flet/            # Interfaz principal: Flet (Flutter), adaptable al tamaño de la ventana
│   │   ├── app.py          # Ventana, navegación lateral (se compacta en ventanas angostas)
│   │   ├── componentes.py  # Tarjetas, tablas, formularios, diálogos, pestañas
│   │   ├── graficas.py     # Gráficas interactivas (flet-charts)
│   │   └── paginas/        # Una página por archivo (se cargan al abrirlas)
│   └── ui/                 # Interfaz clásica: CustomTkinter + matplotlib (`python main.py --clasica`)
└── tests/                  # pytest: cálculos y repositorio
```

### Tablas
`configuracion`, `categorias`, `fuentes_ingreso`, `ingresos`, `productos_credito`, `servicios`, `compras`, `creditos`, `cuotas`, `pagos_credito`, `pagos_aplicacion`, `extractos`, `refinanciaciones`, `reserva_movimientos`, `cierres_mensuales`, `metas_ahorro`, `ahorro_movimientos`, `gastos_previstos`, `ajustes_disponible`, `tasas_legales`, `cargos_mora`, `ajustes_cuota`, `historial_cambios`. Detalle en [finanzas/db.py](finanzas/db.py).

**Saldo histórico:** `Repositorio.deuda_a_fecha(fecha)` reconstruye el capital que se debía en cualquier fecha con el historial de pagos, abonos, devoluciones y refinanciaciones. Los cierres mensuales se completan con él, incluidos los meses en que no se abrió la app (hasta 36 meses).

**Historial de cambios:** las ediciones de tarjetas/cupos (ej. cambio de cupo o tasa), plantillas de condiciones y tasas legales, y lo que se elimina (pagos, compras, deudas, extractos, refinanciaciones, ingresos, movimientos de reserva), quedan en `historial_cambios` y en la hoja "Historial de cambios" del Excel.

**Migración del módulo de financiación** (automática al abrir, solo agrega; el respaldo del día se toma antes):

| Tabla | Columnas nuevas |
|---|---|
| `productos_credito` | `condiciones` (plantilla JSON) |
| `creditos` | `condiciones` (fotografía JSON), `precio_contado`, `cuota_inicial`, `cargos_iniciales`, `periodicidad` |
| `cuotas` | `mora`, `cobranza`, `mora_hasta`, `detalle` (cargos por nombre, JSON), `pagado_capital`, `pagado_interes`, `pagado_otros`, `pagado_mora`, `pagado_cobranza` |
| `pagos_aplicacion` | `a_interes`, `a_otros`, `a_mora`, `a_cobranza` |
| `pagos_credito` | `canal`, `credito_id` (cargos iniciales y devoluciones) |
| `refinanciaciones` | `tipo` (refinanciación / acuerdo de pago) |
| `compras` | `cuota_inicial`, `pago_parcial` (pago de servicio que deja saldo pendiente) |
| `reserva_movimientos` | `compra_id` (servicio pagado con la reserva; se borra con la compra) |
| `creditos` (auditoría) | `dia_pago` (día de pago pactado) |
| `pagos_credito` (auditoría) | `a_manejo`, `ciclo` (manejo una vez por ciclo), `saldo_favor` |
| *nuevas (auditoría)* | `ajustes_cuota` (intereses conciliados con el extracto o causados al prepagar; reversibles), `historial_cambios` |
| *nuevas* | `tasas_legales` (IBC y usura por periodo), `cargos_mora` (mora y cobranza liquidadas, únicas por tramo) |

Lo ya pagado en cuotas anteriores se repartió por componente como lo hacía la versión anterior (primero intereses y cargos, luego capital). Los créditos sin fotografía usan su tasa y sistema guardados.

---

## 6. Desarrollo

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python main.py          # Ejecutar desde el código (interfaz Flet)
python main.py --clasica  # Interfaz anterior (CustomTkinter)
python -m pytest        # Tests
.\construir.bat         # Tests + ejecutable en dist\Finanzas
```

Para probar sin tocar los datos reales: `$env:FINANZAS_DATOS = "C:\ruta\de\prueba"` antes de ejecutar.

---

## 7. Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-10-31 | SQLite; Excel solo exportación | Relaciones crédito→cuotas, transacciones, gratis, liviano. |
| 2026-10-31 | Registros con fecha + cierre mensual | Consultas simples e histórico estable. |
| 2026-10-31 | Compra con tarjeta = deuda; gasto = efectivo/débito; formulario único de compra | Decisión del usuario; información fácil de leer. |
| 2026-10-31 | Intereses, manejo y valor de refinanciación = "Costo de la deuda" | Mostrar lo que cuesta el crédito. |
| 2026-10-31 | Tarjetas: abono constante; préstamos/refinanciación: cuota fija | Métodos usados en Colombia. |
| 2026-10-31 | Montos en centavos; cronogramas redondeados a pesos | Extractos con centavos; cuotas legibles. |
| 2026-10-31 | El extracto vigente manda sobre el cronograma | Es el dato real del banco. |
| 2026-10-31 | Ingresos por fuente con días de pago (quincenal/mensual) | La frecuencia puede cambiar al cambiar de trabajo. |
| 2026-10-31 | Ingresos esperados no entran al plan (solo en simulación) | No están asegurados. |
| 2026-10-31 | Reserva en Cajita con rendimiento configurable | Decisión del usuario. |
| 2026-10-31 | Organizar deuda con valor pagado, cuotas, valor de cuota y E.A. | Pedido del usuario. |
| 2026-10-31 | CustomTkinter + matplotlib, PyInstaller `--onedir` | Liviano, arranca rápido, no extrae temporales. |
| 2026-11-03 | Interfaz nueva con Flet 1.0 (la clásica se conserva con `--clasica`) | CustomTkinter se congelaba al cambiar el tamaño de la ventana; Flet (Flutter) redibuja sin bloquearse, se adapta al ancho y es más moderna. Los cálculos y la base no cambian. |
| 2026-11-03 | Pago de servicios con valor real, pago parcial y método (efectivo o a crédito) | Pedido del usuario: la factura puede ser menor o mayor que el estimado. |
| 2026-11-03 | La reserva del mes adelantado incluye los servicios y los paga (casilla «Lo pagué con la reserva» al pagar un servicio) | Pedido del usuario: el ingreso cubre hasta el siguiente ingreso y además ahorra los pagos del mes siguiente (deudas + servicios; el ahorro, si alcanza). |
| 2026-11-03 | Un sueldo que llega hasta 5 días antes cuenta como el de su fecha; lo que vence el día del próximo ingreso se paga con ese ingreso | Si llegaba antes, el plan solo cubría hasta la fecha programada y dejaba sin apartar el arriendo y los servicios. |
| 2026-10-31 | Tipo "cupo de crédito" (Addi, Sistecrédito, almacenes): cuota fija, vencimiento por compra, cupo editable | Productos que usa el usuario además de la tarjeta. |
| 2026-10-31 | Tasa, primera fecha y cargo fijo por compra | Promociones sin intereses (Addi 3 cuotas) y cargos de aval/plataforma. |
| 2026-10-31 | Cuotas existentes con "valor, total de cuotas, cuotas pagadas" | Son los datos que muestra la app del banco. |
| 2026-10-31 | Condiciones por operación en JSON (plantilla + fotografía) | Configurable sin tocar código; tarifas futuras no cambian créditos viejos. |
| 2026-10-31 | Pagado por componente y orden de aplicación configurable | Respetar el contrato (ej. fianza pendiente tras anticipar capital). |
| 2026-10-31 | Decimal y redondeo comercial | `round()` de Python redondea al par. |
| 2026-10-31 | Mora por tramos mensuales limitada por usura histórica; sin tasa registrada no hay mora | No usar una usura permanente ni inventar tasas. |
| 2026-10-31 | Sin afirmaciones legales automáticas | La naturaleza de un cobro depende del contrato. |
| 2026-10-31 | Auditoría: día de pago pactado por crédito | Una primera cuota el 28-feb arrastraba todas al 28 y generaba mora falsa. |
| 2026-10-31 | Auditoría: el extracto concilia el interés del ciclo | Pagar el mínimo del extracto dejaba saldo "vencido". |
| 2026-10-31 | Auditoría: cobranza única por episodio de atraso | Se volvía a cobrar al pagar la cuota vencida más antigua. |
| 2026-10-31 | Auditoría: interés causado al prepagar como opción de las condiciones | Depende del contrato; por defecto se conserva el periodo completo. |
| 2026-10-31 | Auditoría: saldo a favor, validación de cupo y de reserva | Evitar pagos "perdidos", compras imposibles y reserva negativa. |
| 2026-10-31 | Auditoría: historial de cambios y saldo a una fecha | Trazabilidad y cierres de meses sin abrir la app. |
| 2026-10-31 | Cajas de ahorro por objetivo, separadas de la reserva | La reserva es para deudas; las cajas, para metas personales. |
| 2026-10-31 | Ahorro sugerido = % de ahorro del nivel de deuda sobre lo que queda del mes siguiente | Mismo criterio que el Plan del ingreso; con deuda alta se ahorra menos. |
| 2026-10-31 | Saldo a favor calculado (no se guarda) + ajustes del disponible | Si se corrige un movimiento viejo, el saldo de los meses siguientes se corrige solo. |

---

## 8. Limitaciones conocidas

1. **Intereses del primer mes:** el banco calcula por días entre compra y corte; la app por mes completo. Al registrar el extracto, el interés del ciclo se concilia con el del banco. El **capital** del mes no se concilia: si el extracto trae un capital distinto (ej. el banco cobró la compra en otro ciclo), la diferencia se ve como saldo pendiente o como abono.
2. **Avances en efectivo:** los avances en efectivo (interés desde el día 1 + comisión) se registran como compra a cuotas; la comisión va en el extracto.
3. **Cupo variable:** se actualiza a mano editando el producto (el cambio queda en el historial); el "uso del cupo" y el disponible se calculan con el último valor guardado y con el capital pendiente.
4. **Cuota de manejo:** no es una cuota del cronograma; se suma al mínimo de cada ciclo y se descuenta una vez por ciclo de lo que sobra de los pagos.
5. **Plan vs. real:** el plan no se guarda; se recalcula con el estado actual.
6. **Cobranza por crédito:** se cobra por episodio de atraso de cada crédito; si un contrato la liquida distinto (por saldo total, por días exactos), puede diferir.
7. **Pagos fuera de orden:** si un pago posterior ya liquidó mora, para registrar uno con fecha anterior hay que eliminar los posteriores y registrarlos en orden.
8. **Fechas quincenales y semanales:** cada 15 o 7 días desde la primera cuota (no "15 y último de mes").
9. **Comparador:** usa un cargo de fianza/aval, seguro y otros por oferta; ofertas con más tipos de cargos se registran como compra para ver su costo completo.
10. **Tasa variable:** no hay cambio de tasa sobre un crédito vigente; en tarjetas, el extracto concilia el interés de cada mes.
11. **Deudas registradas antes de esta versión:** conservan las fechas de cuota que ya tenían; el día pactado se aplica a las deudas nuevas y a los recálculos.

---

## 9. Pendientes y reportes de prueba

Anotar aquí lo que se vea raro al usar el ejecutable (qué pantalla, qué se hizo, qué se esperaba).

| # | Reporte | Estado |
|---|---|---|
| | | |

### Ideas futuras
- Guardar el plan de cada ingreso y graficar plan vs. real.
- Importar extractos (PDF/CSV).
- Presupuesto por categoría con alertas.
- Cálculo del 4×1000 (GMF).
