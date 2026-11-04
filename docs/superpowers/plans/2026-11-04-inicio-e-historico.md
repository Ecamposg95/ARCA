# Inicio "Tablero del día" e histórico de análisis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cargar el histórico de los Excel de La Fe como capa de análisis separada de la contabilidad y rehacer Inicio como "Tablero del día" (dinero hoy, pagos de la semana, sucursales, ventas por mes).

**Architecture:** Un dominio nuevo `app/domains/analytics/` con dos tablas (`historical_loads`, `historical_points`), cargadores puros por fuente que devuelven puntos agregados, un servicio que reemplaza por rango y un endpoint de series que une histórico (antes de `opening_date`) con vivo (desde las operaciones). Inicio consume un endpoint nuevo `GET /api/dashboard/today` (paneles) y `GET /api/analytics/series` (gráfica de ventas); el front se rehace en `features/dashboard/` con componentes por panel y tokens globales nuevos.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2; openpyxl (ya en requirements, lo usa `tabular.read_xlsx`); React 18 + TS + Tailwind + TanStack Query v5 + recharts 2.

**Spec:** `docs/superpowers/specs/2026-11-03-inicio-e-historico-design.md` (léelo completo; la sección "Definiciones y reglas" manda sobre cualquier ambigüedad de este plan).

## Global Constraints

- Invariantes de `AGENTS.md`: tenant isolation en toda consulta, `Decimal`/`Numeric` para dinero, ningún saldo se toca fuera de `record_transaction`. **El histórico nunca crea pólizas, movimientos ni toca saldos.**
- `CLIENTE` y `ESTUDIOS` de Toronja nunca se persisten ni se loguean; el cargador agrega antes de persistir (reutiliza `app.services.imports.toronja.parse_toronja`, que ya los descarta).
- Migración `alembic/versions/20261103_04_historico.py`, `revision="20261103_04"`, `down_revision="20261103_03"`; un solo head.
- Montos de histórico: `Numeric(16,2)`.
- API: `/api/<dominio>` plural, errores `{"detail": "mensaje en español"}`, schemas Pydantic, nunca ORM crudo.
- `/api/analytics/series` y `/api/dashboard/today`: **todos los roles de la empresa** (incluidos MEMBER y VIEWER) — decisión de Emmanuel 2026-11-04. `POST /api/admin/historical-loads`: sólo OWNER.
- Copy visible: "ONE Finance", nunca "ARCA"; español; empty states con CTA.
- UI: sólo tokens semánticos Tailwind, cero colores crudos (también en recharts: leer los tokens por `var(--color-*)`).
- Tokens nuevos (oscuro): fondo `#0c1210`, panel `#121a17`, elevado `#18221e`, línea `#22302a`, tinta `#e4ece7`/`#a9b8b0`/`#6f8079`, acento `#4cc38a`/`#2a8f63`, ámbar `#e2a54a`, negativo `#e86a5e`. Tipografía Geist 400/500/600 con `tabular-nums` en cifras.
- Movimiento: count-up ≤ 600 ms y crecimiento de barras una sola vez al cargar; nada más; `prefers-reduced-motion` lo apaga.
- Commits Conventional en español. Los archivos crudos de La Fe nunca al repo (`docs/lafe/privado/` y el scratchpad).

## Review Focus

1. **Doble conteo en el mes del corte.** Noviembre 2026 tiene corte el día 1: todo noviembre sale de vivo, octubre y antes de histórico. Si `opening_date` cae a mitad de mes (otra empresa), ese mes se parte: días antes del corte de histórico diario si existe, y desde el corte de vivo — nunca ambos para el mismo día. Test en Task 7.
2. **Proyecciones de PROY tomadas como reales.** PROY trae oct–dic 2026 como proyección (+35 % fijo). Un mes de 2026 de PROY sólo entra si la fila de "NO. PACIENTES" de ese mes y año tiene valor; si está vacía, es proyección y se descarta. Test en Task 3.
3. **Recarga del mismo archivo o de un archivo con más meses.** Recargar Toronja ene–sep dos veces deja el mismo conteo; cargar luego ene–oct reemplaza ene–sep y agrega oct, sin tocar puntos de otras fuentes. Test en Task 1 y Task 2.
4. **Empresa sin corte ni histórico (la demo o una nueva).** `opening_date` nulo → toda la serie es vivo, `historical_available: false`, nada truena; Inicio muestra empty states con CTA, nunca ejes "$0 a $4". Tests en Task 7 y Task 8.
5. **Unidad del Excel que no existe en ONE Finance** ("LAS CUMBRES" cerrada, un vendedor raro). Se guarda con `unit_label`, se reporta en el resumen de la carga, y en Sucursales no aparece como fila (sólo unidades activas). Test en Task 2.

---

## File Structure

