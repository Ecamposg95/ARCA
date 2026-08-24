# ADR-002 — Primary keys UUID (String 36)

**Fecha:** 2026-08-24 · **Estado:** aceptada

## Contexto

Los repos Atlas más maduros usan PKs enteros en la mayoría de tablas; el ADF y el task pack (§4 "IDs UUID") piden UUID. Para una plataforma financiera multi-tenant, los UUID evitan enumeración de recursos y facilitan integraciones externas (Atlas ONE) sin coordinación de secuencias.

## Decisión

`String(36)` con `uuid4` generado en aplicación (`UUIDPKMixin`) en TODAS las tablas.

## Consecuencias

- Los tests de aislamiento cross-tenant validan por UUID conocido (no basta adivinar IDs).
- Índices algo más grandes que enteros: aceptable a esta escala; si duele, migrar a UUIDv7 para localidad.
