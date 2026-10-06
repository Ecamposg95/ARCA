# Contabilidad electrónica SAT (Anexo 24) — catálogo y balanza en XML

> Sub-proyecto A del frente "cumplimiento" (A contabilidad electrónica, B
> estados financieros NIF, C contabilidad completa, D régimen fiscal y
> obligaciones, E importar CFDI, F cédula de impuestos). Aprobado en
> conversación el 2026-10-06.

## Para qué

Cada mes, el contador entrega al SAT la contabilidad electrónica de cada
cliente: el catálogo de cuentas con su código agrupador y la balanza de
comprobación, en XML, sellados con la e.firma. Hoy eso lo arma desde su
sistema; si el cliente lleva ARCA, ARCA debe producirlo.

**Éxito:** para una empresa con RFC capturado, el contador descarga del mes
que elija el catálogo y la balanza en XML válidos contra los esquemas
oficiales 1.3, con los totales idénticos a la balanza de ARCA, y los sella y
envía con su herramienta de siempre.

## Lo que se sabe

- Esquemas oficiales descargados del SAT (`CatalogoCuentas_1_3.xsd`,
  `BalanzaComprobacion_1_3.xsd`, `CatalogosParaEsqContE.xsd`), que viven en
  `tests/fixtures/sat/` y gobiernan las pruebas.
- El catálogo oficial de códigos agrupadores tiene 1,080 códigos (enumeración
  `c_CodAgrup` del esquema). Los nombres salen del Anexo 24 publicado en el
  DOF (5 de enero de 2015); cinco códigos no tienen nombre en el PDF y se
  dejan con su código.
- Catálogo: raíz `Catalogo` (Version 1.3, RFC, Mes `01`-`12`, Anio ≥ 2015) con
  `Ctas` (CodAgrup, NumCta ≤ 100, Desc ≤ 400, SubCtaDe opcional, Nivel ≥ 1,
  Natur `D`|`A`).
- Balanza: raíz `Balanza` (Version, RFC, Mes `01`-`13`, Anio, TipoEnvio `N`|`C`,
  FechaModBal obligatoria en la práctica cuando es `C`) con `Ctas` (NumCta,
  SaldoIni, Debe, Haber, SaldoFin con dos decimales).
- Nombres de archivo según el Anexo 24: `{RFC}{AAAA}{MM}CT.xml` para el
  catálogo y `{RFC}{AAAA}{MM}B{N|C}.xml` para la balanza.
- El sello (`Sello`, `noCertificado`, `Certificado`) es opcional en el esquema
  y lo pone la herramienta del contador con la e.firma. ARCA entrega los XML
  **sin sellar** y lo dice en pantalla.

## Diseño

### Código agrupador por cuenta

- Columna nueva `accounts.sat_code` (`String(10)`, nullable). Migración
  `20261006_01_codigo_agrupador.py`, aditiva, que además rellena los defaults
  en las cuentas que ARCA sembró (`system = true`) y aún no tienen código.
- Las empresas nuevas nacen con los defaults (el sembrado del catálogo los
  asigna).
- Defaults del catálogo de ARCA (todos existen en la enumeración oficial):

| ARCA | Código agrupador |
|---|---|
| 1000 Activo | 100 |
| 1100 Caja y Bancos | 102.01 Bancos nacionales |
| 1190 IVA acreditable pagado | 118.01 |
| 1191 IVA acreditable pendiente de pago | 119.01 IVA pendiente de pago |
| 1200 Cuentas por Cobrar | 105.01 Clientes nacionales |
| 1300 Otros Activos | 121.01 Otros activos a corto plazo |
| 1400 Activo Fijo | 160.01 Otros activos fijos |
| 1490 Depreciación Acumulada | 171.08 Depreciación acumulada de otros activos fijos |
| 2000 Pasivo | 200 |
| 2100 Cuentas por Pagar | 201.01 Proveedores nacionales |
| 2190 IVA trasladado cobrado | 208.01 |
| 2191 IVA trasladado pendiente de cobro | 209.01 IVA trasladado no cobrado |
| 2200 Tarjetas de crédito | 205.06 Otros acreedores diversos a corto plazo |
| 2300 Préstamos por Pagar | 202.01 Documentos por pagar bancario y financiero nacional |
| 2400 ISR Retenido por Enterar | 216.04 Impuestos retenidos de ISR por servicios profesionales |
| 2410 IVA Retenido por Enterar | 216.10 Impuestos retenidos de IVA |
| 3000 Capital | 300 |
| 3100 Capital | 301.01 Capital fijo |
| 3200 Resultados Acumulados | 304.01 Utilidad de ejercicios anteriores |
| 4000 Ingresos | 400 |
| 4100 Ventas, 4200 Servicios | 401.01 Ventas y/o servicios gravados a la tasa general |
| 5000 Gastos | 600 |
| 5100 Gastos Operativos, 5700 Otros Gastos | 601.84 Otros gastos generales |
| 5200 Nómina | 601.01 Sueldos y salarios |
| 5300 Renta | 601.46 Arrendamiento a personas morales residentes nacionales |
| 5400 Software | 601.60 Cuotas y suscripciones |
| 5500 Marketing | 601.61 Propaganda y publicidad |
| 5600 Transporte | 601.72 Fletes y acarreos |
| 5800 Depreciación | 613.08 Depreciación de otros activos fijos |
| 5900 Intereses | 701.04 Intereses a cargo bancario nacional |

  Son defaults razonables para una pyme; el contador los corrige cuenta por
  cuenta (renta a persona física es 601.45, un préstamo a largo plazo 252.01).

