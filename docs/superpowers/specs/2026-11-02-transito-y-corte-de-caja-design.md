# Dinero en tránsito y corte de caja

_Spec 2026-11-02. Dominio ONE Treasury. Segundo bloque del MVP de LaFe: HU-07 (corte y entrega de efectivo), HU-14 (cobros pendientes de recepción), HU-19 (disponible vs pendiente), base de HU-13/HU-15 (conciliación y comisiones). Reglas de negocio de LaFe: RN-02 (la "Reco" es un traspaso) y el tratamiento de NetPay como cuenta por liquidar._

## Intención

En LaFe el 41 % de la venta se cobra con tarjeta por NetPay y se deposita días después, menos comisión; el 56 % es efectivo que cada unidad corta a diario y entrega a la caja central que administra Abraham. Hoy ONE Finance sólo sabe "cobrado" o "no cobrado": una venta con tarjeta sube el disponible el mismo día, y el corte de caja no existe. Este bloque agrega (1) cuentas de dinero **en tránsito** que no cuentan como disponible y se liquidan al banco con su comisión, y (2) el **corte de caja** por unidad con arqueo, diferencia explicada y entrega a la caja central.

## Objetivos

- Separar en el tablero "Disponible" de "Por recibir de procesadores" (HU-19) y que la fecha de venta y la de depósito vivan separadas (HU-14).
- Que una liquidación de NetPay mueva el bruto a banco, registre la comisión como gasto financiero y nunca duplique el cobro.
- Corte diario por caja: esperado vs contado, diferencia con explicación obligatoria, entrega con quién entrega y quién recibe (HU-07).

## No objetivos

Conciliación contra estado de cuenta (HU-13), validación automática de comisiones contra tarifas (HU-15: sólo se guarda la tasa pactada para después), apertura de caja con fondo fijo, varios cortes por día por caja.

## Modelo

**Cuentas de dinero.** Nuevo tipo `PROCESSOR` en `FINANCIAL_ACCOUNT_TYPES` (activo, no disponible). Campos nuevos en `financial_accounts`: `fee_rate` Numeric(6,4) nullable (0.0350 = 3.5 %), `settlement_days` int nullable, `settlement_account_id` FK nullable (el banco donde liquida). En el catálogo contable, una cuenta `PROCESSOR` se refleja en la cuenta de mayor **"Cobros en tránsito"** (ver cómo el motor mapea hoy `CASH`/`BANK` a 1100/1200 en `rules.py` y `coa.py`; si no existe una cuenta de detalle para tránsito, se agrega al catálogo sembrado con código agrupador SAT 107.05 y se incluye en las cuentas controladas por módulo `MODULE_CONTROLLED_CODES`). Esta es la única extensión permitida al motor: una cuenta nueva y su regla de espejo, en `rules.py` y `coa.py`, con prueba.

**Liquidaciones.** `processor_settlements`: `id`, `organization_id`, `processor_account_id`, `bank_account_id`, `date`, `gross_amount`, `fee_amount` (≥0), `net_amount` (= bruto − comisión, calculado), `reference` (100, única por empresa y procesador cuando viene), `notes`, `created_by`, `transfer_group_id` (del traspaso que generó), `expense_id` (del gasto de comisión, nullable si comisión 0), AuditMixin.

**Cortes de caja.** `cash_cuts`: `id`, `organization_id`, `financial_account_id` (caja de tipo CASH), `business_unit_id` (la de la caja, copiada), `date`, `opening_balance` (saldo de la caja al inicio del día = saldo antes del primer movimiento del día), `inflows`, `outflows` (sumas de movimientos del día en esa caja), `expected_closing` (= apertura + entradas − salidas), `counted_amount` nullable, `difference` (= contado − esperado), `explanation` (500, obligatoria si `difference != 0`), `status` en `OPEN | COUNTED | DELIVERED`, `delivered_amount` nullable, `delivered_to_account_id` nullable (caja central o banco), `delivered_by` (user), `received_by` (user, nullable hasta confirmar), `received_at`, `transfer_group_id`, `adjustment_transaction_id` nullable, `closed_by`, `closed_at`, AuditMixin. Única por (caja, fecha).

Migración `20261102_04_transito_y_cortes.py` (`down_revision` = head de tu worktree).

## Reglas

