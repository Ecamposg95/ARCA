# ADR-004 — Dinero como Decimal / Numeric(14,2)

**Fecha:** 2026-08-24 · **Estado:** aceptada

## Contexto

Task pack §33: nunca float para montos; rechazar NaN/Infinity/negativos.

## Decisión

- BD: `Numeric(14, 2)`. Python: `Decimal` cuantizado a 2 decimales (`_quantize` en engine.py) antes de sumar o persistir.
- Schemas Pydantic: `Decimal = Field(gt=0, allow_inf_nan=False)`; el frontend envía montos como string.
- MXN por default; el modelo lleva `currency` (String 3) para el futuro, sin FX en el MVP (§34).

## Consecuencias

- Redondeo por línea antes de sumar (regla Atlas) — UI y ledger coinciden centavo a centavo.
- FastAPI serializa Decimal en respuestas dict como número JSON; el frontend formatea con Intl es-MX y no re-calcula nada crítico.
