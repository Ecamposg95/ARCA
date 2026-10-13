# Apertura y cierre anual (C-2)

_2026-10-12. Segundo módulo de la fase 1 del plan maestro (`docs/MEGA_PLAN_MVP.md`). Diseño derivado del plan y de C-1; Emmanuel autorizó avanzar sin compuerta por documento._

## Para qué

Una empresa que llega a ARCA desde CONTPAQi trae saldos: IVA pendiente, retenciones por enterar, otros activos, capital. Hoy sólo los instrumentos, la cartera, los activos fijos y los préstamos saben abrir con saldo; el resto del balance no tiene por dónde entrar. Y al terminar el año, ingresos y gastos siguen acumulándose para siempre: la balanza del SAT lo disimula con un cierre virtual, el balance general inventa una línea "3999 Resultado del periodo" y nada protege un ejercicio ya dictaminado.

C-2 agrega las dos pólizas que faltan, con el mismo motor y los mismos invariantes: una **póliza de apertura** con los saldos iniciales por cuenta, balanceada contra el capital, y una **póliza de cierre** que traspasa el resultado del ejercicio a Resultados Acumulados y deja el año bajo candado, reabrible con motivo y rastro.

## Lo que se sabe

- `post_journal_entry` (`app/services/accounting/engine.py`) es el único punto de escritura; valida partida doble, cuentas activas, mes cerrado (`_assert_period_open` contra `period_locks`) y asigna folio. `account_type_balance` suma un tipo de cuenta en un rango; `trial_balance` lista todo.
- `rules.py` tiene `manual_entry` (C-1) con `ManualLine(account_id, debit, credit)`, `MODULE_CONTROLLED_CODES`, `reverse_manual_entry` (sólo `source_type="manual"`) y `reversal_of` (espejo con `reference="reversal:{id}"`, conserva `source_type` y `source_id`).
- `coa.py`: `CODE_CAPITAL="3100"`, `CODE_RETAINED_EARNINGS="3200"`; el catálogo tiene dos niveles. `AccountRead` expone `type`, `parent_id`, `manual_allowed`, `system`, `has_movements`.
- `app/domains/periods/service.py`: `close_period`/`reopen_period` sobre `PeriodLock` (fila única por empresa+año+mes, reutilizada al recerrar, rastro de reapertura en `notes`); `list_periods` arma los últimos meses. Router `/api/periods` con `ACCOUNTING_ROLES` por endpoint.
- `app/domains/accounting/service.py::sat_balance` simula el cierre: las cuentas de resultados sólo arrastran saldo desde el 1 de enero y el neto de años anteriores abre en 3200 (prueba `test_prior_year_results_open_the_year_in_retained_earnings`).
- `app/domains/reports/service.py`: `profit_loss` usa `_lines_by_account` sobre REVENUE/EXPENSE en un rango; `balance_sheet` agrega "3999 Resultado del periodo" con `account_type_balance`. El dashboard usa `account_type_balance` por mes.
- Frontend: `PeriodsPanel.tsx` (tabla de meses con cerrar/reabrir, export CONTPAQi y SAT), `JournalDiary.tsx` (detalle con "Revertir" para pólizas manuales y etiquetas por origen), `AccountingPage.showEntry(id, dateIso)`, `Modal` con `size="lg"`, `JournalEntryForm` como referencia de rejilla con totales vivos.

## Diseño

### Póliza de apertura

Regla nueva en `rules.py`:

```python
OPENING_SOURCE = "opening"
OPENING_BALANCING_CODES = (CODE_RETAINED_EARNINGS, CODE_CAPITAL)  # 3200 por defecto, 3100 opcional

@dataclass(frozen=True)
class OpeningLine:
    account_id: str
    amount: Decimal  # saldo en la naturaleza de la cuenta, >= 0

def opening_entry(db, organization_id, date, lines, balancing_code=CODE_RETAINED_EARNINGS,
                  description=None, created_by=None) -> JournalEntry
```

