# ARCA · Plan maestro del MVP e integraciones Atlas

_Fecha: 2026-10-12 · Versión compartible (con diagramas): https://claude.ai/code/artifact/45f1d0e4-9b85-4ced-8f63-7ced4d33e4eb_

ARCA será el sistema con el que un despacho contable lleva a sus pymes y con el que el dueño entiende su negocio, conectado a Atlas ONE (ventas), Atlas Cortex (agentes) y HRFlow (nómina). Este documento fija los diez alcances que faltan para ese MVP, los contratos de integración con los otros productos Atlas y el orden en que se construyen. La referencia técnica del sistema vive en `docs/ARCHITECTURE.md`.

## 1. Por qué se gana así

Una pyme mexicana vive dos ciclos obligatorios: el del SAT (emitir y recibir CFDI, declarar IVA e ISR cada mes) y el del dinero (cobrar, pagar, cuadrar el banco). Gana la plataforma que tenga ambas verdades dentro, las contabilice sola y hable en lenguaje de empresario. CONTPAQi y Aspel viven con el contador y el dueño nunca los abre; Alegra y Bind viven con el dueño y el contador recaptura. Ninguno conecta ventas, nómina y agentes en el mismo libro.

El canal de entrada es el despacho (Asecofim es el primer partner): el contador migra a sus clientes y el dueño entra después por la facturación y el CFO.

## 2. Estado de partida

Producción corre en Railway con 310 pruebas verdes y un solo head de migraciones. Existe: motor contable de partida doble con folios, candado de mes y reversos; operación completa del dueño (ingresos, gastos, instrumentos con naturaleza, CxC y CxP con devengo, IVA por flujo, retenciones, activos fijos, préstamos, recurrentes, proyectos); reportes derivados del ledger; capa agéntica con llaves, 18 herramientas, auditoría y bandeja de propuestas; portal de despacho multiempresa; puente a CONTPAQi (sin verificar contra un CONTPAQi real) y contabilidad electrónica SAT Anexo 24. Detalle en `docs/MVP_STATUS.md`.

Lo que no hay y este plan cubre: pólizas manuales y catálogo editable; apertura y cierre anual; estados financieros NIF; entrada y salida de CFDI; conciliación bancaria; cálculo de impuestos y calendario; eventos desde Atlas ONE y HRFlow; Cortex operando de verdad sobre ARCA.

Deuda técnica que las integraciones obligan a pagar primero: rate limiting, expiración de propuestas y outbox durable de eventos.

## 3. Alcances

Tamaños estimados de construcción con forks en paralelo: S 1 a 2 días, M 3 a 5, L 6 a 10, XL 10 a 15.

| Id | Módulo | Para quién | Tamaño | Fase |
| --- | --- | --- | --- | --- |
| ROB | Robustez de plataforma | Todos | M | 0 |
| C1 | Pólizas manuales y catálogo editable | Contador | S | 1 |
| C2 | Apertura y cierre anual | Contador | M | 1 |
| B | Estados financieros NIF | Contador y banco | S | 1 |
| E | Importar CFDI | Contador y dueño | M | 2 |
| BANK | Conciliación bancaria | Ambos | M | 2 |
| TAX | Cédula de impuestos y calendario | Contador | M | 3 |
| DESP | Flujo de trabajo del despacho | Contador | S | 3 |
| FACT | Facturación CFDI 4.0 vía PAC | Dueño | XL | 4 |
| CFO | ARCA CFO y bandeja mágica | Dueño | M | 5 |

### ROB · Robustez de plataforma
- Rate limiting y bloqueo temporal en `/api/auth/*` y por llave en `/api/agent/invoke` (slowapi, como Cortex).
- Expiración y edición de propuestas antes de aprobar.
- Outbox durable: tabla `outbox_events` escrita en la misma transacción que el cambio, worker que entrega con reintentos exponenciales y marca `FAILED` al quinto intento; reemplaza al bus síncrono en proceso.
- Webhooks entrantes: tabla `inbound_events` con llave única `(organization_id, source, external_reference)`, firma HMAC-SHA256 y ventana de 5 minutos.
- Partición del bundle del frontend (recharts bajo demanda).
- **Hecho cuando:** un evento sobrevive a un reinicio del servicio; una llave abusiva recibe 429; un webhook con firma inválida recibe 401 y no deja rastro en el libro.

