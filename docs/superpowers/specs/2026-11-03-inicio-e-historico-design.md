# Inicio "Tablero del día" e histórico de análisis

_Spec 2026-11-03. Primer cliente: Laboratorios La Fe. Sale de una sesión de brainstorming con Emmanuel (opción A elegida entre tres maquetas; las maquetas viven en `.superpowers/brainstorm/`, ignorado por git, y el generador en el scratchpad de la sesión). Dominios: ONE Treasury (dinero), ONE Payables (pagos), Analytics (histórico)._

## Intención

La plataforma "se siente fea": desperdicia espacio, los números son planos y no hay objetos visuales. La referencia de gusto es **Linear / Stripe**: denso pero ordenado, tipografía fina, cifras claras, gráficas limpias dentro del flujo, movimiento sólo cuando responde a algo. La primera pantalla que se rehace es **Inicio**, la que Liza (dirección) y Abraham (administración) abren cada mañana para responder tres preguntas: **cuánto dinero hay, qué hay que pagar y cómo van las sucursales.**

La Fe llega a ONE Finance el 1-nov-2026 (fecha de corte), pero tiene años de historia en Excel. Para que Inicio diga algo desde el primer día ("septiembre +55 % contra 2025") se carga un **histórico de análisis**: datos del pasado que alimentan gráficas y comparaciones **sin tocar la contabilidad**.

## Objetivos

1. Capa de **histórico de análisis** por empresa, cargada por el equipo de Atlas desde los Excel de La Fe, que se puede recargar sin duplicar.
2. **Inicio rediseñado** como "Tablero del día" (opción A), con datos vivos de ONE Finance unidos al histórico en una sola línea de tiempo.
3. Un **lenguaje visual** (tipografía, tokens, gráficas, cifras) que después se aplica al resto de la plataforma.

## No objetivos

- Rediseñar Gastos, Movimientos, Reportes, Caja u otras pantallas. Vienen después con el mismo lenguaje.
- Cargar las 1,809 pólizas de la reconstrucción al libro contable. Decisión de Emmanuel: el histórico es de análisis, separado.
- Pantalla para que La Fe suba el histórico por sí misma.
- Proyección de flujo a 30 días como gráfica protagonista. Era la opción C; queda descartada para esta entrega.

## Anti-objetivos (sería un fracaso aunque funcione)

- Que el histórico se confunda con lo registrado o mueva un saldo, una póliza o un reporte contable.
- Que aparezca un nombre de paciente o un estudio en cualquier tabla o gráfica.
- Ceros mudos: una sección sin datos muestra qué falta y un botón para resolverlo, nunca "$0.00" y ejes de "$0 a $4".
- Animaciones decorativas en cada tarjeta (fade-in por sección, hovers en todo).

## Parte 1: histórico de análisis

### Qué entra (fuentes reales, revisadas el 2026-11-03)

| Serie | Fuente | Granularidad | Rango |
|---|---|---|---|
| Ventas por sucursal y forma de pago: tickets, venta neta, descuento, adeudo, cancelados, editados | Toronja `.xls` (HTML, 12,071 tickets) | día × sucursal × forma de pago | 2-ene → 30-sep-2026 |
| Ventas totales por mes | CONTROL GENERAL, hoja PROY | mes | 2022 → 2026 |
| Meta de ventas (normal y conservadora) | PROY | mes | 2027 |
| Estado de resultados: ingresos, costo, utilidad bruta, gastos de operación, utilidad de operación, financieros, utilidad antes y después de sueldo de socias | Reconstrucción, hoja 04 | mes | ene → sep-2026 |
| Gasto por cuenta contable, contribuyente y sucursal | Reconstrucción, hoja 03 (libro diario, agregado) | mes × cuenta × entidad × unidad | ene → sep-2026 |
| Saldos de caja y bancos a fin de mes | CONTROL GENERAL, hoja RESUTADOS | mes × cuenta | ene → sep-2026 |
| Caja central día a día | Control de Efectivo | día | jul → oct-2026 |
| Préstamos (concentrado) e inversión por sucursal | CONTROL GENERAL, hojas PRESTAMOS e INVERSIONES | foto | 2026 |
| Avance de la revisión: pólizas confirmadas / por confirmar, dudas y hallazgos por estatus | Reconstrucción, hojas 03, 17 y 18 | foto | 21-oct-2026 |

Falta **octubre** de Toronja y de la reconstrucción: se pidió a La Fe. El cargador acepta un archivo nuevo y reemplaza ese periodo.

### Modelo