- Siempre `kind="DIARIO"`, `source_type="opening"`, `source_id=f"opening:{organization_id}"` (cabe en 64). Descripción por defecto: "Saldos iniciales al {dd/mm/aaaa}".
- Una sola apertura viva por empresa: si existe una póliza `POSTED` con ese `source_type`+`source_id` que no tenga reverso (`reference="reversal:{id}"`), error "Ya existe una póliza de apertura ({folio}). Reviértela desde el diario para capturar otra."
- Fecha no futura ("No se puede asentar una póliza con fecha futura."); el mes cerrado lo valida el motor.
- Cada línea: cuenta de la empresa por `account_id` (`LookupError` → 404 si no existe), activa, de detalle (`parent_id` no nulo), de tipo ASSET, LIABILITY o EQUITY ("La apertura sólo lleva cuentas de balance; ingresos y gastos empiezan en cero."), no controlada por módulos ("La cuenta {code} abre desde su módulo: bancos y tarjetas en Movimientos, cartera en Por cobrar y Por pagar, activos fijos y préstamos en Patrimonio."), y distinta de la cuenta de cuadre ("La cuenta {code} es la de cuadre; su saldo se calcula."). `amount >= 0`; una línea en cero se ignora; una cuenta repetida se rechaza ("La cuenta {code} aparece dos veces."). Entre 1 y 100 líneas con monto.
- Naturaleza: ASSET → cargo por `amount`; LIABILITY y EQUITY → abono. Excepción 1490 ya está bloqueada por módulos, así que no hay contra-cuentas capturables.
- Cuadre: `residual = cargos − abonos`. Si `residual > 0` se abona a `balancing_code`; si `< 0` se carga `|residual|`; si es cero no se agrega línea (y entonces hacen falta al menos dos líneas capturadas; con una sola y residual cero el motor rechaza). `balancing_code` ∈ `OPENING_BALANCING_CODES`, si no: "La apertura cuadra contra Resultados Acumulados (3200) o Capital (3100)."
- Reverso: `reverse_manual_entry` acepta `source_type` en `HAND_REVERSIBLE_SOURCES = ("manual", "opening")`; el mensaje para los demás no cambia. Tras revertir, se puede capturar otra apertura.

### Cierre de ejercicio

Modelo nuevo `app/models/fiscal_year.py`:

```python
class FiscalYearLock(Base, UUIDPKMixin, TenantMixin, AuditMixin):
    __tablename__ = "fiscal_year_locks"
    # UniqueConstraint(organization_id, year, name="uq_fiscal_year_lock")
    year: int
    closed_by: str | None            # FK users.id
    closing_entry_id: str | None     # FK journal_entries.id; None cuando el año no tuvo resultados
    reopened_at, reopened_by, reopen_reason (500), notes (1000)  # mismos campos que PeriodLock
```

Registrado en `app/models/__init__.py`. Migración `alembic/versions/20261012_01_fiscal_year_locks.py` (`revision="20261012_01"`, `down_revision="20261006_01"`), misma forma que `period_locks` en `20260826_04_rigor.py`.

Servicio `app/domains/periods/service.py` (crece; sigue siendo el dueño de los candados):

```python
def list_years(db, organization_id) -> list[dict]
def close_year(db, organization_id, year, user_id=None, notes=None) -> FiscalYearLock
def reopen_year(db, organization_id, year, reason, user_id=None) -> FiscalYearLock
def is_year_closed(db, organization_id, year) -> bool
```

- `close_year`:
  - `date(year, 12, 31) < today`, si no: "El ejercicio {year} todavía no termina."
  - No cerrado: "El ejercicio {year} ya está cerrado."
  - En orden: el primer año anterior con líneas `POSTED` en cuentas REVENUE/EXPENSE y sin candado vivo debe ser `year`; si existe otro: "Primero cierra el ejercicio {anterior}."
  - Construye la póliza con la regla nueva `rules.year_close_entry(db, organization_id, year, created_by)`: por cada cuenta de detalle REVENUE/EXPENSE con neto (`cargos − abonos` del 1-ene al 31-dic, incluidas las pólizas de cierre y reapertura previas, que se anulan entre sí) distinto de cero: neto > 0 → abono por el neto; neto < 0 → cargo. Utilidad = Σ(abonos − cargos) de resultados; si > 0 abono a 3200, si < 0 cargo a 3200. Fecha 31-dic, `kind="DIARIO"`, `source_type="year_close"`, `source_id=f"year_close:{year}"`, descripción "Cierre del ejercicio {year}". Si ninguna cuenta tiene neto, la regla regresa `None` y el candado se crea sin póliza.
  - La póliza de cierre entra aunque diciembre esté cerrado por mes: `post_journal_entry(..., bypass_period_lock=True)`, parámetro nuevo que sólo usan `year_close_entry` y la reapertura. El módulo de periodos es dueño del candado y la póliza no altera lo declarado del mes (sólo traspasa resultados a capital). Queda escrito en `AGENTS.md`.
  - Fila única por empresa+año reutilizada al recerrar, con la reapertura anterior escrita en `notes` ("Reabierto el {fecha}: {motivo}"), igual que `close_period`. `closing_entry_id` apunta a la póliza nueva. Hace `commit`.