### C1 · Pólizas manuales y catálogo editable
- `POST /api/accounting/journal-entries`: póliza de diario con varias líneas, siempre `DIARIO`, origen `manual`, fecha no futura y mes abierto; sólo cuentas de detalle; bloqueadas las cuentas que mueven los módulos (1100, 1200, 2100, 2200).
- `POST /api/accounting/journal-entries/{id}/reverse`: póliza espejo, una sola vez.
- `POST /api/accounting/accounts` y `PATCH` ampliado: cuentas de detalle bajo una mayor, código numérico único de 4 a 10 dígitos que empieza con el dígito de la mayor, renombrar, desactivar sin movimientos, reactivar.
- UI: "Nueva póliza" en Diario con rejilla de líneas y totales vivos; "Revertir" en el detalle; "Nueva cuenta", nombre editable y desactivar en Catálogo.
- **Hecho cuando:** el contador registra nómina provisionada y una depreciación extra sin tocar código, y la cuenta nueva aparece en balanza, XML del SAT y export CONTPAQi.

### C2 · Apertura y cierre anual
- Póliza de apertura con saldos por cuenta a la fecha de inicio en ARCA (migración desde CONTPAQi), balanceada contra 3100/3200.
- Cierre de ejercicio: traspaso de 4xxx y 5xxx a 3200, candado anual (`fiscal_year_locks`), reapertura con motivo y rastro.
- La balanza SAT deja de simular el cierre cuando existe uno real.
- **Hecho cuando:** enero abre con utilidad acumulada correcta y la balanza XML cuadra sin lógica virtual.

### B · Estados financieros NIF
- Estado de situación financiera clasificado (circulante y no circulante, corto y largo plazo) con clasificación por cuenta en el catálogo.
- Estado de resultados por naturaleza con utilidad bruta, de operación y neta.
- Flujo de efectivo por método indirecto; comparativo contra el ejercicio anterior; PDF y Excel con encabezado de la empresa.
- **Hecho cuando:** el contador entrega el paquete mensual al cliente desde ARCA.

### E · Importar CFDI
- Carga de XML sueltos o ZIP (ingreso, egreso, pago y nómina 4.0); validación de RFC emisor y receptor contra la empresa; deduplicación por UUID; tabla `cfdi_documents`.
- Vínculo con ingresos, gastos, CxC y CxP existentes por monto, fecha y RFC; propuesta de operación para los no vinculados vía bandeja (`propose_cfdi_link`).
- Segunda etapa: descarga masiva del SAT con e.firma cifrada por empresa.
- **Hecho cuando:** un mes completo de facturas recibidas queda contabilizado con cinco clics.

### BANK · Conciliación bancaria
- Importar estado de cuenta CSV y Excel (BBVA, Banorte, Santander, Banamex) a `bank_statements` y `bank_lines`.
- Motor de cruce por monto, fecha y referencia; propuestas de cruce (`propose_bank_match`) que un humano aprueba; no identificados convertidos en propuesta de gasto o ingreso.
- Saldo conciliado contra saldo en libros por cuenta financiera; open banking (Belvo o Syncfy) en segunda etapa.
- **Hecho cuando:** el mes queda conciliado con cero diferencias sin salir de ARCA.

### TAX · Cédula de impuestos y calendario
- `fiscal_profiles`: régimen por empresa (RESICO PF y PM, general de ley, actividad empresarial), coeficiente de utilidad, fechas.
- Cédula mensual: IVA (desde el reporte existente), ISR provisional según régimen, retenciones a enterar; DIOT en layout oficial.
- `obligations`: calendario con fechas y estado, integrado al semáforo del despacho.
- **Hecho cuando:** la cédula del mes coincide con la del contador en las tres empresas demo.

### DESP · Flujo de trabajo del despacho
- `client_tasks`: tareas y solicitudes al cliente (falta factura, clasifica este gasto) con estado y vencimiento.
- Paquete de cierre mensual en PDF; notificaciones por correo; logo del despacho en los entregables.
- **Hecho cuando:** el contador cierra un mes y el dueño recibe su paquete sin que nadie mande un correo a mano.

