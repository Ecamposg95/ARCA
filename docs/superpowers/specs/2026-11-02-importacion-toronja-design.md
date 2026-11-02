# Importación: Toronja y archivos de Excel/CSV

_Spec 2026-11-02. Dominio ONE Accounting (carga) con salida a ONE Treasury. Cubre HU-10 (importación de Excel y CSV), HU-04 (ingresos de todas las fuentes) y RN-01 de LaFe (toda venta se toma de Toronja). Formatos reales en `docs/lafe/privado/HAB-02_inventario.md` (privado; lo que necesitas está resumido aquí)._

## Intención

LaFe no va a capturar 12,000 tickets al año: su punto de venta clínico (Toronja) exporta un reporte de ventas y el control de efectivo vive en Excel. Este bloque agrega una importación con vista previa, detección de duplicados y resultado por fila, con dos formatos: **Toronja** (el primero y más valioso) y **archivo genérico** de ingresos, gastos o movimientos de efectivo con mapeo de columnas.

## Objetivos

- Subir un archivo, ver qué se va a crear y qué está mal antes de confirmar; reimportar sin duplicar.
- Toronja: cada ticket se vuelve ingreso en la unidad correcta con la forma de pago correcta; lo cobrado con tarjeta cae en el procesador (en tránsito), lo de efectivo en la caja de la unidad, las transferencias en el banco, los adeudos en cuentas por cobrar. Nombres de pacientes **no se guardan**.
- Genérico: columnas mapeables a fecha, concepto, monto, categoría, cuenta, unidad, contribuyente, referencia; vista previa con errores por fila.

## No objetivos

Leer PDF o imágenes; estados de cuenta bancarios (HU-12, otra ola); sincronización automática con Toronja (HU-21); importar pólizas contables.

## El formato de Toronja (hecho verificado con el archivo real)

Archivo con extensión `.xls` que en realidad es **HTML** (`<table>` con `<tr>`/`<td>`), codificación latin-1, una fila de encabezado y una por ticket. Columnas en orden: `FOLIO` (10 dígitos `DDMMAA####`), `CLIENTE`, `ESTUDIOS`, `TOTAL`, `EFECTIVO`, `TARJETA DEBITO`, `TARJETA CREDITO`, `TRANSFERENCIA`, `CREDITO`, `SUMA ABONO`, `IVA`, `TOTAL CON IVA`, `PAGO CON IVA / DESCUENTO` (encabezado roto, es DESCUENTO), `GRAN TOTAL`, `ADEUDO`, `VENDEDOR` (es la unidad: "MORELOS", "VILLAS DE NUESTRA SEÑORA", "CENTRO MOVIL", …), `CANCELADO`, `CANCELADO POR`, `EDITADO`, `FECHA` (`AAAA-MM-DD`). Montos como `$ 1,240.00`. Hay 21 nombres de vendedor; cada unidad de negocio tiene `aliases` para resolverlos (bloque de unidades ya en `main`). Un ticket con `CANCELADO` no vacío no se importa. Puede traer tickets de un año anterior al inicio del archivo.

## Modelo

- `import_batches`: `id`, `organization_id`, `kind` (`TORONJA | INCOMES | EXPENSES | CASH`), `filename`, `status` (`PREVIEW | CONFIRMED | DISCARDED`), `mapping` JSON (genérico: columna → campo), `options` JSON, `summary` JSON (`{rows, ok, errors, duplicates, created}`), `created_by`, `confirmed_at`, AuditMixin.
- `import_rows`: `id`, `batch_id`, `organization_id`, `row_number`, `external_id` (Toronja: folio; genérico: hash de fecha+monto+concepto normalizado), `payload` JSON (lo parseado, sin nombre de paciente), `status` (`OK | ERROR | DUPLICATE | SKIPPED | CREATED`), `message`, `result_type`/`result_id` (qué creó). Índice único `(organization_id, kind, external_id)` sobre las filas `CREATED` (unicidad lógica: valida el service).
- `organizations.import_settings` JSON: `{toronja: {bank_account_id, processor_account_id, receivable_customer_id, income_category_id}}`.
- Migración `20261102_06_importacion.py` (`down_revision` = head de tu worktree). Dependencia nueva: `openpyxl` en `requirements.txt` (xlsx); CSV con la stdlib; HTML con `html.parser` de la stdlib (sin BeautifulSoup).

## Reglas de Toronja