- `reopen_year`:
  - Candado vivo, si no: "El ejercicio {year} no está cerrado."
  - Ningún año posterior cerrado: "Primero reabre el ejercicio {posterior}."
  - Marca `reopened_at/by/reason` y, si hay `closing_entry_id`, emite `rules.reversal_of(..., bypass_period_lock=True)` con fecha 31-dic y descripción "Reapertura del ejercicio {year}: {motivo}". `reversal_of` gana el parámetro `bypass_period_lock=False`.
- `list_years`: del año de la póliza más antigua (o el actual si no hay) al año en curso, descendente: `{year, entries, revenue, expenses, result, closed, can_close, closing_entry_id, closing_folio, reopened_at}`. `revenue`/`expenses` excluyen las pólizas de cierre (ver reportes); `can_close` = terminó y no está cerrado y es el siguiente en orden.
- Candado en el motor: `_assert_period_open` también consulta `FiscalYearLock` vivo para `date.year` → `ClosedPeriodError("El ejercicio {year} está cerrado. Reábrelo si necesitas corregir algo.")`. Sin bypass, nada entra a un año cerrado: ni operaciones, ni pólizas manuales, ni reversos.

### Reportes: el cierre no es un gasto

Constante `YEAR_CLOSE_SOURCE = "year_close"` en `engine.py` (rules la importa de ahí).

- `account_type_balance(..., include_closing: bool = False)` y `reports._lines_by_account(..., include_closing: bool = False)` excluyen `JournalEntry.source_type == YEAR_CLOSE_SOURCE` salvo que se pida lo contrario. Así `profit_loss` de un año cerrado sigue mostrando sus ventas, y el dashboard de enero no ve diciembre en cero.
- `balance_sheet` pasa `include_closing=True` en sus tres llamadas: después del cierre, 3200 trae el resultado y "3999" desaparece para ese corte; antes del cierre todo sigue igual.
- `trial_balance`, el diario, CONTPAQi y la balanza SAT incluyen todo: son el libro.
- `sat_balance` no cambia de código: para un año cerrado, las cuentas de resultados netan cero y la simulación aporta cero; el saldo inicial de 3200 en enero sale de la póliza real. Una prueba lo demuestra ("la balanza deja de simular cuando existe un cierre real").

### API

`/api/accounting` (ya exige `ACCOUNTING_ROLES`):

- `GET /opening-balance` → `{"entry": JournalEntryRead | null, "balancing_codes": ["3200", "3100"]}`; `entry` es la apertura viva (sin reverso).
- `POST /opening-balance` → 201 `JournalEntryRead`. Body:
  ```json
  {"date": "2025-12-31", "description": null, "balancing_code": "3200",
   "lines": [{"account_id": "…", "amount": "1500.00"}]}
  ```
  `amount`: `Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)`; `lines` de 1 a 100; `balancing_code: Literal["3200", "3100"] = "3200"`. `AccountingError` → 400, `LookupError` → 404.
- `POST /journal-entries/{id}/reverse` acepta aperturas.

`/api/periods` (`ACCOUNTING_ROLES` por endpoint, como hoy):

- `GET /years` → `{"items": [...], "total", "limit", "offset"}` con los campos de `list_years` (montos como string).
- `POST /years/{year}/close` body `{"notes": str | null}` → `{"year", "closed": true, "closing_entry_id", "closing_folio"}`.
- `POST /years/{year}/reopen` body `{"reason": str (3–500)}` → `{"year", "closed": false}`.
- `year` entre 2000 y 2100; `ValueError` → 400.

### Interfaz

`PeriodsPanel.tsx` recibe `onShowEntry?: (id: string) => void` desde `AccountingPage` (que ya tiene `showEntry`).