### FACT · Facturación CFDI 4.0 vía PAC
- `csd_credentials` cifradas por empresa; catálogos del SAT (`c_ClaveProdServ`, `c_UsoCFDI`, `c_RegimenFiscal`, `c_FormaPago`, `c_MetodoPago`).
- Emisión de ingreso PUE y PPD desde una CxC o una venta de Atlas ONE; complemento de pago (REP) desde cobros; cancelación con motivo; PDF con QR; envío por correo; factura global mensual.
- Servicio de timbrado compartido: facturas de ARCA y ONE, recibos de nómina 1.2 de HRFlow.
- PAC elegido en la spec tras sandbox (Facturama, SW Sapien o Finkok).
- **Hecho cuando:** una factura emitida en ARCA aparece en el portal del SAT y su cobro genera el REP.

### CFO · ARCA CFO y bandeja mágica
- Chat y alertas sobre la empresa a través de Cortex con las herramientas de lectura; tabla `notices` alimentada por `notify_owner`.
- Resumen semanal proactivo por correo (caja proyectada, vencidos, mes sin cerrar).
- Bandeja mágica: foto, PDF o XML se convierte en propuesta con evidencia usando visión de Claude.
- **Hecho cuando:** el dueño recibe el lunes un correo que le dice qué cobrar y qué pagar, y lo aprueba desde ARCA.

## 4. Integraciones Atlas

ARCA es el libro y el centro fiscal de Atlas: ONE, Cortex y HRFlow le mandan eventos de dinero firmados e idempotentes, y ARCA les devuelve contabilidad, CFDI timbrados y propuestas aprobadas. Los tres repos se revisaron el 2026-10-12 y ninguno menciona hoy a ARCA, así que cada integración lleva trabajo en ambos lados.

### Patrón común
1. El sistema origen escribe el evento en su outbox transaccional.
2. Un despachador lo envía por HTTPS a `POST /api/integrations/<origen>/events` con cabeceras `X-Atlas-Signature` (HMAC-SHA256 del cuerpo con el secreto de la conexión), `X-Atlas-Timestamp` (ventana de 5 minutos) y `X-Atlas-Event-Id`.
3. ARCA lo guarda en `inbound_events`; la llave única `(organization_id, source, external_reference)` rechaza duplicados con 200 sin reprocesar.
4. La regla contable correspondiente en `rules.py` arma la póliza y, si aplica, el movimiento; respuesta 202.
5. Un trabajo diario de reconciliación consulta al origen por rango de fechas y detecta eventos perdidos; al tercer fallo de entrega se alerta por correo.
6. Cada empresa guarda su conexión (URL, secreto, mapeos) en `integration_connections`; ningún secreto vive en variables globales.

| Integración | Dirección | Eventos | Idempotencia | Qué produce en ARCA |
| --- | --- | --- | --- | --- |
| Atlas ONE → ARCA | Ventas y caja hacia el libro; CFDI de regreso | `sale.paid`, `payment.recorded`, `sale.cancelled`, `refund.approved`, `cash_session.closed` | `atlas-one:<org>:<sales_document_id>:<estado>` | Ingreso con IVA desglosado, propina como pasivo, CxC para crédito, cobro de abonos, reverso de devoluciones, movimiento en la cuenta de la sucursal |
| Cortex ↔ ARCA | Cortex razona, ARCA ejecuta con aprobación | Herramientas `arca_*` vía llave `ak_`; `proposal.decided` de regreso | `proposal_id` persistido en Cortex | Propuestas en la bandeja, avisos del CFO, brief ejecutivo con datos reales |
| HRFlow → ARCA | Nómina hacia el libro; CFDI de nómina de regreso | `payroll.approved`, `payroll.paid`, `payroll.cancelled` | `hrflow:<empresa>:<periodo>:<evento>` | Provisión de sueldos, retenciones, cuotas patronales, pago del neto, recibos timbrados |

### Atlas ONE (POS y ERP · FastAPI · Docker en IONOS · 4 tiendas en producción)

**Lo que hay.** `SalesDocument` con estados `DRAFT|PENDING|PAID|CANCELLED|REFUNDED_PARTIAL|REFUNDED_TOTAL`, `Payment` por método (`CASH|CARD|TRANSFER|OTHER`), `SaleReturn`, un outbox transaccional con un solo evento (`SalesDocumentCreated`, sólo en proceso, sin montos ni `organization_id`), JWT de usuario, llaves de API definidas pero sin usar, sin CFDI.