1. **Disponible.** Dashboard, reportes de flujo, `cash` del resumen, `/api/financial-accounts` (`current_balance` se mantiene) y el asistente (`list_accounts` ya devuelve tipo): el total "disponible" excluye `PROCESSOR`; se agrega `in_transit_total` al resumen del tablero y una tarjeta "Por recibir" junto a "Disponible". Las series de caja no cambian de forma: añaden la serie de tránsito sólo si la empresa tiene procesadores.
2. **Ingreso con tarjeta.** Si la empresa tiene una cuenta `PROCESSOR` activa y el ingreso trae `payment_method` tarjeta (débito o crédito) sin cuenta explícita, la cuenta por defecto es el procesador (en el formulario se preselecciona; en la API se infiere igual). La póliza es la de siempre: cargo a la cuenta espejo del procesador, abono a ingresos.
3. **Liquidación.** `POST /api/financial-accounts/{id}/settlements` con `{date, gross_amount, fee_amount, bank_account_id?, reference?, notes?}`: valida que `{id}` sea `PROCESSOR` y el banco sea `BANK` de la misma empresa (si no viene, usa `settlement_account_id`; si tampoco, 400 "Elige el banco donde liquida."); `gross_amount` no puede exceder el saldo del procesador (400 "NetPay sólo tiene $X por liquidar."); crea en una sola transacción de BD: un traspaso procesador → banco por el **neto** y un gasto de comisión por `fee_amount` pagado desde el procesador con la categoría de gasto "Comisiones de terminal" (se siembra si no existe; cuenta contable de gasto financiero, misma que usan hoy las comisiones bancarias si existe una). Resultado: el procesador baja el bruto, el banco sube el neto, el gasto queda en resultados. `reference` repetida → 409 "Esa liquidación ya está registrada." Se cancela con `DELETE` → revierte las dos operaciones con el mecanismo de reverso existente.
4. **Corte.** `POST /api/cash-cuts` `{financial_account_id, date}` (una por caja y día; 409 si existe): calcula apertura, entradas, salidas y esperado desde los movimientos de la caja ese día y queda `OPEN`. `POST /api/cash-cuts/{id}/count` `{counted_amount, explanation?}`: fija contado y diferencia; si la diferencia no es cero y no hay explicación → 400 "Explica la diferencia."; si hay diferencia registra un movimiento de ajuste en la caja (ingreso o gasto con categoría "Diferencias de caja", sembrada) para que el saldo de la caja quede en lo contado; estado `COUNTED`. `POST /api/cash-cuts/{id}/deliver` `{delivered_amount, delivered_to_account_id}`: traspaso caja → destino por ese monto (no puede exceder lo contado), `delivered_by` = usuario; estado `DELIVERED`. `POST /api/cash-cuts/{id}/confirm-receipt`: lo llama quien recibe (otro usuario con rol de escritura, o el mismo si es OWNER/ADMIN); fija `received_by`, `received_at`. Cualquier paso posterior a `OPEN` queda bloqueado si el mes está cerrado (el candado del motor ya lo hace).
5. **Recontar.** Un corte `COUNTED` se puede volver a contar: revierte el ajuste anterior y crea uno nuevo. Un corte `DELIVERED` no se edita; se cancela entero (`DELETE`) revirtiendo entrega y ajuste.
6. **Permisos.** Liquidar y cancelar: OWNER/ADMIN. Cortar, contar y entregar: cualquier rol de escritura. Confirmar recepción: rol de escritura.

## API

- `GET /api/cash-cuts?account_id=&date_from=&date_to=&status=&business_unit_id=` paginado; `GET /{id}`; `POST`, `POST /{id}/count`, `/{id}/deliver`, `/{id}/confirm-receipt`, `DELETE /{id}`.
- `GET /api/cash-cuts/today` → por cada caja CASH activa: saldo actual, si ya tiene corte hoy y en qué estado.
- `GET /api/financial-accounts/{id}/settlements` paginado; `POST`; `DELETE /{sid}`.
- `GET /api/dashboard/summary` suma `in_transit_total`; `financial-accounts` expone `fee_rate`, `settlement_days`, `settlement_account_id`, y `available: bool`.
- Reportes: el flujo de efectivo separa "Liquidaciones recibidas" si lo pide un filtro; no es obligatorio en esta ola.

## Interfaz

- **Cuentas:** tipo "Procesador de pagos (NetPay, Mercado Pago)" en el formulario con tasa, días de liquidación y banco destino. Tarjeta de cuenta procesador con botón "Registrar liquidación" (bruto, comisión, neto calculado, fecha, referencia) y su historial.
- **Inicio:** "Disponible" y al lado "Por recibir" con el total en tránsito (solo si hay procesadores).
- **Página "Caja"** (nav, sección Dinero, ícono `Banknote`): hoy por caja (saldo, estado del corte), "Hacer corte" → pantalla con apertura/entradas/salidas/esperado, campo contado, diferencia en vivo con color (`text-pos`/`text-neg`), explicación, "Guardar conteo"; luego "Entregar" (monto, destino) y "Confirmar recepción". Historial de cortes con filtro por unidad y estado. Empty state: "Da de alta una caja de efectivo para hacer cortes."
- Copy en español; cifras `.figures`; tokens semánticos.

## Pruebas (mínimo)

Tipo `PROCESSOR` fuera del disponible y dentro de `in_transit_total`; ingreso con tarjeta cae al procesador por defecto; liquidación: saldos (procesador −bruto, banco +neto), gasto de comisión en resultados, póliza cuadrada, referencia repetida 409, bruto mayor al saldo 400, cancelación revierte todo; corte: esperado calculado desde movimientos, diferencia exige explicación, ajuste deja la caja en lo contado, recontar revierte el ajuste previo, entrega crea traspaso y no excede lo contado, confirmación fija quién recibe, una por caja y día, tenant isolation en todo, mes cerrado bloquea.

## Lo que queda al implementador

Nombre exacto de la cuenta de mayor de tránsito en el catálogo sembrado y su posición; forma de la pantalla de corte; si la lista de cortes vive en la misma página que "hoy". Lo que choque con un invariante de `AGENTS.md` se resuelve a favor del invariante y se anota.
