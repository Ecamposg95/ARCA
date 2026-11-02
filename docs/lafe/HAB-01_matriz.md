# HAB-01 · LaFe contra la plataforma actual

_2026-11-02. Comparación de las 22 historias de `BACKLOG.md` contra Atlas ONE Finance en producción (commit `7bb6ea1`), verificada en el código, no de memoria. Empresa ya creada en prod: "Laboratorios La Fe" (`lafe@atlas.mx`)._

**Leyenda.** Disponible: cumple los criterios tal cual. Parcial: la base existe y faltan criterios concretos. Faltante: no existe. Por probar: existe en código pero hay que validarlo con datos de LaFe.

## Resumen

| Estado | Historias |
|---|---|
| Disponible (4) | HU-03, HU-06, HU-16, HU-20 |
| Parcial (9) | HU-01, HU-02, HU-04, HU-05, HU-09, HU-11, HU-17, HU-18, HU-19 |
| Faltante (9) | HU-07, HU-08, HU-10, HU-12, HU-13, HU-14, HU-15, HU-21, HU-22 |

Del MVP recomendado (entregas 1 a 4: HU-01 a HU-11, HU-14 y HU-19), lo que hay que construir es: **sucursales**, **corte de caja** (HU-07), **autorización por monto** (HU-08), **importación de Excel/CSV** (HU-10), **cobros en tránsito** (HU-14), **adjuntos** en gastos, **historial de modificaciones** y **exportación de movimientos con más filtros**. Lo demás ya opera.

## Tres huecos transversales

1. **Sucursal.** No existe el concepto. Pesa en HU-02, HU-04, HU-07, HU-11 y HU-19. Decisión de diseño: una sucursal es un atributo de la caja/cuenta y de cada movimiento (no una empresa aparte, porque LaFe es una sola razón social). Es lo primero que se construye porque todo lo demás lo referencia.
2. **Dinero en tránsito.** Hoy un ingreso está cobrado o pendiente; no hay "cobrado por NetPay/Mercado Pago, aún no depositado". Pesa en HU-04, HU-13, HU-14, HU-15 y HU-19. Diseño propuesto: una cuenta de dinero por procesador (tipo "en tránsito") que no cuenta como disponible y se vacía al banco con la liquidación; la comisión sale ahí.
3. **Autorización por monto.** Existe la bandeja de propuestas con aprobación humana (para agentes). El estado "pendiente de autorización" en un gasto o pago de proveedor, con umbral por rol, no existe. Se reutiliza el patrón de bandeja.

## Matriz por historia