**Hallazgos que condicionan el contrato.** "Creada" no es "cobrada" y el mismo evento sale dos veces para ventas a crédito; abonos, cancelaciones, devoluciones y cotizaciones convertidas no emiten nada; `total_amount` incluye la propina; el recargo por tarjeta no está en `total_amount`; el IVA sólo se desglosa si el ticket pide factura; el efectivo guardado es el entregado, no el neto del cambio; las fechas están en UTC; cancelar una venta pendiente con cliente truena hoy.

**Trabajo en ONE.** Publicar los cinco eventos con montos, IVA desglosado, propina y recargo por separado, sucursal, método y fecha local; despachador de webhooks desde su outbox con HMAC; conexión a ARCA por organización; exponer `tip_amount`, `usd_rate` y `updated_at` en lectura; corregir la cancelación.

**Trabajo en ARCA.** Endpoint de eventos; reglas `pos_sale_paid`, `pos_payment_recorded`, `pos_sale_cancelled`, `pos_refund_approved`; cuenta 2500 Propinas por pagar; mapeo sucursal y método a cuenta financiera editable en Configuración; reconciliación diaria contra `GET /api/sales/`; en FACT, `POST /api/invoices` para que ONE pida el CFDI de un ticket con RFC y reciba UUID y PDF, más la factura global mensual.

Ejemplo de `sale.paid`:

```json
{
  "event": "sale.paid",
  "event_id": "9b1f...",
  "occurred_at": "2026-10-12T19:42:10-06:00",
  "external_reference": "atlas-one:7:0f3a...:PAID",
  "organization_external_id": "7",
  "branch": "Centro",
  "sales_document_id": "0f3a...",
  "series": "A", "folio": 1842,
  "subtotal": "1000.00", "tax": "160.00", "total": "1160.00",
  "tip": "100.00", "card_surcharge": "0.00",
  "payments": [{"method": "CARD", "amount": "1260.00", "reference": "AUTH123"}],
  "customer": {"tax_id": "XAXX010101000", "name": "Público en general"},
  "requires_invoice": false
}
```

Póliza resultante: cargo 1100 (cuenta mapeada de la sucursal y método) 1260.00; abono 4100 Ventas 1000.00; abono 2190 IVA trasladado cobrado 160.00; abono 2500 Propinas por pagar 100.00.

### Atlas Cortex (sistema operativo agéntico · FastAPI · Railway)

**Lo que hay.** `ArcaConnection` por organización con la llave `ak_` en texto plano; cliente HTTP hacia `/api/agent/tools`, `/api/agent/invoke` y el estatus de propuestas; un toolset `arca_*` con gate `USE_ARCA` que nadie pasa al runtime (código muerto); brief del CFO con reglas fijas y `float`; sin loop proactivo; sin MCP; producción sin `ANTHROPIC_API_KEY`. Las herramientas `propose_*` no piden confirmación en Cortex y el ciclo de la propuesta nunca se cierra; el rol del dueño cliente no tiene `USE_ARCA`; las llamadas a ARCA son síncronas dentro de la petición del usuario.

**Trabajo en Cortex.** Cifrar la llave en reposo; inyectar el toolset de ARCA al runtime del agente CFO; persistir `proposal_id` y mostrar la tarjeta que enlaza a la bandeja de ARCA; loop semanal por organización que lee `finance_snapshot`, cartera vencida y meses sin cerrar y emite avisos; abrir `USE_ARCA` al dueño cliente; `Decimal` en los montos; endpoint con token de servicio para que la página CFO de ARCA converse con el agente.

**Trabajo en ARCA.** Webhook `proposal.decided` hacia Cortex al aprobar o rechazar; herramientas de propuesta nuevas (`propose_cfdi_link`, `propose_bank_match`, `propose_journal_entry`); herramienta `notify_owner` que alimenta `notices`; servidor MCP (A2) sobre la misma llave.

**Decisión abierta.** La llave de Anthropic vive en Cortex (recomendado: un solo runtime agéntico para Atlas) o ARCA corre su propio CFO. Este plan asume Cortex y deja a ARCA con el modo de lectura y alertas deterministas si la llave tarda.