**Backend — nuevo dominio `app/domains/analytics/`:**
- `app/models/historical.py` — `HistoricalLoad`, `HistoricalPoint` (registrar en `app/models/__init__.py`).
- `alembic/versions/20261103_04_historico.py`.
- `app/domains/analytics/points.py` — dataclass `Point` y `replace_points()` (reemplazo por rango).
- `app/domains/analytics/loaders/toronja.py` — Toronja → `sales_daily`.
- `app/domains/analytics/loaders/control_general.py` — PROY, RESUTADOS, PRESTAMOS, INVERSIONES.
- `app/domains/analytics/loaders/reconstruccion.py` — 04, 03, 17, 18.
- `app/domains/analytics/loaders/efectivo.py` — Control de Efectivo → `cash_daily`.
- `app/domains/analytics/loading.py` — `load_files()` orquesta cargadores + resolución de unidades/entidades + `replace_points`.
- `app/domains/analytics/series.py` — `series()` (histórico + vivo).
- `app/domains/analytics/schemas.py`, `app/domains/analytics/router.py` (`/analytics`, `/admin/historical-loads`).
- `scripts/lafe_historico.py`.
- `app/domains/dashboard/today.py` — paneles de Inicio; ruta nueva en `app/domains/dashboard/router.py`.

**Tests:** `tests/test_historico_carga.py`, `tests/test_historico_cargadores.py`, `tests/test_historico_series.py`, `tests/test_inicio_hoy.py`, `tests/historico_fixtures.py` (xlsx sintéticos con openpyxl).

**Frontend:**
- `frontend/index.html`, `frontend/src/index.css`, `frontend/tailwind.config.js` — Geist + tokens.
- `frontend/src/components/layout/AppLayout.tsx` — arreglos de scroll.
- `frontend/src/features/dashboard/DashboardPage.tsx` — se reescribe como composición.
- `frontend/src/features/dashboard/{MoneyPanel,WeekPayablesPanel,BranchesPanel,SalesByMonthChart,ApprovalStrip,Skeletons}.tsx`, `frontend/src/features/dashboard/useCountUp.ts`.
- `frontend/src/types/api.ts` — tipos `DashboardToday`, `AnalyticsSeries`.

---

### Task 1: Modelo, migración y reemplazo por rango

**Files:**
- Create: `app/models/historical.py`, `alembic/versions/20261103_04_historico.py`, `app/domains/analytics/__init__.py`, `app/domains/analytics/points.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_historico_carga.py`

**Interfaces:**
- Produces:
  - `HistoricalLoad(id, organization_id, source: str, period_from: date, period_to: date, rows: int, loaded_by: str|None, loaded_at: datetime, notes: str|None)` — `TenantMixin`, `AuditMixin`.
  - `HistoricalPoint(organization_id, load_id, dataset: str, metric: str, period_start: date, period_grain: str, business_unit_id: str|None (FK), unit_label: str|None, fiscal_entity_id: str|None (FK), payment_method: str|None, account_code: str|None, account_label: str|None, value: Numeric(16,2), source: str)`; índice `(organization_id, dataset, metric, period_start)`.
  - `DATASETS = ("sales_daily","sales_monthly","sales_target","pnl_monthly","expense_monthly","balance_monthly","cash_daily","snapshot")`, `GRAINS = ("day","month","snapshot")`.
  - `@dataclass(frozen=True) class Point: dataset, metric, period_start: date, period_grain, value: Decimal, unit_label=None, entity_label=None, payment_method=None, account_code=None, account_label=None` (en `points.py`; las etiquetas se resuelven a ids en `loading.py`).
  - `replace_points(db, organization_id, *, source_family: str, source: str, points: list[ResolvedPoint], user_id: str|None, notes: str|None=None) -> HistoricalLoad` — borra los `HistoricalPoint` de la org con `source LIKE f"{source_family}:%"` y `dataset` en los datasets de `points` y `period_start` entre el mínimo y el máximo de `points` (por dataset), inserta los nuevos y crea el `HistoricalLoad`; un solo commit. `source_family` ∈ `{"toronja","control_general","reconstruccion","efectivo"}`; `source` = `f"{family}:{archivo}#{hoja}"`.
  - `ResolvedPoint` = `Point` + `business_unit_id`, `fiscal_entity_id`.

- [ ] **Step 1: Write the failing tests**

```python
def test_replace_points_reemplaza_solo_el_rango_y_la_familia(db, org):
    # carga toronja ene–feb (4 puntos) y control_general ene (1 punto)
    # recarga toronja feb–mar (2 puntos)
    # → toronja: ene intacto, feb reemplazado, mar nuevo; control_general intacto
    assert counts == {"toronja": 3, "control_general": 1}

def test_recargar_igual_deja_el_mismo_conteo(db, org): ...  # 2 cargas idénticas → mismo número de puntos, 2 HistoricalLoad

def test_historico_no_toca_la_contabilidad(db, org):
    # trial balance y suma de current_balance antes == después de replace_points
```

Fixture `org`: empresa registrada con `tests/helpers.register` vía `client`, o creada con el servicio de onboarding como en `tests/test_apertura.py`.