Tabla `historical_points` (nombre libre al implementador):
- `organization_id`
- `dataset`: `sales_daily | sales_monthly | sales_target | pnl_monthly | expense_monthly | balance_monthly | cash_daily | snapshot`
- `metric`: por ejemplo `net_sales`, `tickets`, `discount`, `cancelled`, `edited`, `revenue`, `operating_profit`, `profit_after_partners`, `balance`
- `period_start`, `period_grain`: `day | month | snapshot`
- dimensiones opcionales: `business_unit_id` (FK cuando se resuelve; si no, `unit_label`), `fiscal_entity_id`, `payment_method`, `account_code`, `account_label`
- `value`: `Numeric(16,2)`
- `source` (archivo y hoja), `load_id`
- AuditMixin

Tabla `historical_loads`: `id`, `organization_id`, `source`, `period_from`, `period_to`, `rows`, `loaded_by`, `loaded_at`, `notes`.

**Recarga sin duplicar:** cargar una fuente reemplaza, en una sola transacción, los puntos de esa `(organization_id, dataset, source-family)` en el rango que trae el archivo.

**Privacidad:** el cargador de Toronja reutiliza `app/services/imports/toronja.py` y **agrega antes de persistir**. `CLIENTE` y `ESTUDIOS` nunca salen del proceso.

Migración `20261103_04_historico.py` (`down_revision="20261103_03"`).

### Cómo se carga

Script `scripts/lafe_historico.py --org "Laboratorios La Fe" --toronja <xls> --control-general <xlsx> --reconstruccion <xlsx> --efectivo <xlsx> [--dry-run]`. Corre con la sesión de la app, como `lafe_apertura.py`.

Los archivos originales no entran al repo; viven en el equipo de Emmanuel. En producción el clasificador bloqueó `railway ssh` al contenedor. Por eso se agrega además un endpoint `POST /api/admin/historical-loads` (multipart, sólo OWNER de la empresa; ver Decisiones abiertas) que corre el mismo cargador; el script y el endpoint comparten el servicio.

Unidades: los nombres de los Excel ("VILLAS DE NUESTRA SEÑORA", "Villas", "LAS CUMBRES"…) se resuelven con los `aliases` de `business_units` (ya existen). Lo no resuelto queda con `unit_label` y se reporta.

### Cómo se lee

`GET /api/analytics/series?dataset=&metric=&from=&to=&grain=&business_unit_id=&fiscal_entity_id=&compare=previous_year` devuelve puntos `{period, value, origin: "historical" | "live"}`. **Une histórico y vivo:**
- antes de `organizations.opening_date` sale del histórico;
- desde esa fecha sale de ONE Finance (ingresos, gastos, ventas por unidad desde las operaciones);
- nunca suma ambos para el mismo periodo.

Lo ven todos los roles de la empresa, incluido MEMBER (auxiliar) y VIEWER: Inicio es el mismo para todos (decisión de Emmanuel, 2026-11-04). El tenant isolation sí aplica.

## Parte 2: Inicio "Tablero del día" (opción A)

Maqueta aprobada: `.superpowers/brainstorm/996202-1793743918/content/inicio-opciones.html`, opción A. Las cifras de la maqueta son de ejemplo.

### Estructura (escritorio ≥ 1280 px)

```
┌ filtros: unidad · contribuyente · fecha ───────────────── ⌘K ┐
│ [franja ámbar sólo si hay algo por autorizar y el usuario autoriza] │
├──────────────┬────────────────────────┬──────────────────────┤
│ Dinero hoy   │ Por pagar esta semana  │ Sucursales           │
│ total grande │ barras lun→dom         │ ranking del mes      │
│ Δ vs día háb.│ lista: día · concepto  │ barra · cifra · Δ vs │
│ barra apilada│  · monto · saldo que   │ año pasado · sparkline│
│ 4 renglones  │  queda · "Por autorizar"│ 30 días · punto de   │
│ con estado   │                        │ corte de ayer        │
├──────────────┴────────────────────────┴──────────────────────┤
│ Ventas por mes: 2026 (histórico punteado → vivo sólido) vs 2025 │
│ y meta 2027; marca vertical "1 nov · inicia ONE Finance"         │
└──────────────────────────────────────────────────────────────┘
```

Columnas `≈ 300px | 1.1fr | 1.2fr`. Debajo de 1024 px los tres paneles se apilan en este orden: dinero, pagos, sucursales. La gráfica de ventas queda al final con scroll horizontal propio si hace falta, nunca en la página.

### Paneles

**Dinero hoy**
- Total = disponible (caja + bancos) + en tránsito (procesador), con la partición visible.
- Barra apilada y 4 renglones:
  - **Caja central:** estado `opening_status` o "Confirmado".
  - **Cajas de sucursal:** "Por recolectar".
  - **Bancos:** "Provisional" mientras la apertura lo sea.
  - **NetPay en tránsito:** "Por depositar".
