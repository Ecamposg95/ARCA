# Pólizas manuales y catálogo editable (C-1)

_2026-10-12. Primer módulo de la fase 1 del plan maestro (`docs/MEGA_PLAN_MVP.md`). Diseño aprobado en conversación el 12 de octubre._

## Para qué

Un contador no puede llevar una empresa si no puede registrar lo que los módulos no saben hacer: una provisión de nómina, una depreciación extraordinaria, una reclasificación, un ajuste de inventario. Hoy el motor sólo recibe pólizas desde las reglas de negocio y el catálogo sólo se lee. C-1 abre las dos puertas sin romper ningún invariante: la póliza manual pasa por el mismo motor, y el catálogo crece dentro de la misma estructura.

## Lo que se sabe

- `post_journal_entry` (`app/services/accounting/engine.py`) ya valida partida doble, cuenta activa, mes cerrado y asigna folio. Acepta `kind`, `source_type`, `source_id`, `reference`, `created_by`.
- `reversal_of` (`rules.py`) emite la póliza espejo con `reference="reversal:{id}"`; `already_reversed` (`services/reversals.py`) detecta por `source_type`+`source_id`.
- El catálogo tiene dos niveles: mayores sin padre (1000, 2000, 3000, 4000, 5000) y cuentas de detalle con `parent_id`. La balanza SAT agrega hijas en su padre una sola vez y cuadra por hojas, así que un tercer nivel la rompería.
- Las cuentas sembradas llevan `system=True`; las reglas las referencian por código (`coa.CODE_*`).
- Los instrumentos mantienen `current_balance` espejo del ledger a través de `record_transaction`; CxC y CxP mantienen `balance` espejo de 1200 y 2100.
- Router `/api/accounting` ya exige `ACCOUNTING_ROLES`; el patrón de errores es `ValueError` en service → `HTTPException(400, detail)` en router.
- Frontend: `AccountingPage` con pestañas diario, balanza, catálogo y periodos; `JournalDiary` maestro-detalle; `AccountFieldCell` edita un campo de cuenta con PATCH; `Modal`, `Field`, `TextInput`, `SelectInput`, `Button`, `Table` en `components/ui`.

## Diseño

### Póliza manual

Regla nueva en `rules.py`:

```python
def manual_entry(db, organization_id, date, description, lines, reference=None, created_by=None) -> JournalEntry
```

- Siempre `kind="DIARIO"`, `source_type="manual"`, `source_id=None` al crear; después de persistir se fija `source_id=entry.id` para que el reverso lo encuentre por el mismo camino que una operación.
- Validaciones propias, antes de llamar al motor, con mensajes en español:
  - Fecha no futura: "No se puede asentar una póliza con fecha futura."
  - Descripción obligatoria (1 a 500 caracteres), entre 2 y 100 líneas.
  - Cada línea referencia una cuenta de la empresa por `account_id`; se traduce a código para `LineSpec`.
  - Cuenta mayor (sin `parent_id`): "Las pólizas van a cuentas de detalle, no a la cuenta mayor {code}."
  - Cuentas controladas por módulos: 1100, 1200, 2100, 2200, 1400, 1490, 2300 → "La cuenta {code} la mueven los módulos. Para bancos y tarjetas usa Movimientos; para cartera, Por cobrar y Por pagar; para activos fijos y préstamos, Patrimonio."
  - Cuenta inactiva: "La cuenta {code} está inactiva."
- Lo demás (balance, montos, mes cerrado) lo valida el motor y sus errores suben tal cual.

### Reverso de una póliza manual

```python
def reverse_manual_entry(db, organization_id, entry_id, date, description, created_by=None) -> JournalEntry
```

