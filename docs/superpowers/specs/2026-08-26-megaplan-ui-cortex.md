# Mega Plan — pulido UI/UX + integración Atlas Cortex

> Versión de trabajo del plan publicado como artifact ("Mega Plan ARCA").
> Tesis: **Cortex es el cerebro; ARCA es el libro.** El CFO digital de Cortex
> (`app/agents/executives.py`, hoy simulación determinista, color `#3caab0`)
> espera exactamente los datos que ARCA ya publica por `/api/agent/*`.

## Criterio de look & feel (vara para revisar cada pantalla)

1. Una casa, dos acentos: neutrales y tipografías compartidas (Plus Jakarta +
   JetBrains Mono); ARCA teal `#2c9aa6`, Cortex noir. No se mezclan.
2. Cifras `.figures` tabulares; el signo sigue a la naturaleza del instrumento.
3. Densidad LayerZero: granularidad, rangos, tooltips con desglose.
4. Nada de estética de consumo (tarjetas ilustradas, avatares, donas, logos).
5. Toda pantalla mira hacia adelante, no sólo hacia atrás.
6. Semántica pos/warn/neg separada del acento.
7. Español de dueño arriba; contabilidad formal a un clic ("Póliza").
8. Toda vista filtrada comparte URL.
9. Vacíos que invitan; errores que explican; avisos que no bloquean.
10. Motion sobrio; charts sin animación; tap targets 44px en pointer coarse.

## Olas de UI (repo ARCA)

- **U-1 · Gráficas y comparación** (bajo): tooltip con desglose por categoría;
  granularidad Día/Semana/Mes; rango personalizado + comparación vs periodo
  anterior en Reportes con delta chips; sobregiro en rojo con aviso; DSO
  estrella en Cartera ("Te pagan en N días · ▼2 vs mes pasado").
- **U-2 · Maestro-detalle** (medio): libro diario lista+póliza sin modal con
  navegación ↑↓; cartera con historial de cobros y pólizas al costado; detalle
  de cuenta con movimientos filtrados y **"Pagar la tarjeta"** (traspaso
  banco→tarjeta); panel deslizante en angosto.
- **U-3 · Tablas pro** (medio): orden por columna en URL; selección múltiple y
  acciones en lote (marcar pagadas, asignar proyecto, exportar selección);
  filtros con contador y chips removibles; deducibilidad filtrable.
- **U-4 · Cromo y rendimiento** (continuo): paleta de comandos ⌘K; división del
  bundle (719 KB → <300 KB inicial, recharts aparte); pase oscuro+móvil;
  onboarding con momento wow ("tu contabilidad ya existe").

## Fases Cortex

- **C-1 · El CFO ve ARCA** (repo atlas-cortex, sólo lectura):
  `app/services/arca_client.py` → `{ARCA_URL}/api/agent/*` con llave `ak_`
  cifrada por organización; `_brief_finance()` consume dashboard_summary,
  aging, cash-projection, net-worth; `simulated: False`; card "Conectar ARCA"
  en settings. En ARCA: cero código.
- **C-2 · El CFO propone** (ambos): en Cortex `arca_toolset()` dinámico desde
  `GET /agent/tools` (patrón del MCP: el catálogo lo dicta ARCA), gateado por
  Action nueva `USE_ARCA`; en ARCA `GET /agent/proposals/{id}` para polling de
  estado; llave nombrada "Atlas Cortex · CFO" visible en la bandeja.
- **C-3 · Demo integrado**: misión "revisa la cartera y recupera lo vencido" →
  CFO lee aging (Retail Vega $52,200 vencida) → propuesta en ARCA → aprobación
  humana → póliza. Plan B por capas: Cortex → Claude Code/MCP → demo_plan_b.py.

## Secuencia

U-1 → C-1 → U-2 → C-2 → U-3 → C-3 → U-4 (continuo).

## Riesgos

- Llave ak_ en Cortex: cifrada, nunca en logs, permiso mínimo, rotación en ARCA.
- Deriva de catálogo: descubrimiento al arrancar + prueba de contrato en CI.
- Bundle: dividir rutas antes de que U-2/U-3 sumen peso.
- Dos deploys: el plan B por capas es entregable de C-3, no un extra.

## No vamos a hacer

Rediseñar Cortex desde ARCA · webhooks/bus entre productos (polling basta) ·
SSO compartido · estética de consumo · que Cortex escriba directo en ARCA
(la aprobación humana en ARCA es el producto).
