# LaFe — Historias de usuario y backlog financiero

_Fuente: análisis de la transcripción con Laboratorios La Fe, entregado por Emmanuel el 2026-11-02. Estado: propuesta inicial para refinamiento y validación. La comparación contra la plataforma (HAB-01) vive en `HAB-01_matriz.md`._

## 1. Objetivo

Construir una única fuente de información financiera para:

- Conocer saldos de efectivo y cuentas bancarias.
- Identificar el origen y destino del dinero.
- Controlar gastos y autorizaciones.
- Conciliar ventas, cobros, depósitos y comisiones.
- Anticipar compromisos de pago.
- Consultar resultados financieros durante el mes.

Alcance inicial: operación financiera y administrativa. No contempla reemplazar Toronja ni desarrollar funciones clínicas.

## 2. Usuarios

| Perfil | Usuario previsto | Funciones |
|---|---|---|
| Dirección / autorizador superior | Liza | Consulta y operación financiera; autorización de movimientos superiores al umbral acordado |
| Administración | Abraham | Registro, conciliación, programación de pagos y consulta financiera |
| Auxiliar administrativo | Por definir | Captura y operación restringidas por permisos y montos |

Regla propuesta: Liza y Abraham tienen la misma visibilidad y capacidad operativa. La diferencia principal es la autorización de determinados movimientos. Las restricciones del auxiliar deben validarse.

## 3. Prioridades

- **P0:** indispensable para operar con control.
- **P1:** siguiente entrega para completar conciliación, planeación y resultados.
- **P2:** evolución y automatización.

Las prioridades no representan fechas ni estimaciones de esfuerzo.

## 4. Historias de usuario

### Épica A · Accesos y estructura financiera

**HU-01 · Accesos y permisos — P0.** Como responsable de LaFe, quiero accesos individuales con permisos por perfil, para delegar sin perder control.
- Existen los tres perfiles definidos.
- Liza y Abraham consultan la misma información.
- El auxiliar solo ejecuta acciones autorizadas.
- Los permisos protegen consulta, captura, modificación y autorización.

**HU-02 · Catálogos financieros — P0.** Como administrador, quiero configurar sucursales, cajas, cuentas y categorías, para registrar movimientos de forma uniforme.
- Se distinguen ingresos de mostrador, empresas, rentas y otras fuentes.
- Los egresos se clasifican en categorías validadas.
- Préstamos, inversiones y traspasos se distinguen de ingresos y gastos operativos.
- Desactivar una categoría no elimina su historial.

**HU-03 · Saldos iniciales — P0.** Como administrador, quiero registrar saldos de arranque por caja y cuenta, para consultar disponibilidades correctas.
- Cada saldo tiene importe, fecha de corte y responsable.
- El saldo actual se explica mediante saldo inicial y movimientos posteriores.
- La carga histórica no duplica importes incluidos en el saldo de arranque.

### Épica B · Operación y trazabilidad

**HU-04 · Registro de ingresos — P0.** Como administrador, quiero registrar ingresos de todas las fuentes, para conocer su origen y recepción.
- Se registra fecha, importe, fuente, categoría, medio de pago y sucursal cuando corresponda.
- Se identifica la caja o cuenta receptora.
- Se distingue cobro recibido de cobro pendiente de recepción.
- Se conserva una referencia de origen cuando exista.

**HU-05 · Registro de egresos — P0.** Como operador autorizado, quiero registrar gastos con motivo y responsable, para saber quién gastó, cuánto y para qué.
- Se captura importe, fecha, categoría, concepto, beneficiario y origen del dinero.
- Se identifica al usuario que registra.
- Se permite adjuntar soporte documental.
- Se aplican las reglas de autorización correspondientes.

**HU-06 · Traspasos internos — P0.** Como administrador, quiero registrar transferencias entre cajas y cuentas, para mantener trazabilidad sin duplicar ingresos o gastos.
- Se registra origen, destino, importe, fecha y responsable.
- La salida y la entrada quedan vinculadas.
- El traspaso no incrementa ingresos ni gastos.
- Se permite confirmar la recepción cuando el traslado no sea inmediato.

**HU-07 · Apertura, corte y entrega de efectivo — P0.** Como responsable de caja, quiero registrar el corte y la entrega del efectivo, para detectar diferencias por sucursal.
- Se registra apertura, movimientos y efectivo contado al cierre.
- Se compara efectivo esperado contra contado.
- Las diferencias requieren explicación.
- La entrega a matriz identifica quién entrega, quién recibe y el importe recibido.

**HU-08 · Autorizaciones por monto — P0.** Como autorizador superior, quiero configurar límites por perfil, para permitir gastos menores y controlar movimientos relevantes.
- Los umbrales son configurables.
- Las operaciones que requieren aprobación quedan pendientes.
- Solo el perfil autorizado puede aprobar o rechazar.
- Se conserva decisión, responsable, fecha y motivo de rechazo.
- Una operación pendiente no se presenta como pagada.

