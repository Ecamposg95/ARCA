# Unidades de negocio y entidad fiscal

_Spec 2026-11-02. Primer bloque del MVP de LaFe (`docs/lafe/BACKLOG.md`, `docs/lafe/HAB-01_matriz.md`, `docs/lafe/HAB-02_inventario.md`). Dominio ONE Accounting (dimensiones del libro)._

## Intención

LaFe opera nueve unidades (matriz, tomas de muestra, unidad móvil, canal Empresas) bajo dos contribuyentes (Liza, persona física con actividad empresarial; Ale, RESICO) con una sola caja y una sola operación. Hoy ONE Finance tiene una dimensión: la empresa. Este bloque agrega dos dimensiones opcionales a cada movimiento, **unidad de negocio** y **entidad fiscal**, para que cajas, ingresos, gastos, traspasos, reportes y el tablero se puedan ver por unidad y por contribuyente sin partir el negocio en varias empresas.

Habilita HU-02 (catálogos), HU-04/05 (sucursal en ingresos y gastos), HU-07 (corte por unidad), HU-11 (filtro por unidad) y HU-19 (tablero por unidad), y RN-03 (cada póliza lleva entidad).

## Objetivos

- Una empresa puede definir N unidades y N entidades. Una empresa sin ninguna sigue exactamente igual que hoy: ningún selector, ningún filtro, ninguna columna nueva visible.
- Cada cuenta de dinero puede pertenecer a una unidad (la caja de Morelos). Cada ingreso, gasto, traspaso, cuenta por cobrar y cuenta por pagar puede llevar unidad y entidad.
- La póliza hereda las dos dimensiones de la operación que la originó, para que balanza, resultados, flujo y tablero se filtren por ellas directamente desde el libro.
- Alias: una unidad conoce los nombres con los que Toronja la llama ("VILLAS DE NUESTRA SEÑORA", "VNSA MOVIL" → Villas / Unidad Móvil). El importador de Toronja (spec posterior) resuelve contra esos alias.

## No objetivos

- Permisos por unidad (el auxiliar que sólo ve su sucursal). Viene con HU-08.
- Consolidación entre empresas y reportes por contribuyente para el SAT con sello. La balanza filtrada por entidad es el insumo; el XML del Anexo 24 sigue siendo por empresa.
- Centros de costo distintos de la unidad.
- Migrar datos existentes de otras empresas: todas arrancan sin unidades ni entidades.

## Anti-objetivos

- Que una empresa con unidades tenga movimientos "huérfanos" sin querer: la unidad se hereda de la cuenta de dinero cuando la operación no la trae, y el formulario la preselecciona.
- Que la dimensión rompa la partida doble o el aislamiento por empresa: unidad y entidad son FK validadas contra la misma `organization_id`; el motor contable no cambia sus reglas, sólo copia dos ids a la póliza.

## Modelo

`business_units` (nuevo, `app/models/business_unit.py`, registrar en `app/models/__init__.py`):
- `id`, `organization_id` (TenantMixin), `name` (255, único por empresa, case-insensitive), `code` (12, único por empresa, mayúsculas, opcional: se deriva del nombre si falta), `kind` en `MATRIZ | TOMA_MUESTRA | UNIDAD_MOVIL | CANAL | OTRA` (default `OTRA`), `active` bool default true, `opened_on` date nullable, `aliases` JSON lista de strings (comparación sin acentos ni mayúsculas), `sort_order` int, AuditMixin.
- Como máximo una unidad `MATRIZ` activa por empresa.

`fiscal_entities` (nuevo, `app/models/fiscal_entity.py`):
- `id`, `organization_id`, `name` (255, único por empresa), `tax_id` (13, nullable, mayúsculas), `regime` (80, nullable, texto libre: "Persona física con actividad empresarial", "RESICO"), `active`, `sort_order`, AuditMixin.

Columnas nuevas, todas nullable, con índice, FK a la tabla correspondiente:
- `financial_accounts.business_unit_id`
- `incomes`, `expenses`, `receivables`, `payables`: `business_unit_id` y `fiscal_entity_id`
- `transactions.business_unit_id` (la de la cuenta de dinero en el momento de registrar; en un traspaso cada pierna lleva la de su cuenta)
- `journal_entries.business_unit_id` y `journal_entries.fiscal_entity_id`

Una sola migración `20261102_01_unidades_entidades.py` con un solo head.

## Reglas