- [ ] **Step 2: Run** `pytest tests/test_historico_carga.py -v` → FAIL (import error).
- [ ] **Step 3: Implement** modelo, registro en `app/models/__init__.py`, migración (create_table ×2 + índice; `downgrade` las borra) y `points.py`. El borrado es `DELETE` real: el histórico es una capa reemplazable, no un registro contable (el invariante "nada se borra" aplica al libro).
- [ ] **Step 4: Run** `pytest tests/test_historico_carga.py -v && alembic upgrade head && alembic heads` → PASS, un solo head `20261103_04`.
- [ ] **Step 5: Commit** `feat(historico): tablas de histórico de análisis y reemplazo por rango`.

---

### Task 2: Cargador de Toronja → `sales_daily`

**Files:**
- Create: `app/domains/analytics/loaders/__init__.py`, `app/domains/analytics/loaders/toronja.py`, `app/domains/analytics/loading.py`
- Test: `tests/test_historico_cargadores.py` (usa `tests/toronja_fixture.py`: `ticket()`, `render_html()`)

**Interfaces:**
- Consumes: `parse_toronja(content: bytes) -> list[dict]` (claves `date, vendor, cancelled, edited, gran_total, discount, debt, cash, debit_card, credit_card, transfer, credit`); `Point`, `replace_points` (Task 1); `normalize_alias` de `app.services.dimensions`.
- Produces:
  - `load_toronja(content: bytes, filename: str) -> list[Point]` — por día × `vendor` (como `unit_label`) × forma de pago:
    - métricas por día × unidad (sin forma): `net_sales` (suma de `gran_total` sin cancelados), `tickets` (conteo sin cancelados), `discount`, `debt`, `cancelled` (conteo), `edited` (conteo);
    - métricas por día × unidad × `payment_method` ∈ `EFECTIVO|TARJETA|TRANSFERENCIA|CREDITO`: `net_sales_by_method` desde `cash`, `debit_card+credit_card`, `transfer`, `credit` (sin cancelados).
    - Un ticket es cancelado si `cancelled` no está vacío.
  - `load_files(db, organization_id, files: dict[str, tuple[str, bytes]], user_id, dry_run=False) -> LoadReport` en `loading.py`, donde la clave es la familia (`"toronja"`, …) y el valor `(filename, content)`. Resuelve `unit_label` → `business_unit_id` con nombre/código/alias normalizados de **todas** las unidades de la org (activas o no, para que Cumbres resuelva), y `entity_label` → `fiscal_entity_id` por nombre normalizado. En `dry_run` hace rollback.
  - `@dataclass LoadReport: loads: list[dict]` (familia, source, period_from, period_to, rows), `unresolved_units: list[str]`, `unresolved_entities: list[str]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_toronja_agrega_por_dia_unidad_y_excluye_cancelados():
    # 3 tickets: 2 de "VILLAS" el 2026-01-02 (1,000 y 500), 1 cancelado de 300
    points = load_toronja(render_html([...]), "ventas.xls")
    net = [p for p in points if p.metric == "net_sales"]
    assert net == [Point("sales_daily","net_sales",date(2026,1,2),"day",Decimal("1500.00"),unit_label="VILLAS")]
    assert value(points, "tickets") == 2 and value(points, "cancelled") == 1

def test_toronja_nunca_persiste_paciente_ni_estudios(db, org):
    load_files(db, org.id, {"toronja": ("v.xls", render_html([ticket(..., cliente="JUANA PEREZ", estudios="BH")]))}, None)
    dump = " ".join(str(c) for row in db.query(HistoricalPoint).all() for c in row.__dict__.values())
    assert "JUANA" not in dump and "BH" not in dump

def test_unidad_no_resuelta_queda_con_etiqueta_y_se_reporta(db, org_con_unidades):
    report = load_files(..., vendedor "SUCURSAL FANTASMA" ...)
    assert report.unresolved_units == ["SUCURSAL FANTASMA"]
    assert point.business_unit_id is None and point.unit_label == "SUCURSAL FANTASMA"

def test_alias_resuelve_unidad_inactiva(db, org_con_unidades):  # "LAS CUMBRES" → unidad Cumbres (active=False)

def test_recargar_con_un_mes_mas_reemplaza_y_agrega(db, org): ...  # Review Focus 3
```

- [ ] **Step 2: Run** `pytest tests/test_historico_cargadores.py -v` → FAIL.
- [ ] **Step 3: Implement** `load_toronja` y `load_files` (por ahora sólo con la familia `toronja`; las demás se registran en Tasks 3–5 en un dict `LOADERS = {"toronja": load_toronja, ...}`).
- [ ] **Step 4: Run** `pytest tests/test_historico_cargadores.py -v` → PASS.
- [ ] **Step 5: Commit** `feat(historico): cargador de ventas de Toronja agregado por día y sucursal`.

---

### Task 3: Cargador de CONTROL GENERAL (PROY, RESUTADOS, PRESTAMOS, INVERSIONES)

**Files:**
- Create: `app/domains/analytics/loaders/control_general.py`, `tests/historico_fixtures.py`
- Modify: `app/domains/analytics/loading.py` (registrar `"control_general"`)
- Test: `tests/test_historico_cargadores.py`