- Sólo pólizas con `source_type="manual"` y `status="POSTED"`; una póliza de operación se revierte desde su módulo: "Esta póliza nació de una operación; cancélala desde {módulo}."
- Una sola vez: si existe una póliza con `reference="reversal:{id}"` → "Esta póliza ya fue revertida."
- La propia póliza de reverso no se revierte: "Un reverso no se revierte; captura una póliza nueva."
- Fecha del reverso ≥ fecha original y no futura; el motor cuida el mes cerrado.
- Descripción por defecto: "Reverso de {folio}: {descripción original}".

### Catálogo

Funciones nuevas en `coa.py`:

```python
def create_account(db, organization_id, parent_id, code, name, sat_code=None, contpaqi_code=None) -> Account
def rename_account(db, organization_id, account, name) -> Account
def set_account_active(db, organization_id, account, active) -> Account
def account_has_movements(db, account_id) -> bool
```

- `parent_id` debe ser una cuenta mayor de la empresa (sin padre). El tipo se hereda del padre; nunca se captura.
- `code`: sólo dígitos, de 4 a 10, único por empresa, y su primer dígito igual al del padre ("Una cuenta bajo {padre} debe empezar con {dígito}"). Se guarda tal cual.
- `name`: 1 a 255 caracteres, recortado.
- `sat_code` opcional validado contra `sat_code_names()`; si viene vacío se hereda el del padre cuando exista. `contpaqi_code` opcional, misma normalización que el PATCH actual.
- Renombrar: permitido en toda cuenta, sembrada o no.
- Desactivar: sólo cuentas con `system=False` y sin líneas en el ledger ("La cuenta {code} tiene movimientos; no se puede desactivar" / "Las cuentas que ARCA sembró no se desactivan"). Reactivar: siempre.
- Las cuentas inactivas siguen en balanza, XML y export si tuvieron movimientos (sólo filtran `get_account_by_code` y los selectores de la UI). `_active_accounts` del SAT ya filtra por `active`; una cuenta inactiva sin movimientos no afecta nada.

### API

| Método y ruta | Cuerpo | Respuesta |
| --- | --- | --- |
| `POST /api/accounting/journal-entries` | `{date, description, reference?, lines: [{account_id, debit, credit, description?}]}` con montos como strings decimales ≥ 0 | 201 `JournalEntryRead` con líneas |
| `POST /api/accounting/journal-entries/{id}/reverse` | `{date, description?}` | 201 `JournalEntryRead` del reverso |
| `POST /api/accounting/accounts` | `{parent_id, code, name, sat_code?, contpaqi_code?}` | 201 `AccountRead` |
| `PATCH /api/accounting/accounts/{id}` | agrega `name?` y `active?` a `contpaqi_code?`, `sat_code?` | 200 `AccountRead` |
| `GET /api/accounting/accounts` | — | agrega `has_movements: bool` a cada cuenta (una consulta agrupada, no N+1) |
| `GET /api/accounting/journal-entries` | — | agrega `reversed: bool` y `reversal_of: str \| null` a cada póliza |

Errores de regla → 400 con el mensaje de arriba; cuenta o póliza de otra empresa → 404 "Esa cuenta no existe." / "Esa póliza no existe.".

### Interfaz

Pestaña **Diario**:
- Botón "Nueva póliza" en el encabezado. Abre `JournalEntryForm` (modal): fecha (hoy por defecto), concepto, referencia; rejilla de líneas con cuenta (selector con búsqueda por código y nombre, sólo cuentas de detalle activas y no bloqueadas), cargo, abono, concepto de línea; botón "Agregar línea"; al teclear en la última línea se agrega otra. Pie con totales de cargos y abonos y la diferencia; "Guardar" deshabilitado hasta que cuadre y haya dos líneas con monto. Los errores del backend se muestran en el pie.
- Al guardar: invalida `journal-entries` y `trial-balance`, cierra el modal y selecciona la póliza nueva en el diario (`?poliza=`).
- En el detalle de una póliza con `source_type="manual"` y sin `reversed`: botón "Revertir" que pide fecha (hoy) y motivo y llama al endpoint. Una póliza revertida muestra la etiqueta "Revertida" y enlaza al reverso; un reverso muestra "Reverso de {folio}".
- `SOURCE_LABELS` agrega `manual: 'Póliza manual'`.