Por validar: si la aprobación controla el pago o documenta una autorización previa a un pago externo.

**HU-09 · Historial de cambios — P0.** Como responsable de LaFe, quiero consultar el historial de los movimientos, para revisar correcciones y conservar trazabilidad.
- Se registra quién creó, modificó, autorizó o canceló.
- Se conservan los valores anteriores.
- Las cancelaciones requieren motivo.
- No se elimina silenciosamente una operación que afectó saldos.

### Épica C · Carga y consulta

**HU-10 · Importación de Excel y CSV — P0.** Como administrador, quiero importar archivos, para comenzar sin recapturar toda la información ni esperar integraciones.
- Se pueden mapear columnas a los campos del sistema.
- Se presenta una vista previa.
- Se identifican errores y posibles duplicados.
- Se informa qué filas se cargaron y cuáles requieren corrección.
- Reimportar un archivo no genera duplicados inadvertidos.

**HU-11 · Consulta y exportación — P0.** Como usuario autorizado, quiero filtrar y exportar movimientos, para revisar la operación y compartir información.
- Hay filtros por periodo, sucursal, cuenta, categoría, responsable, medio de pago y estado.
- Los totales corresponden a los filtros aplicados.
- Se exporta a Excel o CSV.
- La exportación respeta permisos.

**HU-12 · Carga de movimientos bancarios — P1.** Como administrador, quiero cargar estados de cuenta o movimientos diarios, para conciliarlos sin transcribir cada operación.
- Se identifica cuenta, periodo y archivo de origen.
- Se obtiene fecha, descripción, referencia e importe.
- Se revisa la información antes de confirmar.
- Se detectan posibles duplicados entre cargas.

Alcance inicial: formatos estructurados acordados. La lectura de PDF o imágenes requiere evaluar muestras reales.

### Épica D · Conciliación

**HU-13 · Conciliación de cobros y depósitos — P1.** Como administrador, quiero comparar ventas y cobros con movimientos bancarios, para verificar que el dinero se recibió.
- Se contemplan transferencias, NetPay y Mercado Pago.
- Se proponen coincidencias por importe, fecha y referencia.
- El usuario confirma o rechaza coincidencias.
- Se identifican pendientes, conciliados y diferencias.
- Se contempla que un depósito liquide varias ventas, según la información del proveedor.

**HU-14 · Cobros pendientes de recepción — P0.** Como administrador, quiero visualizar cobros aún no depositados, para distinguir venta registrada de dinero disponible.
- Se muestra importe, origen y fecha de operación.
- La fecha de venta se conserva separada de la fecha de depósito.
- La recepción actualiza el estado.
- El mismo cobro no incrementa dos veces el saldo disponible.

**HU-15 · Validación de comisiones — P1.** Como administrador, quiero comparar las comisiones cobradas contra las pactadas, para detectar descuentos incorrectos.
- Se configuran tasas y condiciones por proveedor y vigencia.
- Se compara importe bruto, comisión esperada y depósito neto.
- Se contemplan impuestos y cargos según el contrato.
- Las diferencias quedan disponibles para revisión.

### Épica E · Compromisos y cobranza

**HU-16 · Cuentas por pagar — P1.** Como administrador, quiero registrar obligaciones y pagos recurrentes, para controlar vencimientos.
- Cada obligación tiene beneficiario, concepto, importe y vencimiento.
- Se programan rentas, impuestos, créditos y otros compromisos.
- Se distinguen pendientes, pagos parciales, pagadas y canceladas.
- Registrar un pago actualiza la obligación sin duplicar el egreso.

**HU-17 · Planeación semanal — P1.** Como responsable de LaFe, quiero consultar los compromisos de la semana, para anticipar necesidades de efectivo.
- Se muestran compromisos semanales y vencidos.
- Se compara el total comprometido con la disponibilidad registrada.
- Se identifican faltantes potenciales.
- Se define si el resumen del lunes será una vista, una notificación o ambos.

**HU-18 · Cuentas por cobrar — P1.** Como administrador, quiero registrar adeudos y abonos de clientes, para saber quién debe y cuánto falta por cobrar.
- Se registra cliente, concepto, importe y vencimiento.
- Se permiten abonos parciales.
- Se muestra saldo pendiente y antigüedad.
- Cada cobro se vincula al ingreso correspondiente sin duplicarlo.

### Épica F · Visibilidad financiera

**HU-19 · Tablero de disponibilidad — P0.** Como responsable de LaFe, quiero consultar saldos por caja y cuenta, para saber cuánto dinero puedo utilizar.
- Se muestran saldos individuales y consolidados.
- Se separa disponibilidad de cobros pendientes.
- Cada saldo permite consultar sus movimientos.
- Se muestra la última actualización.

**HU-20 · Estado de resultados — P1.** Como responsable de LaFe, quiero consultar resultados y distribución del gasto por periodo, para decidir antes del cierre mensual.
- Se muestran ingresos, costos, gastos y resultado conforme a la estructura validada.
- Cada rubro permite consultar sus movimientos.
- Se muestra importe y porcentaje por categoría de gasto.
- Préstamos, inversiones y traspasos reciben el tratamiento acordado.
- Se indica fecha de corte e información pendiente de integrar.