**Interfaces:**
- Consumes: `openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)`; `Point`.
- Produces: `load_control_general(content: bytes, filename: str) -> list[Point]`:
  - **PROY ventas** (bloque cuya fila 1 col A = `VENTAS`; meses en filas ENERO…DICIEMBRE; columnas de año = encabezados numéricos o texto `"2023"`; las columnas `%` y `DIFERENCIA` se ignoran): `sales_monthly / net_sales` por mes para cada año ≤ 2026. Un mes de 2026 (o de cualquier año) sólo entra si el bloque `NO. PACIENTES` tiene valor para ese mes y año (Review Focus 2). También `sales_monthly / patients` con ese bloque.
  - **PROY meta**: columnas `2027` → `sales_target / target`, `2027 conservador` → `sales_target / target_conservative`, `period_start` = día 1 de cada mes de 2027.
  - **RESUTADOS**: fila de encabezado con meses en D…; filas `CAJA` (col B) y bancos (col C bajo `BANCOS`, excepto `TOTAL`) → `balance_monthly / balance`, `account_label` = nombre, `period_start` = día 1 del mes (es el saldo a fin de ese mes). Celdas vacías, `#REF!` o meses sin valor se omiten.
  - **PRESTAMOS**: filas con nombre en col B y total en col C → `snapshot / loan_balance`, `account_label` = nombre, `period_start = date(2026,10,31)`, `period_grain="snapshot"`.
  - **INVERSIONES**: bloque "CONCENTRADO GENERAL" (cols H–I) → `snapshot / investment`, `unit_label` = nombre de la fila (HACIENDAS…), excepto `TOTAL`.
- `tests/historico_fixtures.py`: `control_general_xlsx(...) -> bytes`, `reconstruccion_xlsx(...) -> bytes`, `efectivo_xlsx(...) -> bytes`, construidos con openpyxl reproduciendo las posiciones de arriba con cifras inventadas.

- [ ] **Step 1: Write the failing tests**

```python
def test_proy_carga_anios_y_descarta_proyeccion():
    pts = load_control_general(control_general_xlsx(), "cg.xlsx")
    assert value(pts, "sales_monthly", "net_sales", date(2025,9,1)) == Decimal("573522.00")
    assert value(pts, "sales_monthly", "net_sales", date(2026,9,1)) == Decimal("888242.00")
    assert not has(pts, "sales_monthly", "net_sales", date(2026,10,1))  # sin pacientes = proyección

def test_proy_meta_2027(): assert value(pts, "sales_target", "target", date(2027,1,1)) == Decimal("1328191.01")
def test_resultados_saldos_omite_ref_y_total(): ...
def test_prestamos_e_inversiones_como_foto(): ...
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(historico): cargador de CONTROL GENERAL (ventas, metas, saldos, préstamos, inversiones)`.

---

### Task 4: Cargador de la reconstrucción contable (04, 03, 17, 18)

**Files:**
- Create: `app/domains/analytics/loaders/reconstruccion.py`
- Modify: `app/domains/analytics/loading.py`, `tests/historico_fixtures.py`
- Test: `tests/test_historico_cargadores.py`

**Interfaces:**
- Produces: `load_reconstruccion(content: bytes, filename: str) -> list[Point]`:
  - **04_Estado_Resultados**: encabezado en la fila cuyo col A = `Cuenta` (meses `Ene`…`Dic` desde col D). Renglones de total por su concepto (col B) → `pnl_monthly` con métrica: `Total de ingresos`→`revenue`, `Total costo de ventas`→`cost_of_sales`, `Utilidad bruta`→`gross_profit`, `Total gastos de operación`→`operating_expenses`, `Utilidad de operación`→`operating_profit`, `Total resultado integral…` (prefijo)→`financial_result`, `Utilidad antes de sueldo…` (prefijo)→`profit_before_partners`, `Utilidad después de sueldo…` (prefijo)→`profit_after_partners`. El año sale del título (`… 2026`).
  - **03_Libro_Diario**: encabezado en la fila con `Póliza`. Agrega `Monto` por mes (`Fecha`) × `Cuenta de cargo` (`account_code`, `account_label` = nombre) × `Entidad (Liza / Ale)` (`entity_label`; `Por asignar` → None) × `Unidad de negocio` (`unit_label`) sólo para cuentas de cargo que empiezan con `5`, `6` o `7` → `expense_monthly / amount`.
  - **Avance de la revisión** (`snapshot`, `period_start = date(2026,10,21)`): `journal_confirmed` / `journal_pending` = conteo de pólizas con `Estatus` `Confirmado` / distinto; `findings_<estatus>` desde 17 (col `Estatus`) y `questions_<estatus>` desde 18, estatus normalizado en minúsculas sin acentos (`findings_resuelto`, `findings_parcial`…).

- [ ] **Step 1: Tests**: `test_estado_resultados_mapea_totales` (sep `profit_after_partners` del fixture), `test_libro_diario_agrega_gasto_y_omite_ingresos`, `test_por_asignar_queda_sin_entidad`, `test_avance_de_revision_cuenta_por_estatus`.
- [ ] **Step 2–4:** FAIL → implementar → PASS.
- [ ] **Step 5: Commit** `feat(historico): cargador de la reconstrucción (resultados, gasto por cuenta, avance)`.

---