1. **Saldos iniciales** (arriba del panel). Sin apertura: tarjeta con texto "Trae los saldos con los que la empresa llega a ARCA." y botón "Capturar saldos iniciales". Con apertura: "Saldos iniciales al {fecha} · {folio}" con enlace "Ver póliza" (→ `onShowEntry`) y nota "Para corregirlos, revierte la póliza desde el diario y captura otra."
2. **`OpeningBalanceForm.tsx`** (modal `size="lg"`): fecha (por defecto 31 de diciembre del año anterior), selector "Cuadrar contra" (Resultados Acumulados 3200 / Capital 3100), rejilla con las cuentas permitidas (de detalle, activas, tipo de balance, `manual_allowed`, excluida la de cuadre), agrupadas por mayor, con columnas código, nombre, naturaleza ("Deudora"/"Acreedora") y un campo "Saldo" (`AMOUNT_PATTERN` de `JournalEntryForm`). Las cuentas controladas aparecen al final en gris con "Se captura desde {Movimientos | Por cobrar y Por pagar | Patrimonio}". Pie con totales vivos: "Activo", "Pasivo y capital" y "Va a {cuenta de cuadre}: ±X". Guardar envía sólo líneas con monto > 0; al éxito invalida `['accounting']` y `['periods']` y muestra la póliza.
3. **Ejercicios** (tabla entre la tarjeta y los meses): Año · Ingresos · Gastos · Resultado · Estado ("Cerrado" / "Abierto") · acción: "Cerrar ejercicio" (confirm: "¿Cerrar el ejercicio {year}? Ingresos y gastos pasan a Resultados Acumulados y el año queda bajo candado."), "Reabrir" (modal con motivo, mismo patrón que el mes), "Ver póliza" cuando hay `closing_folio`. Cuando no puede cerrarse: "Aún en curso" o "Cierra {año anterior} primero".
4. **Diario**: etiquetas de origen "Apertura" (`opening`) y "Cierre anual" (`year_close`); el botón "Revertir" aparece también en aperturas.
5. Texto del panel de meses sin cambios. Nada de colores crudos; cifras con `.figures`.

### Demo

`scripts/demo_despacho.py` siembra además un ingreso y un gasto en junio y julio del año anterior para que el contador pueda cerrar ese ejercicio en producción y ver 3200 abrir en enero.

## Pruebas

`tests/test_apertura.py`:
- Apertura con IVA pendiente (1191), retención (2410) y capital 3100: líneas cargo/abono correctas y residual a 3200; `trial_balance` cuadra; el balance general cuadra.
- Residual negativo carga a 3200; `balancing_code="3100"` manda el residual a capital.
- Rechazos: cuenta de resultados, cuenta controlada (1100), cuenta mayor, cuenta de cuadre en las líneas, cuenta repetida, fecha futura, mes cerrado, segunda apertura viva; `LookupError` → 404 con cuenta de otra empresa.
- Tras revertir desde `/journal-entries/{id}/reverse`, `GET /opening-balance` regresa `entry: null` y se acepta otra apertura.
- Aislamiento: la apertura de A no aparece en `GET /opening-balance` de B.

`tests/test_cierre_anual.py`:
- Cierre de un año con ventas y gastos: la póliza carga 4xxx, abona 5xxx y abona 3200 por la utilidad; después del cierre `profit_loss` del año no cambia, `balance_sheet` al 31-dic no trae "3999" y cuadra, `trial_balance` al 31-dic deja 4xxx/5xxx en cero.
- Pérdida: cargo a 3200.
- Año sin movimientos de resultados: candado sin póliza (`closing_entry_id` nulo).
- Reglas: año en curso no se cierra; dos veces no; orden (cerrar 2025 antes que 2026 cuando ambos tienen resultados); reabrir exige motivo, emite el reverso con fecha 31-dic, y no se reabre 2025 si 2026 está cerrado.
- Candado: una operación (`POST /api/income`) con fecha dentro del año cerrado recibe 400 con "ejercicio"; después de reabrir, entra. Diciembre cerrado por mes no impide cerrar ni reabrir el año.
- `GET /years`: campos, orden descendente, `can_close` sólo en el siguiente en orden, `closing_folio` tras cerrar.
- Dashboard: la utilidad de diciembre no se vuelve cero después del cierre (`account_type_balance` sin `include_closing`).
- Aislamiento: el candado de A no bloquea pólizas de B en el mismo año.

`tests/test_sat_export.py`: con cierre real del año anterior, la balanza de enero abre 3200 con el resultado real y 4100 en cero; la balanza de diciembre incluye las líneas de cierre y cuadra por hojas.

## Fuera de alcance

- Balanza de cierre del SAT como periodo 13 (TipoEnvio de cierre): se exporta diciembre con la póliza dentro.
- Apertura de activos fijos con depreciación acumulada previa y de préstamos con saldo: siguen entrando por Patrimonio con su fecha real.
- Edición de la apertura: se revierte y se captura otra.
- Cierre automático de los doce meses al cerrar el año: el candado anual ya los cubre; los candados mensuales siguen siendo independientes.
