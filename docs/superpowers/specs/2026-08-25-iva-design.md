# ARCA — IVA e impuestos (diseño aprobado)

**Fecha:** 2026-08-25 · **Estado:** aprobado por Emmanuel · **Decisión previa:** las operaciones históricas se asumen **sin IVA** (tasa 0).

## El problema que resuelve

Hoy un gasto de $1,160 se registra completo como gasto. En realidad son $1,000 de gasto y $160 de IVA que el negocio puede acreditar. Sin ese desglose, el Estado de Resultados infla gastos e ingresos, y no hay forma de saber cuánto IVA se debe o se tiene a favor.

## La decisión que define el diseño: IVA por flujo de efectivo

En México el IVA se causa **cuando se cobra o se paga**, no cuando se factura (LIVA art. 1-B). ARCA ya distingue devengo (CxC/CxP emitidas) de efectivo (cobros/pagos), así que el modelo lo respeta con cuatro cuentas en vez de dos:

| Código | Cuenta | Tipo | Cuándo |
|---|---|---|---|
| 1190 | IVA acreditable pagado | ASSET | Se pagó al proveedor → **se declara** |
| 1191 | IVA acreditable pendiente de pago | ASSET | CxP emitida, aún no pagada |
| 2190 | IVA trasladado cobrado | LIABILITY | Se cobró al cliente → **se declara** |
| 2191 | IVA trasladado pendiente de cobro | LIABILITY | CxC emitida, aún no cobrada |

Sin las cuentas "pendientes" el ledger quedaría incorrecto: una CxC de $116,000 registraría $116,000 de ingreso en vez de $100,000 + $16,000 de IVA.

## Modelo de datos

Cada operación (`incomes`, `expenses`, `receivables`, `payables`) suma:

- `subtotal` Numeric(14,2) — base gravable
- `tax_rate` Numeric(5,4) — 0.1600 / 0.0800 / 0.0000
- `tax_amount` Numeric(14,2) — impuesto

`amount` **sigue siendo el total** (lo que se mueve en efectivo): no se toca su semántica ni el código que ya depende de ella.

`organizations.default_tax_rate` Numeric(5,4) default 0.1600: la tasa que propone el formulario. Un negocio exento la pone en 0 una vez y deja de pelear con el formulario.

### Cálculo y redondeo

El usuario captura el **total** (lo que dice el ticket) y elige la tasa. ARCA desglosa:

```
subtotal = redondear(total / (1 + tasa), 2)
impuesto = total − subtotal          ← por diferencia, nunca recalculado
```

El impuesto se obtiene por diferencia para garantizar `subtotal + impuesto == total` exacto. Recalcularlo introduciría centavos de deriva que romperían la partida doble.

## Reglas contables (todas en `rules.py`)

| Evento | Cargo | Abono |
|---|---|---|
| Ingreso cobrado | 1100 total | ingreso subtotal + **2190** impuesto |
| Gasto pagado | gasto subtotal + **1190** impuesto | 1100 total |
| CxC emitida | 1200 total | ingreso subtotal + **2191** impuesto |
| Cobro de CxC | 1100 cobrado + **2191** impuesto proporcional | 1200 cobrado + **2190** impuesto proporcional |
| CxP emitida | gasto subtotal + **1191** impuesto | 2100 total |
| Pago de CxP | 2100 pagado + **1190** impuesto proporcional | 1100 pagado + **1191** impuesto proporcional |

**Cobros y pagos parciales:** el impuesto se traslada en proporción a lo cobrado (`impuesto_total × cobrado / total`), redondeado a 2 decimales. El último cobro liquida el remanente exacto para que 2191 quede en cero sin residuos de centavos.

Con tasa 0 las líneas de impuesto no se emiten: los asientos quedan idénticos a los de hoy, y las operaciones históricas siguen cuadrando.

## Reporte de IVA

`GET /api/reports/iva?start&end`:

- **IVA trasladado (cobrado)** — movimientos de 2190 en el periodo
- **IVA acreditable (pagado)** — movimientos de 1190 en el periodo
- **Diferencia** — a pagar si es positiva, a favor si es negativa
- **Pendientes** — saldos de 2191 y 1191, informativos: aún no se declaran

Nueva pestaña "IVA" en Reportes. No se emite ni se envía nada al SAT (task pack §35): esto prepara el terreno, no lo integra.

## Migración `20260825_02`

1. Agrega las seis columnas (`subtotal`, `tax_rate`, `tax_amount` × 4 tablas) como nullable y `organizations.default_tax_rate`.
2. Respalda: `subtotal = amount`, `tax_rate = 0`, `tax_amount = 0` — **decisión de Emmanuel: lo histórico va sin IVA**.
3. Las vuelve NOT NULL.
4. Siembra las cuatro cuentas nuevas en el catálogo de **cada organización existente**, respetando su jerarquía (1190/1191 bajo 1000, 2190/2191 bajo 2000).

## Tests

Desglose exacto (1160 al 16% → 1000 + 160, y que sumen el total); ingreso cobrado con IVA abona 2190; gasto pagado carga 1190; CxC emitida usa 2191 y al cobrarse lo mueve a 2190; proporcionalidad en cobro parcial; el último cobro deja 2191 en cero; tasa 0 produce el asiento de hoy; reporte de IVA cuadra con la balanza; y el aislamiento por organización se mantiene.

## Fuera de alcance

Retenciones (IVA/ISR retenido), IEPS, tasa 8% de frontera como configuración regional automática, declaración o timbrado ante el SAT, complementos de pago.