### Task 5: Cargador de Control de Efectivo → `cash_daily`

**Files:**
- Create: `app/domains/analytics/loaders/efectivo.py`
- Modify: `app/domains/analytics/loading.py`, `tests/historico_fixtures.py`
- Test: `tests/test_historico_cargadores.py`

**Interfaces:**
- Produces: `load_efectivo(content: bytes, filename: str) -> list[Point]`: en cada hoja de mes (`Enero`…`Diciembre`), la tabla de la derecha con encabezado `Fecha | Ingresos día | Egresos día | Saldo cierre día` (buscar la fila que contiene `Saldo cierre día`; columnas por posición del encabezado) → `cash_daily` con métricas `inflows`, `outflows`, `closing_balance`, `account_label="Caja central"`. Se omiten días sin fecha y meses vacíos.

- [ ] **Step 1: Test** `test_efectivo_saldo_cierre_por_dia` (último día de octubre del fixture = 27,407.00) y `test_efectivo_omite_meses_vacios`.
- [ ] **Step 2–4:** FAIL → implementar → PASS.
- [ ] **Step 5: Commit** `feat(historico): cargador del control de efectivo diario`.

---

### Task 6: Script y endpoint de carga

**Files:**
- Create: `scripts/lafe_historico.py`, `app/domains/analytics/schemas.py`, `app/domains/analytics/router.py`
- Modify: `app/routers.py` (incluir el router)
- Test: `tests/test_historico_carga.py`

**Interfaces:**
- Consumes: `load_files` (Task 2).
- Produces:
  - `POST /api/admin/historical-loads` multipart con campos opcionales `toronja`, `control_general`, `reconstruccion`, `efectivo` (UploadFile) y `dry_run: bool=False`; `require_role(("OWNER",))`; responde `HistoricalLoadReport {loads: [{family, source, period_from, period_to, rows}], unresolved_units: [str], unresolved_entities: [str], dry_run: bool}`. Sin archivos → 400 "Sube al menos un archivo". Un archivo que no es el esperado → 400 con el mensaje del cargador (los cargadores levantan `HistoricalFormatError(ValueError)` con mensaje en español).
  - `GET /api/admin/historical-loads` → lista de `HistoricalLoad` de la org (OWNER/ADMIN/ACCOUNTANT).
  - `scripts/lafe_historico.py --org <nombre|id> [--toronja F] [--control-general F] [--reconstruccion F] [--efectivo F] [--dry-run]`, mismo patrón que `scripts/lafe_apertura.py` (`find_organization`, `SessionLocal`, imprime el reporte).

- [ ] **Step 1: Tests**: `test_carga_solo_owner` (ADMIN → 403), `test_carga_dry_run_no_guarda`, `test_carga_sin_archivos_400`, `test_archivo_equivocado_400_en_espanol`, `test_otra_empresa_no_ve_las_cargas`.
- [ ] **Step 2–4:** FAIL → implementar → PASS.
- [ ] **Step 5: Commit** `feat(historico): carga por script y por endpoint (sólo dueño)`.

---

### Task 7: Serie unida histórico + vivo

**Files:**
- Create: `app/domains/analytics/series.py`
- Modify: `app/domains/analytics/router.py`, `app/domains/analytics/schemas.py`
- Test: `tests/test_historico_series.py`

**Interfaces:**
- Produces:
  - `GET /api/analytics/series?dataset=sales&metric=net_sales&from=YYYY-MM-DD&to=YYYY-MM-DD&grain=month|day&business_unit_id=&fiscal_entity_id=&compare=previous_year` — todos los roles.
  - Respuesta `AnalyticsSeries {points: [{period: date, value: Decimal, origin: "historical"|"live", partial: bool}], previous: [{period, value, origin}] | null, target: [{period, value}] | null, opening_date: date|null, historical_available: bool, historical_note: str|null}`.
  - `series(db, organization_id, *, metric, start, end, grain, business_unit_id=None, fiscal_entity_id=None, compare=None) -> dict`. Para esta entrega sólo `dataset=sales`, `metric=net_sales` (otro → 400 "Serie no disponible").
  - `live_sales(db, organization_id, start, end, grain, business_unit_id, fiscal_entity_id) -> dict[date, Decimal]` — suma de `Income.amount` (status ≠ CANCELLED) + `Receivable.amount` (status ≠ CANCELLED) con `category_id` = categoría de ventas (`_resolved_toronja_settings(db, org)["income_category_id"]`; si es None, categoría INCOME llamada "Ventas"; si no hay, serie viva vacía). Lo usa también Task 9.
- Reglas (spec "Cómo se lee" y Definiciones 1 y 7):
  - periodo < `opening_date` → histórico; ≥ → vivo; sin `opening_date` → todo vivo. Mes que contiene el corte con día ≠ 1: días previos de `sales_daily` y el resto vivo, sumados en el mismo punto con `origin="live"` (Review Focus 1).
  - Histórico mensual: año ≤ 2025 desde `sales_monthly`; 2026 desde la suma de `sales_daily` del mes, y `sales_monthly` sólo si no hay `sales_daily` en ese mes.
  - Con `business_unit_id`: histórico sólo de `sales_daily` (PROY no trae unidad). Con `fiscal_entity_id`: no hay histórico → `historical_available=false`, `historical_note="El histórico no trae desglose por contribuyente"`; vivo sí se filtra.
  - `partial=True` en el mes (o día) en curso.
  - `compare=previous_year` → `previous` con el mismo cálculo un año atrás; `target` desde `sales_target` cuando hay puntos en el rango.
  - Nunca puntos con `value` inventado: periodo sin dato no aparece.