### HRFlow (RR.HH. · Fastify y Prisma · Docker en IONOS · API detrás del proxy de Next)

**Lo que hay.** Nómina quincenal aproximada por empleado y periodo: bruto, IMSS obrero a tasa fija, ISR en cero, una sola deducción manual y marca de pagado por fila. Sin entidad periodo, sin CFDI de nómina, sin cuotas patronales ni provisiones, sin RFC ni registro patronal, sin eventos ni tokens de servicio, una base de datos por empresa. Lo que se asumiría mal: que hay UUID que conciliar, que ISR e IMSS guardados son reales, o que existe un `PayrollPaid`.

**Trabajo en HRFlow.** Entidad `PayrollPeriod` con estados calculada, autorizada, timbrada y pagada; desglose por concepto persistido (sueldo, incentivo, vacaciones; ISR, IMSS obrero, otras); motor fiscal con tablas de ISR, subsidio, cuotas IMSS obrero y patronal e INFONAVIT; RFC y registro patronal por empresa; `GET /nomina/periodos/:id/resumen`; token de servicio y webhooks firmados al autorizar y al pagar; dispersión por layout bancario como etapa posterior.

**Trabajo en ARCA.** Endpoint de eventos; reglas `payroll_accrual` (5200 Sueldos contra 2400 ISR retenido, 2420 IMSS obrero por enterar y 2150 Sueldos por pagar), `payroll_employer_cost` (5210 Cuotas patronales contra 2430 IMSS e INFONAVIT por pagar) y `payroll_paid` (2150 contra la cuenta bancaria); provisión mensual de aguinaldo y vacaciones (5220 contra 2440); vista Nómina con los periodos y su estado; en FACT, timbrado de CFDI de nómina 1.2 por recibo.

**Etapa 1 realista.** ARCA acepta el resumen con lo que HRFlow calcula hoy más las deducciones manuales, marcado "sin motor fiscal"; etapa 2 enciende el motor fiscal y el timbrado.

Ejemplo de `payroll.approved`:

```json
{
  "event": "payroll.approved",
  "external_reference": "hrflow:rmazh:2026-10-Q1:approved",
  "company_slug": "rmazh",
  "period": {"start": "2026-10-01", "end": "2026-10-15", "pay_date": "2026-10-15"},
  "employees": 18,
  "totals": {
    "gross": "180000.00", "isr": "0.00", "imss_employee": "4275.00",
    "other_deductions": "1200.00", "net": "174525.00",
    "imss_employer": null, "infonavit": null
  },
  "fiscal_engine": false
}
```

### Facturación como servicio compartido
Un solo proveedor de timbrado (PAC) integrado en ARCA sirve a los tres sistemas: facturas de ARCA y de ONE, factura global y recibos de nómina de HRFlow. Elegir el PAC es la primera decisión de la fase 4: Facturama, SW Sapien o Finkok, probados en sandbox con un CFDI de ingreso, un REP y un recibo de nómina antes de firmar.

## 5. Secuencia y fases

Seis fases ordenadas por dependencia, las dos primeras en paralelo, con un estimado total de 7 a 11 semanas de construcción; cada fase termina desplegada en producción y validada con la cartera demo del despacho antes de abrir la siguiente.

| Fase | Módulos de ARCA | Trabajo en otros sistemas | Depende de | Compuerta de salida |
| --- | --- | --- | --- | --- |
| 0 · Robustez | ROB | Nada | Nada | Un evento sobrevive a un reinicio; una llave abusiva recibe 429; webhook firmado rechaza firma inválida |
| 1 · Base contable | C1, luego C2, B en paralelo con C2 | Nada | Nada | El contador abre saldos, cierra el ejercicio demo y descarga el paquete NIF |
| 2 · Verdad del negocio | E y BANK en paralelo | Atlas ONE: eventos y despachador de webhooks | 0 | Un mes de CFDI recibidos contabilizado; banco conciliado a cero; ventas de ONE como ingresos del día |
| 3 · Cumplimiento | TAX y DESP en paralelo | HRFlow etapa 1: periodo, resumen y webhooks | 1 y 2 | Cédula del mes coincide con la del contador; paquete mensual sale solo; nómina provisionada y pagada en el libro |
| 4 · Facturación | FACT | ONE pide CFDI a ARCA; HRFlow etapa 2 timbra nómina | 2 | Factura en el portal del SAT; cobro genera REP; recibo de nómina timbrado |
| 5 · Inteligencia | CFO y bandeja mágica | Cortex: toolset vivo, loop semanal, ciclo de propuestas cerrado | 2 y 3 | El dueño recibe el lunes qué cobrar y qué pagar y lo aprueba desde ARCA |