Dependencia: validar criterio contable y estructura con el responsable de contabilidad.

### Épica G · Evolución

**HU-21 · Integraciones automáticas — P2.** Como administrador, quiero sincronizar ventas y liquidaciones, para reducir cargas manuales y errores.
- Se evalúan por separado Toronja, NetPay y Mercado Pago.
- Cada registro conserva su identificador de origen.
- La sincronización evita duplicados e informa errores.
- Se mantiene la carga manual o por archivo como alternativa.

Dependencias: accesos autorizados, documentación y disponibilidad técnica de cada proveedor. Refinamiento: dividir por proveedor antes de estimar.

**HU-22 · Proyección de flujo de caja — P2.** Como dirección, quiero proyectar entradas y salidas, para anticipar necesidades futuras de dinero.
- La proyección considera disponibilidad, cuentas por cobrar y compromisos.
- Distingue datos registrados de supuestos.
- Permite consultar el origen de los importes.
- No presenta cobros previstos como dinero disponible.

## 5. Backlog de implementación

| Orden | Entrega | Historias o trabajo | Resultado |
|---|---|---|---|
| 1 | Descubrimiento | Revisar plataforma, archivos, reglas y saldos | Identificar qué existe y qué falta |
| 2 | Base financiera | HU-01, HU-02, HU-03 y base de HU-09 | Accesos, catálogos y saldos iniciales |
| 3 | Operación diaria | HU-04 a HU-08 | Registro y control de movimientos y efectivo |
| 4 | MVP operativo | HU-10, HU-11, HU-14, HU-19 y cierre de HU-09 | Operación centralizada sin depender de APIs |
| 5 | Conciliación | HU-12, HU-13, HU-15 | Depósitos vinculados y diferencias visibles |
| 6 | Planeación y cobranza | HU-16, HU-17, HU-18 | Vencimientos, compromisos y adeudos controlados |
| 7 | Resultados | HU-20 | Consulta de resultados y composición del gasto |
| 8 | Automatización | HU-21, HU-22 | Menor captura manual y proyección de liquidez |

MVP recomendado: entregas 1 a 4, probadas con datos reales. La conciliación debe continuar inmediatamente después, apoyada en registros y fuentes confiables.

## 6. Tareas habilitadoras

| ID | Tarea | Entregable |
|---|---|---|
| HAB-01 | Comparar plataforma actual contra backlog | Matriz: disponible, parcial, faltante y por probar |
| HAB-02 | Recopilar Excel, cortes y muestras bancarias | Inventario de formatos |
| HAB-03 | Definir movimientos, estados y reglas de saldo | Diccionario de datos |
| HAB-04 | Validar categorías y tratamiento contable | Catálogo aprobado |
| HAB-05 | Confirmar permisos y límites | Matriz de autorizaciones |
| HAB-06 | Definir arranque y carga histórica | Plan de migración |
| HAB-07 | Evaluar integraciones | Viabilidad y alternativa por archivo |
| HAB-08 | Preparar pruebas con usuarios | Casos de aceptación y resultados |

## 7. Decisiones pendientes

1. **Autorizaciones:** confirmar el umbral mencionado de movimientos mayores a $100,000, moneda, tratamiento de exactamente $100,000 y operaciones sujetas a aprobación. El monto de $2,000 para el auxiliar fue un ejemplo, no una regla aprobada.
2. **Permisos:** confirmar restricciones del auxiliar y facultades de configuración.
3. **Contabilidad:** definir reconocimiento por cobro/pago o devengo, impuestos y tratamiento de inversiones y préstamos.
4. **Conciliación:** confirmar cuentas, referencias, depósitos agrupados y tiempos de liquidación.
5. **Migración:** acordar fecha inicial, alcance histórico y responsable de validar saldos.
6. **Excepciones:** definir devoluciones, contracargos, cancelaciones y correcciones.
7. **Alertas:** acordar canal, destinatarios y frecuencia.

## 8. Condiciones para considerar terminada una historia

- Cumple sus criterios de aceptación.
- Respeta permisos y conserva trazabilidad.
- No genera duplicidades ni descuadres.
- Se prueba con datos representativos de LaFe.
- El usuario responsable valida el resultado.
- Las funciones que afectan saldos permiten explicar su cálculo.
- Antes del uso productivo se definen respaldo y recuperación.

## 9. Fuera del MVP, pendiente de refinamiento

- CRM comercial y segmentación de clientes.
- Presupuesto y seguimiento por proyecto.
- Lectura de XML de facturas.
- Extracción con IA desde documentos no estructurados.
- Agentes para análisis y sugerencias de priorización de pagos.
- Conexión bancaria directa.
- Balance general, sujeto a definir activos, pasivos, patrimonio y saldos contables.

La mención de estas capacidades durante la demostración no equivale a aprobación para el primer lanzamiento.