- Delta contra el cierre del día hábil anterior.
- Una línea de "lo que viene": la próxima liquidación esperada del procesador (de `settlement_days`) o la próxima cobranza grande.
- **Sin datos** (bancos en $0 provisional): "Captura el saldo de tus bancos" con enlace a Configuración › Apertura.

**Por pagar esta semana**
- Fuente: CxP con vencimiento lunes→domingo de la semana elegida, más recurrentes y préstamos con pago esa semana si ya existen como compromisos.
- Barras por día; los colores distinguen pago normal, por autorizar (ámbar) y día vacío.
- Lista con el saldo corrido: dinero hoy menos los pagos acumulados.
- Lo que espera autorización lleva la etiqueta "Por autorizar".
- Clic en un pago → Por pagar con ese documento abierto.
- **Sin datos:** "No hay pagos programados esta semana" y "Registrar cuenta por pagar".

**Sucursales**
- Una fila por unidad activa, ordenada por venta del mes en curso.
- Cada fila lleva:
  - barra horizontal relativa y cifra;
  - delta contra el mismo mes del año anterior (histórico si hace falta);
  - sparkline de 30 días (venta diaria);
  - punto del corte de ayer: entregado, entregado tarde, falta o no aplica (unidades sin caja, como Empresas). Sale de `cash_cuts`.
- Clic → Ingresos filtrado por esa unidad.
- Si no hay ventas vivas, se muestran las del último mes histórico con la marca "histórico".

**Ventas por mes**
- Eje de 12 meses del año elegido.
- Series:
  - año actual: punteado en histórico, sólido en vivo;
  - año anterior: gris;
  - meta (si existe): ámbar punteado.
- Marca vertical en `opening_date`.
- Tooltip con cifra y Δ % contra el año anterior.
- El mes en curso se muestra como punto "en curso" y no como caída de la línea.
- Leyenda arriba a la derecha.

**Franja de autorización** (tomada de la opción B)
- Aparece sólo si hay propuestas de autorización pendientes y el usuario puede autorizar: "1 pago espera a Liza · Reactivos · Adrián Estrada · $48,300 · Revisar".

### Comportamiento

- Filtros de unidad y contribuyente aplican a todo Inicio (ya existen; se reubican en la barra superior compacta).
- Tooltips en todas las gráficas. Clic lleva a la pantalla filtrada.
- **Movimiento:** las cifras grandes cuentan hacia su valor una vez al cargar (≤ 600 ms) y las barras crecen una vez. Nada más se mueve sin acción del usuario. `prefers-reduced-motion` lo apaga.
- Las cargas muestran esqueletos con la forma del panel, no spinners.
- Accesible: foco visible, contraste AA, gráficas con `aria-label` y la cifra clave en texto.

### Lenguaje visual (base para el resto)

- **Tipografía:** Geist (400/500/600) para interfaz y cifras con `tabular-nums`. Reemplaza Plus Jakarta Sans y JetBrains Mono en las cifras (decisión mía, sujeta a revisión al ver la pantalla real).
- **Tokens** (modo oscuro; el claro se deriva con el mismo criterio):
  - fondo `#0c1210`, panel `#121a17`, panel elevado `#18221e`, línea `#22302a`;
  - tinta `#e4ece7` / `#a9b8b0` / `#6f8079`;
  - acento `#4cc38a` / `#2a8f63`; ámbar `#e2a54a`; negativo `#e86a5e`.

  Se expresan como los tokens semánticos que ya existen en `index.css` y `tailwind.config.js`, no como colores crudos.
- **Paneles:** radio 10 px, borde de 1 px, sin sombras, títulos en tinta secundaria de 13 px.
- **Cifra protagonista:** 40 px, peso 500, tracking −0.03em.
- **Gráficas:** se quedan en recharts (ya está en el repo) con estilo propio: líneas de 1.5–2.5 px, rejilla sólo horizontal en el color de línea, ejes de 10.5 px en tinta terciaria y sin leyendas default. Histórico punteado (`4 3`), proyección o meta con punteado fino.
- **Arreglos globales que se hacen en esta entrega** porque afectan a Inicio:
  - la barra de desplazamiento horizontal de la página a 1440 px;
  - la barra de desplazamiento blanca del menú lateral en modo oscuro.

## Pruebas (mínimo)

**Backend**
- Cargador de Toronja con HTML sintético: agrega por día × unidad × forma, excluye cancelados de la venta y cuenta cancelados y editados aparte, sin CLIENTE ni ESTUDIOS en ningún punto.
- Recargar el mismo archivo deja el mismo número de puntos.
- Cargador de PROY y del estado de resultados con xlsx sintéticos.
- `/analytics/series` une histórico antes del corte y vivo después, sin doble conteo en el mes del corte.
- Tenant isolation: otra empresa nunca ve la serie; MEMBER y VIEWER sí la reciben.
- La contabilidad no cambia tras cargar el histórico: trial balance idéntico antes y después.