- `GET /api/accounting/sat/codes` → la lista oficial `[{code, name}]`.
- `PATCH /api/accounting/accounts/{id}` acepta también `sat_code`: debe existir
  en la lista oficial (400 si no) o ser vacío para quitarlo. Sólo cambia los
  campos que vienen en el cuerpo.
- En Contabilidad → Catálogo, columna "Código SAT" con selector con búsqueda
  por código o nombre, en todas las cuentas (padres incluidos: el catálogo del
  SAT lleva todos los niveles).

### Naturaleza

`D` para activo y gastos, `A` para pasivo, capital e ingresos. Excepción
declarada: `1490 Depreciación Acumulada` es un contra-activo y va con `A`
(lista `CONTRA_ACCOUNT_CODES` en el módulo; una sola entrada hoy).

### Catálogo XML

`GET /api/accounting/sat/catalogo?year&month`

- Incluye todas las cuentas activas de la empresa. Nivel 1 las que no tienen
  padre, nivel 2 las hijas; `SubCtaDe` con el código ARCA del padre.
- `Desc` recortada a 400; `NumCta` es el código ARCA.
- Antes de generar se exige: RFC con formato válido y código agrupador en
  todas las cuentas que entran. Si falta algo → 400 con
  `{"detail": "...", "missing": {"rfc": bool, "accounts": [{id, code, name}]}}`.

### Balanza XML

`GET /api/accounting/sat/balanza?year&month&tipo=N|C`

- Por cuenta: `SaldoIni` (saldo al cierre del mes anterior), `Debe` y `Haber`
  (movimientos del mes), `SaldoFin`. **Cierre anual virtual:** ARCA no cierra el
  ejercicio, así que ingresos y gastos sólo arrastran saldo desde el 1 de enero
  del año pedido y el resultado neto de los años anteriores abre en `3200
  Resultados Acumulados`. Así enero no muestra las ventas de años pasados como
  saldo inicial, que es lo que el SAT cruza contra la declaración anual. Los saldos van en la naturaleza de la
  cuenta: para `D`, `SaldoFin = SaldoIni + Debe − Haber`; para `A`,
  `SaldoFin = SaldoIni − Debe + Haber`. Un saldo contrario a la naturaleza sale
  negativo.
- Las cuentas padre llevan la suma de sus hijas. Entran las cuentas con algún
  valor distinto de cero y sus padres.
- Totales: suma de Debe = suma de Haber del mes, y coinciden con la balanza de
  ARCA del mismo periodo. Si no cuadran, 409 y no se entrega el archivo.
- `tipo=C` (complementaria) agrega `FechaModBal` con la fecha de hoy.
- Mismas exigencias previas que el catálogo (RFC y códigos de las cuentas que
  entran).

### Vista previa

`GET /api/accounting/sat/preview?year&month` → `{rfc, rfc_ok, accounts,
missing_accounts: [{id, code, name}], ready}`.

### Interfaz

En Contabilidad → Cierre de periodo, junto al botón CONTPAQi, botón **SAT** por
mes. El modal muestra RFC, cuántas cuentas entran, las que no tienen código
agrupador (con enlace al catálogo) y dos descargas: "Catálogo XML" y "Balanza
XML" (normal; la complementaria se pide desde el API). Aviso fijo: los
archivos salen sin sellar; el sello y el envío al buzón los hace el contador
con su herramienta.

### Código

- `app/services/accounting/sat.py`: lista oficial (desde
  `app/services/accounting/sat_codes.json`), defaults, naturaleza, y los dos
  generadores puros `render_catalogo(...)` y `render_balanza(...)` que
  reciben datos ya calculados y devuelven bytes UTF-8.
- Cálculo de saldos y movimientos por cuenta en
  `app/domains/accounting/service.py`.
- Endpoints en `app/domains/accounting/router.py`.
- `xmlschema` como dependencia de desarrollo para validar en pruebas contra
  los XSD locales.

## Pruebas

- Catálogo y balanza válidos contra los XSD oficiales (fixtures locales).
- Balanza: cada cuenta cumple su ecuación por naturaleza; totales Debe =
  Haber; coinciden con `/api/accounting/trial-balance`; el padre suma a las
  hijas; un saldo inicial viene de meses anteriores.
- Catálogo: niveles, `SubCtaDe`, naturaleza, 1490 con `A`, descripción larga
  recortada, códigos agrupadores de la lista.
- Defaults: una empresa nueva nace con `sat_code` en todas sus cuentas; la
  migración rellena las existentes sólo donde falta.
- PATCH: código válido se guarda; inválido 400; vacío lo quita; no toca
  `contpaqi_code` si no viene.
- Sin RFC o RFC inválido → 400 con `missing.rfc`; cuenta sin código → 400 con
  la lista; sólo la empresa activa; 403 a roles sin contabilidad; nombres de
  archivo según el Anexo 24.

## Fuera de alcance

- Pólizas XML y auxiliares (necesitan UUID de CFDI → sub-proyecto E).
- Sello con e.firma, empaquetado `.zip` y envío al buzón tributario.
- Cuentas de más de dos niveles (ARCA no las tiene).
- Importar el catálogo de códigos agrupadores desde otro sistema.