- [ ] **Step 1: Tests**:

```python
def test_antes_del_corte_historico_despues_vivo(db, org_lafe_like):
    # opening_date 2026-11-01; histórico sales_daily oct = 900; ingreso vivo Ventas nov-02 = 100
    s = series(..., start=date(2026,1,1), end=date(2026,12,31), grain="month")
    assert pt(s, "2026-10").origin == "historical" and pt(s, "2026-11").origin == "live"
    assert pt(s, "2026-11").value == Decimal("100.00")

def test_corte_a_mitad_de_mes_no_duplica(db, org): ...  # corte 15-oct: oct = histórico 1–14 + vivo 15–31
def test_sin_corte_todo_vivo_y_sin_historico(db, demo_org): assert s["historical_available"] is False
def test_filtro_contribuyente_oculta_historico(db, org): assert s["historical_note"] == "El histórico no trae desglose por contribuyente"
def test_2025_sale_de_proy_y_2026_de_toronja(db, org): ...
def test_ingreso_cancelado_y_otros_ingresos_no_cuentan(db, org): ...  # categoría "Rentas" excluida
def test_member_y_viewer_ven_la_serie(client): ...  # 200
def test_otra_empresa_no_ve_el_historico(client): ...
```

- [ ] **Step 2–4:** FAIL → implementar → PASS.
- [ ] **Step 5: Commit** `feat(analytics): serie de ventas que une histórico y lo registrado en ONE Finance`.

---

### Task 8: `/api/dashboard/today` — dinero, pagos de la semana y autorización

**Files:**
- Create: `app/domains/dashboard/today.py`
- Modify: `app/domains/dashboard/router.py`
- Test: `tests/test_inicio_hoy.py`

**Interfaces:**
- Consumes: `available_cash`, `in_transit_total`, `outstanding` de `app/domains/dashboard/service.py`; `AgentProposal`; `approvals.can_authorize`, `approvals.reaches_threshold`.
- Produces: `GET /api/dashboard/today?week_of=YYYY-MM-DD&business_unit_id=&fiscal_entity_id=` (todos los roles) → `{money, week, approvals, branches}` (`branches` en Task 9). `today(db, organization_id, membership, week_of: date, business_unit_id, fiscal_entity_id) -> dict`.
  - `money`: `{total, available, in_transit, previous_close, delta, rows: [{key: "central"|"branches"|"banks"|"processor", label, amount, status: "CONFIRMED"|"PROVISIONAL"|"TO_COLLECT"|"TO_DEPOSIT"|null}], next_settlement: {account, amount, expected_on}|null, needs_opening: bool}`.
    - central = CASH activas sin `business_unit_id`; branches = CASH con unidad; banks = BANK + OTHER; processor = PROCESSOR (Definición 4).
    - status de central/banks: `CONFIRMED` si todas las cuentas del grupo tienen `opening_status == "CONFIRMED"`, si no `PROVISIONAL`; branches `TO_COLLECT`; processor `TO_DEPOSIT`.
    - `previous_close`: suma de los saldos de las mismas cuentas al cierre del día hábil anterior (lunes → viernes previo), calculada como saldo actual menos movimientos `ACTIVE` posteriores a ese día; `delta = total - previous_close`.
    - `next_settlement`: para cada PROCESSOR con `settlement_days`, el saldo actual con `expected_on = hoy + settlement_days` (días naturales); el más próximo.
    - `needs_opening`: la org tiene `opening_status == "PROVISIONAL"` y todas las BANK tienen saldo 0.
  - `week`: `{start, end, days: [{date, amount, pending_approval_amount}], items: [{payable_id, due_date, vendor, description, amount (saldo pendiente), running_balance, approval: "PENDING"|"REQUIRED"|null}], total}`.
    - CxP `OPEN|PARTIAL` con `due_date` lunes–domingo de `week_of`, más las vencidas antes del lunes como renglón del lunes con `overdue: true`. Orden por `due_date`.
    - `running_balance` = `money.total` − pagos acumulados.
    - `approval`: `PENDING` si existe `AgentProposal` `kind="PAYABLE_PAYMENT"`, `status="PROPOSED"`, `payload["payable_id"] == id`; `REQUIRED` si no y `reaches_threshold(org, saldo)` (Definición 3).
  - `approvals`: `{pending: [{proposal_id, summary, amount, requested_by_name}], can_authorize: bool}` — propuestas `PROPOSED` cuyo `origin` empieza con `approval:`; la franja sólo se pinta si `can_authorize` y hay pendientes.