**Frontend**
- Typecheck y build.
- Capturas de Inicio con La Fe (vacío salvo histórico) y con la demo (con datos) a 1440 y 390 px, revisadas antes de cerrar.

## Definiciones y reglas (resueltas tras la revisión del constructor)

Marcadas **(decisión de Claude)** las que no vienen de Emmanuel; él las revisa al leer.

1. **Qué es "ventas"** (decisión de Claude, verificada con los datos):
   - **Histórico:** el `GRAN TOTAL` de Toronja, es decir venta neta después de descuento, con adeudos y crédito incluidos, sin cancelados y con el IVA sin separar.
   - **Comprobación:** de enero a septiembre de 2026 la suma de Toronja coincide con PROY dentro de ±1.4 %. Por ejemplo, septiembre: Toronja $892,011 y PROY $888,242.
   - **Qué fuente manda:** 2022–2025 sale de PROY. En 2026 manda Toronja; PROY se usa sólo en un mes sin Toronja.
   - **Vivo** (desde el corte): ingresos de la categoría de ventas (`import_settings.toronja.income_category_id`, o la categoría "Ventas" por omisión) más las CxC de adeudos de Toronja, sin cancelados y por `amount`. Otros ingresos, como rentas de consultorios, no cuentan como venta.
2. **Delta de cada sucursal** (decisión de Claude): no hay ventas por sucursal antes de 2026.
   - Mientras no exista el mismo mes del año anterior para esa sucursal, el delta se calcula contra **su promedio de los 3 meses previos**, con la etiqueta "vs prom. 3 meses".
   - Cuando exista ese mes, se compara contra él.
   - Nunca se reparten los totales de PROY entre sucursales.
3. **"Por autorizar" en pagos de la semana** (decisión de Claude):
   - Ámbar con "Por autorizar" = ya hay una propuesta `PAYABLE_PAYMENT` pendiente para ese documento. Es lo mismo que cuenta la franja.
   - Gris con "Requiere autorización" = saldo ≥ `approval_threshold` sin propuesta todavía, para que se vea antes de intentar pagarlo.
4. **Caja central contra cajas de sucursal** (decisión de Claude):
   - **Caja de sucursal** = cuenta CASH con `business_unit_id`.
   - **Caja central** = cuenta CASH sin unidad.
   - No hace falta un flag nuevo. La "Caja" duplicada de La Fe se desactiva y deja de contar.
5. **Estado del corte de ayer** (decisión de Claude), para el corte del día D de una caja de sucursal:
   - **Entregado:** existe y su `delivered_at` es del mismo día D.
   - **Tarde:** existe y su `delivered_at` es posterior a D.
   - **Falta:** no existe corte de D y la caja tuvo movimientos ese día.
   - **No aplica:** la unidad no tiene caja.
6. **Alcance de tokens y tipografía** (decisión de Claude):
   - Geist y los nuevos valores de tokens van **globales** en `index.css` y `tailwind.config.js`, porque la petición es que toda la plataforma deje de verse fea. Cambian valores de tokens existentes, no se crean paralelos.
   - El mapeo es: tinta 1/2/3 → `ink` / `ink-soft` / `muted`; panel elevado → `surface-2`. Si falta alguno, se agrega como token semántico.
   - Antes de cerrar se capturan las pantallas principales para confirmar que nada se rompió, aunque sólo Inicio se rediseña.
7. **Filtros contra histórico sin esa dimensión** (decisión de Claude):
   - Si el filtro activo es una dimensión que el histórico no trae (contribuyente en ventas; unidad en PROY), la serie histórica no se dibuja.
   - En su lugar aparece la nota "El histórico no trae desglose por contribuyente". La serie viva sí se filtra.
   - El endpoint devuelve `historical_available: false` con el motivo.

## Lo que queda al implementador

- Nombres exactos de tablas y métricas; índices.
- Si `/analytics/series` es un endpoint o varios.
- Cómo calcular la venta diaria viva por unidad: desde ingresos, o desde las filas de importación de Toronja si son más finas.
- Estructura de componentes de las gráficas.
- Íconos.

## Decisiones de Emmanuel

1. **Quién ve Inicio:** todos los roles ven el mismo Inicio completo, con dinero, ventas e histórico (2026-11-04). No hay versión reducida por rol.

## Decisiones de Claude pendientes de visto bueno

1. **Carga en producción:** el endpoint de carga del histórico es sólo para el OWNER de la empresa. No se crea un flag de superusuario de Atlas; Atlas carga con la cuenta OWNER, como hizo con la apertura.
2. **Geist:** se adopta. Se confirma o se cambia al ver las capturas reales de Inicio.
