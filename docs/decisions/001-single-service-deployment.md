# ADR-001 — Deployment de servicio único

**Fecha:** 2026-08-24 · **Estado:** aceptada

## Contexto

El task pack §42 sugería tres servicios Railway (PostgreSQL, API, Web). La convención Atlas canon (Atlas-Rmazh, atlas-cortex, dasic-atlas-api) es un servicio único donde FastAPI sirve la SPA construida, y el task pack §6 ordena priorizar consistencia con Atlas.

## Decisión

Dos servicios Railway: PostgreSQL + `arca` (FastAPI que sirve `/api/*` y `frontend/dist` vía catch-all registrado al final).

## Consecuencias

- Sin CORS entre front y API (misma origen), sin dominio extra, deploy más simple.
- El build construye ambos (Railpack: Python + Node).
- Si algún día el frontend necesita CDN/edge propio, se separa; `CORS_ORIGINS` ya existe para ese caso.