1. **Resolución de unidad:** `VENDEDOR` normalizado (sin acentos, mayúsculas) contra `aliases` y `name` de las unidades de la empresa. Sin unidad → fila `ERROR` "Vendedor sin unidad: X. Agrégalo como alias en Configuración."; la fila se muestra y no bloquea el resto. "Soporte Técnico del Sistema" y filas con gran total 0 y sin adeudo → `SKIPPED`.
2. **Cuentas destino:** la caja de la unidad = cuenta `CASH` activa con `business_unit_id` de esa unidad (si hay varias, la primera por nombre; si no hay, `ERROR` "La unidad X no tiene caja."). Tarjeta débito y crédito → `processor_account_id` de `import_settings` (si el tipo `PROCESSOR` no existe aún en tu worktree, acepta cualquier cuenta de dinero y anótalo; se cambia a procesador al integrar). Transferencia → `bank_account_id`. Crédito (columna `CREDITO`) y `ADEUDO` → cuenta por cobrar.
3. **Agrupación:** un ingreso por **(unidad, fecha, forma de pago)** con descripción "Ventas Toronja · {unidad} · {forma} · {n} tickets" y monto = suma de esa forma de pago en los tickets del día; `category_id` = `income_category_id` (default: la categoría de ingreso "Ventas" sembrada); `business_unit_id` = la unidad; `payment_method` = efectivo / tarjeta / transferencia; `reference` = `toronja:{AAAA-MM-DD}:{unidad}:{forma}`; `status` PAID con `paid_at` = fecha. El descuento no se registra (se importa la venta neta cobrada); el IVA no se separa (`tax_rate` 0; decisión del contador pendiente).
4. **Adeudos:** por (unidad, fecha) una cuenta por cobrar "Adeudos Toronja · {unidad} · {fecha} · {n} folios" por la suma de `ADEUDO` + `CREDITO`, cliente = `receivable_customer_id` (default: cliente "Pacientes (Toronja)" creado al confirmar si no existe), vencimiento = fecha + 30.
5. **Duplicados:** un folio ya `CREATED` en otra importación → `DUPLICATE` y se excluye de las sumas. Reimportar el mismo archivo entero crea cero operaciones y lo dice.
6. **Trazabilidad:** cada ingreso y CxC creados guardan en `import_rows` sus `result_id`; el `payload` de la fila guarda folio, fecha, unidad, montos por forma de pago, descuento, adeudo, cancelado; **nunca** `CLIENTE` ni `ESTUDIOS`.
7. **Periodo cerrado:** filas cuya fecha cae en un mes cerrado → `ERROR` "Mes cerrado" y no bloquean las demás.

## Reglas del genérico

- CSV (`,` o `;`, UTF-8 o latin-1) y XLSX (primera hoja o la elegida). El servidor devuelve las primeras 50 filas crudas y las columnas; el usuario mapea en la UI (`mapping` = `{fecha, concepto, monto, categoria?, cuenta?, unidad?, contribuyente?, referencia?, forma_pago?}`); `monto` acepta "$ 1,240.00", "1240", "-350"; en `CASH` una columna de ingreso y una de egreso o una sola con signo.
- Categoría y cuenta se resuelven por nombre (normalizado) contra los catálogos de la empresa; si no existen → `ERROR` por fila con el nombre, o la UI permite elegir una categoría/cuenta por defecto para todo el lote.
- Duplicado = mismo `external_id` (hash de fecha + monto + concepto normalizado) ya `CREATED`, o ya existente en el lote.
- Crea ingresos o gastos pagados (PAID, `paid_at` = fecha) o, en `CASH`, movimientos como ingreso/gasto en la caja elegida.

## API

- `POST /api/imports` multipart `{file, kind, sheet?}` → crea el lote en `PREVIEW` con filas parseadas y clasificadas (Toronja) o con filas crudas y columnas detectadas (genérico). Respuesta: lote + `summary` + primeras 200 filas.
- `POST /api/imports/{id}/map` `{mapping, defaults}` (genérico) → reclasifica y devuelve la vista previa.
- `GET /api/imports/{id}` (lote + filas paginadas con filtro `status`), `GET /api/imports` paginado.
- `POST /api/imports/{id}/confirm` → crea las operaciones de las filas `OK` en una transacción por lote (si una falla por algo inesperado, nada se crea y el error vuelve en español); marca `CONFIRMED`; devuelve resumen. `POST /{id}/discard`.
- `GET/PATCH /api/organizations/current/import-settings`.
- Tamaño máximo 20 MB (el de Toronja real pesa 15 MB); límite 50,000 filas.

## Interfaz

- Página **"Importar"** (nav, sección Dinero, ícono `Upload`): elegir formato (tarjetas: "Ventas de Toronja", "Ingresos", "Gastos", "Efectivo"), soltar archivo, **vista previa** con resumen (a crear / errores / duplicados / omitidas), tabla de filas con estado y mensaje, filtros por estado, y para el genérico el mapeo de columnas con selects. Botón "Importar N operaciones". Resultado con enlaces a Ingresos / Por cobrar filtrados por la fecha. Historial de lotes.
- Configuración → "Importación": cuenta de banco, procesador y categoría por defecto de Toronja.
- Empty state: "Sube el reporte de ventas de Toronja o un Excel de gastos; antes de registrar nada vas a ver qué entra."

## Pruebas (mínimo)

Con un HTML sintético de 12 tickets (varias unidades, formas de pago mezcladas, uno cancelado, uno con adeudo, uno con vendedor desconocido, uno de soporte en 0, dos del mismo día y unidad): vista previa clasifica cada fila; confirmar crea exactamente los ingresos agrupados con montos correctos por forma de pago en la cuenta correcta y la CxC de adeudos; saldos de caja/procesador/banco suben lo justo; reimportar crea cero y marca duplicados; vendedor desconocido queda en error sin bloquear; nombre de paciente no aparece en ningún payload; tenant isolation; genérico CSV con mapeo crea gastos, detecta duplicado por hash y categoría inexistente da error por fila; XLSX se lee; mes cerrado bloquea sólo sus filas.

## Lo que queda al implementador

Estructura exacta del parser HTML (recomendado: `html.parser` acumulando celdas por fila); si la vista previa se pagina en el cliente o el servidor; íconos. No tocar `rules.py`.