- [ ] **Step 1: Tests**: `test_dinero_parte_central_sucursales_bancos_transito`, `test_banco_provisional_marca_needs_opening`, `test_delta_contra_dia_habil_anterior` (movimiento hoy de 500 → delta 500; lunes compara contra viernes), `test_semana_lunes_a_domingo_con_saldo_corrido`, `test_vencida_aparece_el_lunes`, `test_por_autorizar_y_requiere_autorizacion`, `test_member_ve_inicio`, `test_empresa_vacia_responde_ceros_y_listas_vacias`.
- [ ] **Step 2–4:** FAIL → implementar → PASS.
- [ ] **Step 5: Commit** `feat(inicio): endpoint del tablero del día (dinero, pagos de la semana, autorizaciones)`.

---

### Task 9: Sucursales en `/api/dashboard/today`

**Files:**
- Modify: `app/domains/dashboard/today.py`
- Test: `tests/test_inicio_hoy.py`

**Interfaces:**
- Consumes: `live_sales` (Task 7); `HistoricalPoint` (`sales_daily`); `CashCut`.
- Produces: `branches: {month, origin: "live"|"historical", rows: [{business_unit_id, name, sales, share, delta_pct, delta_basis: "previous_year"|"avg_3m"|null, sparkline: [{date, value}] (30 días), cut: "DELIVERED"|"LATE"|"MISSING"|"NA"}]}`.
  - Filas: unidades activas, orden por `sales` desc. `share` = sales / máximo.
  - Venta del mes en curso viva por unidad; si **ninguna** unidad tiene venta viva en el mes, se usa el último mes con `sales_daily` y `origin="historical"`.
  - Delta (Definición 2): contra el mismo mes del año anterior si hay dato de esa unidad (vivo o histórico); si no, contra el promedio de los 3 meses previos con dato (`avg_3m`); sin base → null. Para el mes en curso compara contra el mismo tramo de días del periodo base.
  - Sparkline: 30 días hasta ayer, días sin dato con 0 sólo dentro del rango donde la unidad tiene algún dato.
  - Corte (Definición 5) para ayer y la caja CASH de la unidad (primera por nombre, como `_cash_by_unit`): sin caja → `NA`; corte no `CANCELLED` con `delivered_at` del mismo día (zona `organization.timezone`) → `DELIVERED`; `delivered_at` posterior → `LATE`; sin corte y la caja tuvo movimientos ese día → `MISSING`; sin corte y sin movimientos → `NA`.

- [ ] **Step 1: Tests**: `test_sucursales_ordenadas_por_venta`, `test_delta_vs_mismo_mes_anio_pasado`, `test_delta_vs_promedio_3_meses_sin_anio_previo`, `test_sin_venta_viva_usa_ultimo_mes_historico`, `test_estado_del_corte` (cuatro casos), `test_unidad_inactiva_no_aparece`.
- [ ] **Step 2–4:** FAIL → implementar → PASS.
- [ ] **Step 5: Commit** `feat(inicio): sucursales con venta del mes, comparación y corte de ayer`.

---

### Task 10: Lenguaje visual global (Geist, tokens, scroll)

**Files:**
- Modify: `frontend/index.html`, `frontend/src/index.css`, `frontend/tailwind.config.js`, `frontend/src/components/layout/AppLayout.tsx`, `CLAUDE.md` (línea de UI: cifras con `.figures` en Geist tabular)