| HU | Historia | P | Estado | Qué existe hoy | Qué falta |
|---|---|---|---|---|---|
| 01 | Accesos y permisos | P0 | Parcial | 5 roles por empresa (OWNER, ADMIN, ACCOUNTANT, MEMBER, VIEWER), alta de miembros en Configuración → Equipo, misma vista para OWNER y ADMIN. Mapeo natural: Liza OWNER, Abraham ADMIN, auxiliar MEMBER. | MEMBER captura todo sin límite: la restricción del auxiliar depende de HU-08 y de la decisión 2. No hay permiso separado para "modificar". |
| 02 | Catálogos financieros | P0 | Parcial | Cajas, cuentas bancarias y tarjetas; categorías de ingreso y gasto editables, desactivar conserva historial; las fuentes de ingreso (mostrador, empresas, rentas) se modelan como categorías de ingreso; préstamos son pasivo y traspasos no son ingreso ni gasto. | Sucursales. Inversiones como instrumento (hoy solo activos fijos). Catálogo de LaFe por validar (HAB-04). |
| 03 | Saldos iniciales | P0 | Disponible | Saldo inicial por caja/cuenta con fecha; póliza de apertura contable cuadrada (C-2); el saldo actual = inicial + movimientos, explicable en el diario. | El "responsable" del saldo se infiere del usuario que creó la cuenta; no se captura explícito. La no duplicación con la carga histórica es regla de la importación (HU-10). |
| 04 | Registro de ingresos | P0 | Parcial | Fecha, importe, categoría, cliente, cuenta receptora, medio de pago, referencia, cobrado vs pendiente, póliza automática. | Sucursal. "Pendiente de recepción" como tránsito (HU-14), distinto de "no cobrado". |
| 05 | Registro de egresos | P0 | Parcial | Importe, fecha, categoría, concepto, proveedor, cuenta origen, medio de pago, referencia, notas, usuario que registra, cancelación con motivo. | Adjuntar soporte (no hay almacenamiento de archivos). Autorización (HU-08). Sucursal. |
| 06 | Traspasos internos | P0 | Disponible | Origen, destino, importe, fecha, responsable; salida y entrada ligadas por grupo; no tocan resultados. | Confirmación de recepción diferida (traslado no inmediato): se cubre con la cuenta "en tránsito" de HU-14. |
| 07 | Corte y entrega de efectivo | P0 | Faltante | Saldo de caja en tiempo real y traspasos caja → matriz como base. | Apertura, arqueo (esperado vs contado), diferencias con explicación, entrega con quién entrega y quién recibe. |
| 08 | Autorizaciones por monto | P0 | Faltante | Bandeja de propuestas con aprobación humana, decisión, responsable y fecha (capa agéntica). | Umbrales por rol, estado "pendiente de autorización" en gastos/pagos, aprobar/rechazar con motivo, que lo pendiente no cuente como pagado. Depende de la decisión 1. |
| 09 | Historial de cambios | P0 | Parcial | Quién creó y quién canceló con motivo; nada se borra: una cancelación genera póliza de reverso; el libro es inmutable; acciones de agentes auditadas. | Historial de modificaciones con valores anteriores (no hay tabla de cambios). Por probar: qué campos se pueden editar después de pagar. |
| 10 | Importación Excel/CSV | P0 | Faltante | Nada (solo exportación). | Mapeo de columnas, vista previa, errores, duplicados, resultado por fila, reimportación idempotente. Necesita HAB-02 (los archivos reales). |
| 11 | Consulta y exportación | P0 | Parcial | Movimientos con filtros por periodo, cuenta, tipo y origen; totales del filtro; CSV de reportes con permisos. | Filtros por sucursal, categoría, responsable, medio de pago y estado; exportar la lista de movimientos (hoy solo reportes). |
| 12 | Carga bancaria | P1 | Faltante | Nada. Está en el plan maestro como BANK (fase 2). | Carga por archivo con cuenta, periodo, duplicados entre cargas. |
| 13 | Conciliación | P1 | Faltante | Nada. BANK, fase 2. | Coincidencias propuestas, confirmar/rechazar, depósito que liquida varias ventas. |
| 14 | Cobros pendientes de recepción | P0 | Faltante | Ingreso pendiente y CxC (que son deuda del cliente, no tránsito). | Cuenta en tránsito por procesador, fecha de venta vs fecha de depósito, recepción que mueve a banco sin duplicar. |
| 15 | Validación de comisiones | P1 | Faltante | Nada. | Tasas por proveedor y vigencia; bruto, comisión esperada, neto; diferencias. Se apoya en HU-14. |
| 16 | Cuentas por pagar | P1 | Disponible | Proveedor, concepto, importe, vencimiento, pagos parciales, estados (abierta, parcial, pagada, vencida, cancelada), recurrentes que se proponen solas; el pago no duplica el gasto. | Nada estructural. Por validar con LaFe la lista de compromisos. |
| 17 | Planeación semanal | P1 | Parcial | Por pagar con vencidos y próximos; dashboard con series semanales; semáforo de vencidos. | Vista "esta semana": comprometido vs disponible y faltante; notificación del lunes (decisión 7). |
| 18 | Cuentas por cobrar | P1 | Parcial | Cliente, concepto, importe, vencimiento, abonos parciales, saldo, vencidas; el cobro genera el ingreso sin duplicarlo. | Antigüedad por tramos (30/60/90). |
| 19 | Tablero de disponibilidad | P0 | Parcial | Saldos por cuenta y consolidado en Inicio y Cuentas, clic a movimientos. | Separar disponible de "en tránsito" (HU-14); por sucursal; última actualización. |
| 20 | Estado de resultados | P1 | Disponible | ER por periodo, gasto por categoría con importe y porcentaje, fecha de corte; préstamos, activos y traspasos con tratamiento contable correcto; cada cifra deriva del libro. | Por probar: drill-down de cada rubro a sus movimientos. "Información pendiente de integrar" depende de HU-14. Estructura por validar con el contador (decisión 3). |
| 21 | Integraciones | P2 | Faltante | API con llaves por empresa, idempotencia por origen (`source_type`/`source_id`), bandeja de propuestas. Webhooks firmados y outbox en el plan ROB. | Conectores Toronja, NetPay, Mercado Pago (cada uno por separado, HAB-07). |
| 22 | Proyección de flujo | P2 | Faltante | Flujo de efectivo histórico. | Proyección con CxC, compromisos y supuestos marcados. Es el CFO de la fase 5. |

## Qué se construye para el MVP de LaFe (entregas 2 a 4)

En orden de dependencia, con el dominio ONE que le toca:

1. **Sucursales** (ONE Accounting / base): entidad, atributo en cajas y cuentas, en ingresos, gastos y traspasos, y filtro en listas y tablero. Habilita HU-02, 04, 07, 11, 19.
2. **Cobros en tránsito** (ONE Treasury): cuentas tipo procesador, liquidación a banco con comisión, tablero que separa disponible de pendiente. Cierra HU-14 y la mitad de HU-19; deja lista la conciliación (HU-13, 15).
3. **Autorización por monto** (ONE Payables): umbral por rol, estado pendiente en gasto y pago de CxP, bandeja de autorización. Cierra HU-08 y la restricción del auxiliar de HU-01. Bloqueado por la decisión 1.
4. **Corte de caja** (ONE Treasury): apertura, arqueo, diferencia explicada, entrega a matriz. Cierra HU-07.
5. **Importación Excel/CSV** (ONE Accounting): ingresos, gastos y saldos con mapeo, vista previa y huella por fila para reimportar sin duplicar. Cierra HU-10 y la carga histórica de HU-03. Bloqueado por HAB-02.
6. **Adjuntos** en gastos (HU-05) y **historial de modificaciones** (HU-09).
7. **Exportación y filtros** de movimientos (HU-11).

Lo que ya está (HU-03, 06, 16, 20 y la base de 01, 02, 04, 05, 09, 18) se prueba con datos de LaFe (HAB-08), no se reconstruye.

## Lo que necesito de LaFe antes de construir

- **Decisión 1 (umbral):** $100,000 confirmado, qué pasa con exactamente $100,000, y si aplica a gastos, pagos de CxP, traspasos o todos.
- **Decisión 2 (auxiliar):** qué puede capturar y hasta qué monto; si ve saldos.
- **Sucursales:** cuántas, cuáles tienen caja propia, y si la matriz recibe efectivo de todas.
- **HAB-02:** un Excel real de ingresos, uno de gastos, un corte de caja y un estado de cuenta (o reporte de liquidación de NetPay y de Mercado Pago). Sin eso la importación se diseña a ciegas.
- **Decisión 4 (tiempos de liquidación):** NetPay y Mercado Pago, cada cuántos días depositan y si agrupan ventas.