Reglas de secuencia: dentro de una fase, los módulos marcados en paralelo corren en forks con territorios de archivos disjuntos; entre fases no se adelanta trabajo salvo specs. La fase 4 es la más larga y la única con un proveedor externo de por medio, por eso su spec y la prueba de sandbox del PAC arrancan durante la fase 3. El trabajo en ONE, Cortex y HRFlow se planea como sub-proyecto de cada repo con su propio spec, y ARCA publica primero el contrato (endpoint, firma, payload de ejemplo y pruebas de contrato).

## 6. Forma de trabajo y calidad

Cada módulo: diseño conversado → spec en `docs/superpowers/specs/AAAA-MM-DD-<tema>-design.md` → plan en `docs/superpowers/plans/` → forks paralelos con worktrees aislados y territorios disjuntos → verificación completa → merge → push a `main` (despliega). Los forks nunca pushean; la sesión principal re-verifica suite, build y captura antes de integrar.

**Definición de hecho por módulo**
- [ ] Spec aprobada y plan escrito, ambos en el repo
- [ ] Pruebas de aislamiento de tenant, partida doble, efecto en saldos y reporte contra ledger; archivo dorado si produce un formato externo
- [ ] `pytest`, `ruff check .`, `npm run typecheck` y `npm run build` verdes en local y en CI
- [ ] Migración con un solo head y nombre `AAAAMMDD_NN_slug`
- [ ] Captura de pantalla de la UI nueva revisada
- [ ] `docs/MVP_STATUS.md` y `AGENTS.md` actualizados si cambia un invariante o una regla
- [ ] Desplegado y probado contra la cartera demo en producción

**Riesgos**

| Riesgo | Impacto | Mitigación |
| --- | --- | --- |
| Layout de CONTPAQi sin verificar | El despacho no importa las pólizas | Bajado de pólizas de Asecofim en la fase 1 como archivo dorado |
| PAC tarda o su sandbox difiere de producción | La fase 4 se alarga | Dos PAC en sandbox durante la fase 3 |
| HRFlow sin motor fiscal de nómina | Nómina contabilizada aproximada | Etapa 1 marcada "sin motor fiscal"; etapa 2 antes de timbrar |
| Cortex sin llave de Anthropic en producción | El CFO no razona | Decisión en la fase 5; mientras, alertas deterministas desde ARCA |
| Secretos fiscales en la base | Exposición legal grave | Cifrado por empresa con llave maestra en entorno, rotación documentada, nunca en logs |
| Eventos perdidos entre sistemas | Libros incompletos | Outbox con reintentos, reconciliación diaria, alerta al tercer fallo |
| Alcance que crece | El MVP no llega | Nada entra sin spec; lo nuevo va a la fase siguiente |

**Decisiones abiertas**
- [ ] Proveedor de timbrado: Facturama, SW Sapien o Finkok, tras sandbox
- [ ] La llave de Anthropic vive en Cortex o ARCA corre su propio CFO
- [ ] Open banking: Belvo o Syncfy, o sólo estados de cuenta en el MVP
- [ ] Canal de alertas al dueño: correo en el MVP, WhatsApp después
- [ ] Motor fiscal de nómina en HRFlow: construir o integrar un proveedor
- [ ] Modelo comercial del despacho: precio por empresa y quién factura a quién
- [ ] Descarga masiva del SAT con e.firma dentro del MVP o sólo carga de XML

**Cómo se mide el MVP.** Tres empresas reales llevadas por Asecofim en ARCA durante un mes completo: cierre mensual con cédula coincidente, paquete NIF entregado, CFDI emitidos y recibidos dentro, banco conciliado, nómina contabilizada y el dueño leyendo su correo del lunes.