**Interfaces:**
- Produces: tokens existentes con valores nuevos en `.dark` (`--bg` #0c1210, `--surface` #121a17, `--surface-2` #18221e, `--border` #22302a, `--ink` #e4ece7, `--muted` #6f8079, `--accent` #4cc38a, `--warn` #e2a54a, `--neg` #e86a5e) y token nuevo `--ink-soft` (#a9b8b0) → Tailwind `ink-soft`; `--accent-strong` (#2a8f63) → `accent-strong`. Modo claro derivado con el mismo matiz (fondo casi blanco verdoso, tinta #0e1613, acento #1f8a5b). Alias `--color-*` para recharts de todos los tokens que use una gráfica (`--color-accent`, `--color-warn`, `--color-neg`, `--color-ink-soft`, `--color-surface-2`).
  - Geist desde Google Fonts (400;500;600) reemplaza Plus Jakarta Sans y JetBrains Mono; `fontFamily.body/display = Geist`, `.figures` = Geist con `tabular-nums`.
  - Utilidades: `.panel` (radio 10px, borde 1px `border`, fondo `surface`, sin sombra), `.figure-hero` (40px, 500, tracking −0.03em).
  - Scroll: `html, body { overflow-x: hidden }` no basta; el contenedor de `main` lleva `min-w-0` y el ancho lo ponen los hijos; el `nav` del menú lateral lleva `scrollbar-color: hsl(var(--border)) transparent; scrollbar-width: thin` y `::-webkit-scrollbar` equivalente.

- [ ] **Step 1:** Implementar tokens, fuente, utilidades y scroll.
- [ ] **Step 2: Run** `cd frontend && npm run typecheck && npm run build` → sin errores.
- [ ] **Step 3: Verificar** con capturas (Edge headless, ver memoria `ui-screenshots-via-windows-edge.md`) de `/`, `/gastos`, `/movimientos`, `/caja`, `/reportes` en oscuro y claro a 1440 px: sin scroll horizontal de página, scrollbar del menú oscura, nada ilegible. Corregir lo que se rompa.
- [ ] **Step 4: Commit** `style(ui): Geist y paleta nueva en toda la plataforma; arregla scroll horizontal y barra del menú`.

---

### Task 11: Inicio en el front

**Files:**
- Rewrite: `frontend/src/features/dashboard/DashboardPage.tsx`
- Create: `frontend/src/features/dashboard/{MoneyPanel,WeekPayablesPanel,BranchesPanel,SalesByMonthChart,ApprovalStrip,Skeletons}.tsx`, `frontend/src/features/dashboard/useCountUp.ts`
- Modify: `frontend/src/types/api.ts`

**Interfaces:**
- Consumes: `GET /api/dashboard/today` (Tasks 8–9), `GET /api/analytics/series?dataset=sales&metric=net_sales&grain=month&from=<año>-01-01&to=<año>-12-31&compare=previous_year` (Task 7); filtros `DimensionFilterSelects` + `dimensionParams` de `components/ui/DimensionFields`.
- Produces: `useCountUp(value: number, durationMs = 600): number` (una vez por montaje; con reduced-motion devuelve `value` directo). Tipos `DashboardToday`, `AnalyticsSeries` espejo de los schemas.
- Layout y comportamiento exactos: spec, secciones "Estructura", "Paneles", "Comportamiento" y la maqueta A (`.superpowers/brainstorm/996202-1793743918/content/inicio-opciones.html`; si no existe en tu worktree, pídela al orquestador).
  - Grid `lg:grid-cols-[300px_1.1fr_1.2fr]`, apilado < 1024 px en orden dinero → pagos → sucursales; ventas a todo el ancho abajo.
  - Barra superior compacta con filtros unidad / contribuyente / semana; `ApprovalStrip` debajo sólo si `approvals.can_authorize && approvals.pending.length`.
  - Enlaces: pago → `/por-pagar?open=<payable_id>`; sucursal → `/ingresos?business_unit_id=<id>`; "Captura el saldo de tus bancos" → `/configuracion/apertura`; "Registrar cuenta por pagar" → `/por-pagar?new=1`. Si `/por-pagar` no lee `open`/`new` de la URL, agregarlo en `PayablesPage`.
  - Gráfica de ventas (recharts `ComposedChart`): año actual en dos `Line` (histórico `strokeDasharray="4 3"`, vivo sólido; el punto frontera se repite en ambas para que no haya hueco), año anterior en `muted`, meta en `warn` punteado fino, `ReferenceLine` en `opening_date` con etiqueta "1 nov · inicia ONE Finance" (fecha formateada), mes `partial` como punto hueco "en curso". Rejilla sólo horizontal, ejes 10.5px `muted`, leyenda propia arriba a la derecha, tooltip con cifra y Δ % vs año anterior. Con `historical_note` se muestra la nota en lugar de la serie histórica.
  - Esqueletos con la forma de cada panel mientras carga; empty states con CTA (spec "Sin datos"); nunca "$0.00" mudo.
  - Cada gráfica con `aria-label` que incluye la cifra clave.
  - Borrar del archivo lo que el tablero viejo ya no usa (DeltaChip, ChartCard, colores crudos `IN/OUT/LOSS/GRID`).

- [ ] **Step 1:** Tipos y `useCountUp`.
- [ ] **Step 2:** Paneles y gráfica.
- [ ] **Step 3: Run** `cd frontend && npm run typecheck && npm run build` → sin errores.
- [ ] **Step 4: Verificar** con capturas a 1440 y 390 px, oscuro y claro, contra la demo (con datos) y La Fe en prod (con histórico tras Task 12). Comparar contra la maqueta A; corregir antes de seguir.
- [ ] **Step 5: Commit** `feat(inicio): tablero del día con dinero, pagos de la semana, sucursales y ventas por mes`.

---

### Task 12: Integración, despliegue y carga de La Fe

**Files:** ninguno nuevo (sólo `docs/MVP_STATUS.md`).

- [ ] **Step 1: Run** `pytest -q && ruff check . && cd frontend && npm run typecheck && npm run build` → todo verde.
- [ ] **Step 2:** Merge a `main` y push (= deploy). Vigilar `railway deployment list` hasta SUCCESS y revisar `railway logs --deployment <id>` sin 500.
- [ ] **Step 3:** Cargar el histórico de La Fe en prod por el endpoint como `lafe@atlas.mx` (OWNER) con los 4 archivos del scratchpad (`lafe-in/`), primero `dry_run=true`; revisar `unresolved_units`, agregar alias a las unidades si falta alguno y cargar en firme.
- [ ] **Step 4: Verificar** en prod: `/api/analytics/series` de La Fe con ene–sep 2026 `historical` y sep ≈ 892,011; Inicio de La Fe en captura; `GET /api/accounting/trial-balance` igual que antes de la carga.
- [ ] **Step 5:** Actualizar `docs/MVP_STATUS.md` y commit `docs: estado tras Inicio e histórico`.