Pestaña **Catálogo**:
- Botón "Nueva cuenta": modal con cuenta mayor (select), código, nombre, código SAT (datalist existente), equivalente CONTPAQi. El select de mayor precarga el dígito del código.
- Nombre editable en línea con `AccountFieldCell` (campo `name`).
- Columna de acciones: "Desactivar" (sólo `!system && !has_movements`) o "Reactivar". Interruptor "Mostrar inactivas" (apagado por defecto) que filtra la tabla; una inactiva se pinta en `text-muted`.
- La vista empty state no cambia: el catálogo siempre tiene las sembradas.

Paleta de comandos: acción "Nueva póliza" que navega a `/contabilidad?nueva=poliza` y abre el modal (si existe el patrón de acciones; si no, se omite).

### Código

- `app/services/accounting/rules.py`: `MODULE_CONTROLLED_CODES`, `manual_entry`, `reverse_manual_entry`.
- `app/services/accounting/coa.py`: `create_account`, `rename_account`, `set_account_active`, `account_has_movements`, `validate_detail_code`.
- `app/domains/accounting/router.py`: schemas `JournalEntryCreate`, `JournalLineCreate`, `ReverseRequest`, `AccountCreate`; `AccountUpdate` ampliado; endpoints nuevos; `list_accounts` con `has_movements`; `list_journal_entries` con `reversed`/`reversal_of`.
- Frontend: `features/accounting/JournalEntryForm.tsx`, `features/accounting/AccountForm.tsx`, cambios en `AccountingPage.tsx`, `JournalDiary.tsx`, `AccountFieldCell.tsx` (campo `name`), `types/api.ts`.
- Sin migración: no cambia el esquema.

## Pruebas

`tests/test_polizas_manuales.py`:
- Póliza balanceada de tres líneas → 201, folio `Dr-`, aparece en diario y balanza, `source_type="manual"`.
- Descuadre → 400 "no está balanceado"; una línea → 400; línea con cargo y abono → 400.
- Cuenta mayor → 400; cuentas 1100, 1200, 2100, 2200, 1400, 1490 y 2300 → 400 con "Movimientos" y "Patrimonio"; cuenta inactiva → 400.
- Fecha futura → 400; mes cerrado → 400 "cerrado".
- Reverso → 201 con líneas invertidas y `reference="reversal:{id}"`; segundo reverso → 400; revertir el reverso → 400; revertir póliza de un gasto → 400.
- Otra empresa no ve ni revierte la póliza (404).
- Saldos de instrumentos y de cartera no cambian tras una póliza manual (la regla de bloqueo lo garantiza; prueba directa).

`tests/test_catalogo.py`:
- Alta bajo 5000 con código 5210 → 201, tipo EXPENSE, `sat_code` heredado del padre si no se manda.
- Código duplicado, con letras, de 3 dígitos, o que no empieza con el dígito del padre → 400; padre que no es mayor → 400; padre de otra empresa → 404.
- Renombrar sembrada → 200; desactivar sembrada → 400; desactivar nueva sin movimientos → 200 y ya no acepta pólizas (400 en manual); desactivar con movimientos → 400; reactivar → 200.
- `has_movements` verdadero tras una póliza.
- La cuenta nueva con movimientos aparece en balanza, en el catálogo XML del SAT (con su código agrupador) y en el export CONTPAQi del mes.

## Fuera de alcance

Apertura y cierre anual (C-2), tres niveles de catálogo, pólizas manuales de tipo Ingreso o Egreso, propuestas de agente para pólizas (`propose_journal_entry`, fase 5), edición de una póliza (se revierte y se captura otra), borrado físico de cuentas.