1. **Herencia.** Al crear o pagar un ingreso/gasto sin `business_unit_id`, se toma la de la cuenta de dinero. Si la operación trae una distinta a la de la cuenta, gana la de la operación (un gasto de Morelos pagado desde la caja central). Nada se infiere para `fiscal_entity_id`: si no viene, queda nula ("por asignar").
2. **Póliza.** `record_transaction` acepta `business_unit_id` y `fiscal_entity_id` opcionales y los guarda en la póliza. Las reglas en `rules.py` no cambian; la validación de que los ids pertenecen a la empresa ocurre en el service que llama al motor. El reverso copia las dimensiones de la póliza original. Apertura y cierre anual no llevan dimensiones.
3. **Validación.** Un id de unidad o entidad de otra empresa responde 404 con detalle en español, igual que cualquier recurso ajeno. Una unidad inactiva no se puede asignar a operaciones nuevas, pero conserva su historial y sigue filtrando.
4. **Borrado.** No existe. Se desactiva. Una unidad con cuentas de dinero o movimientos no se puede desactivar si tiene cuentas de dinero activas con saldo distinto de cero (detalle: "Primero traspasa el saldo de sus cajas.").
5. **Alias.** Se guardan como vienen; la búsqueda normaliza (sin acentos, mayúsculas, espacios colapsados). Un alias no puede repetirse entre unidades de la misma empresa.

## API

Prefijo `/api/business-units` y `/api/fiscal-entities`, paginación estándar, errores `{"detail": "..."}` en español. Escritura para OWNER y ADMIN; lectura para cualquier miembro.

- `GET /api/business-units?active=` → `{items,total,limit,offset}` con `id,name,code,kind,active,opened_on,aliases,sort_order,accounts_count`
- `POST /api/business-units` · `PATCH /api/business-units/{id}` (nombre, código, tipo, alias, activa, orden, fecha)
- `GET /api/fiscal-entities` · `POST` · `PATCH /{id}`
- Las listas de ingresos, gastos, movimientos, por cobrar y por pagar aceptan `business_unit_id` y `fiscal_entity_id` como filtro; sus schemas de lectura incluyen `business_unit_id`, `business_unit_name`, `fiscal_entity_id`, `fiscal_entity_name`; los de creación aceptan los ids.
- Cuentas de dinero: `business_unit_id` en creación, edición y lectura.
- Reportes (`/api/reports/*`), balanza, diario y dashboard aceptan los dos filtros; cuando no vienen, el resultado es idéntico al actual (todas las pruebas existentes siguen verdes sin tocarse).
- `/api/me` o `GET /api/organizations/current` exponen `has_business_units` y `has_fiscal_entities` para que el front sepa si muestra selectores.

## Interfaz

- **Configuración → "Unidades y contribuyentes"**: dos tarjetas. Lista editable de unidades (nombre, tipo, código, alias como chips, activa) y de contribuyentes (nombre, RFC, régimen). Empty state con CTA: "Si tu negocio tiene sucursales o más de un contribuyente, dalos de alta aquí para ver tus números por cada uno."
- **Selectores** en los formularios de ingreso, gasto, cuenta por cobrar, cuenta por pagar y cuenta de dinero; solo aparecen si la empresa tiene unidades/entidades. Preselección: la unidad de la cuenta de dinero elegida.
- **Filtros** (chip "Unidad: Morelos ×", "Contribuyente: Liza ×") en Movimientos, Ingresos, Gastos, Por cobrar, Por pagar, Reportes y en el tablero de Inicio. El filtro de unidad del tablero cambia saldos, series y gasto por categoría.
- Columna "Unidad" en las tablas cuando hay unidades. Copy en español, tokens semánticos, cifras con `.figures`.

## Semilla de LaFe

`scripts/lafe_seed.py --url --email --password` (idempotente, por nombre): 10 unidades con tipo y alias de Toronja exactamente como la hoja 13 del Registro Contable (Centro Médico MATRIZ con alias "CENTRO MÉDICO", "CENTRO MOVIL"→Unidad Móvil, "VILLAS DE NUESTRA SEÑORA" y "VNSA MOVIL"…; Cumbres inactiva; Empresas CANAL; "Liza Díaz de León" y "Soporte Técnico del Sistema" como alias de "Laboratorio / Dirección"); 2 contribuyentes (Liza — Persona física con actividad empresarial; Ale — RESICO); caja central y una caja de efectivo por unidad con ventas (ligadas a su unidad). Sin saldos.

## Pruebas (mínimo)

Tenant isolation de las dos tablas y de los filtros; herencia de unidad desde la cuenta; dimensiones copiadas a la póliza y al reverso; filtro en balanza y estado de resultados suma exactamente lo de esa unidad; empresa sin unidades: respuestas idénticas a las actuales; alias normalizado; matriz única; desactivar con saldo bloqueado.

## Lo que queda al implementador

Nombres de componentes, orden de las columnas, si el filtro del tablero vive en la URL. Todo lo demás está decidido arriba; lo que no cuadre con un invariante de `AGENTS.md` se resuelve a favor del invariante y se anota en el PR.
