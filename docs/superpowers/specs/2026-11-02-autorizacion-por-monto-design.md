# Autorización por monto

_Spec 2026-11-02. Dominio ONE Payables. Cubre HU-08 (autorizaciones por monto) y la restricción del auxiliar de HU-01. Decisión pendiente 1 del backlog de LaFe: se arranca con umbral $100,000 MXN inclusive y límite del auxiliar $2,000, ambos configurables; LaFe los confirma después sin tocar código._

## Intención

En LaFe, Liza (dirección) autoriza los movimientos grandes; Abraham (administración) registra y programa pagos; un auxiliar captura cosas chicas. Hoy cualquier rol de escritura registra cualquier monto. Este bloque agrega un umbral por empresa: lo que lo alcanza no se registra, queda **pendiente de autorización** en la bandeja que ya existe (propuestas), y sólo quien tiene facultad de autorizar lo aprueba o rechaza con motivo. Lo pendiente nunca cuenta como pagado ni toca saldos.

## Objetivos

- Umbral y límite configurables por empresa; facultad de autorizar por miembro.
- Gastos, pagos a cuentas por pagar y traspasos que alcancen el umbral van a la bandeja; aprobar ejecuta el service real con el usuario que lo capturó como autor y el autorizador como `reviewed_by`.
- El auxiliar (rol MEMBER) no puede capturar por encima de su límite ni ver la configuración.
- Decisión, responsable, fecha y motivo de rechazo quedan guardados (ya existen en `agent_proposals`).

## No objetivos

Flujos de varios niveles; autorización de ingresos o de cuentas por cobrar; notificaciones (decisión 7 pendiente); que la aprobación controle un pago externo (sólo documenta y registra).

## Modelo

- `organizations`: `approval_threshold` Numeric(14,2) nullable (null = sin autorización), `member_capture_limit` Numeric(14,2) nullable (null = sin límite).
- `organization_members`: `can_authorize` bool default false. OWNER siempre autoriza aunque esté en false.
- `agent_proposals`: `PROPOSAL_KINDS` gana `PAYABLE_PAYMENT` y `TRANSFER` si no existen; el payload de cada kind es exactamente el schema Create del dominio correspondiente; `origin` = `"approval:{user_id}:{uuid}"`; nuevo campo `requested_by` (FK users, nullable) para distinguir al que captura del `agent_key_id`/asistente. `kind` existente `EXPENSE` se reutiliza.
- Migración `20261102_05_autorizacion.py` (`down_revision` = head de tu worktree).

## Reglas

1. **Qué se evalúa.** Monto total de la operación (`amount`) contra `approval_threshold`, **mayor o igual**. Aplica a: crear gasto pagado (status PAID) o pagar un gasto pendiente; registrar pago (total o parcial) a una cuenta por pagar; traspaso entre cuentas de dinero. Un gasto que se crea `PENDING` (no pagado) no se evalúa al crearse: se evalúa al pagarlo.
2. **Quién salta la bandeja.** Si quien captura tiene `can_authorize` (o es OWNER), la operación se registra directo y se audita como autoautorizada (`AgentActionLog` con tool `self_authorized_{kind}`, o una tabla ligera de auditoría si ya existe un patrón mejor; no inventar una tercera cosa).
3. **Qué pasa cuando no.** El endpoint de creación responde **202** con `{"pending_approval": true, "proposal_id": ..., "detail": "Se envió a autorización: supera el umbral de $100,000.00."}` y no crea nada más. La propuesta lleva `summary` legible ("Gasto de $120,000.00 a Adrián Estrada · Reactivos"), `evidence` con quién la capturó y cuándo, y `requested_by`.
4. **Aprobar.** Solo OWNER o miembro con `can_authorize` (403 "Solo quien autoriza puede aprobar."). Ejecuta el service real con `created_by = requested_by` y guarda `reviewed_by` = autorizador. Si al aprobar la operación ya no es válida (cuenta inactiva, CxP ya pagada, mes cerrado), la propuesta se queda `PROPOSED` y el error vuelve en español. Rechazar exige motivo (ya lo hace la bandeja).
5. **Auxiliar.** Rol MEMBER: si `member_capture_limit` existe y el monto lo supera → 403 "Ese monto necesita a un administrador." (antes de evaluar el umbral). MEMBER no ve `GET /api/organizations/current/approvals` ni puede editarlo.
6. **Configuración.** `GET/PATCH /api/organizations/current/approvals` `{approval_threshold, member_capture_limit}` OWNER/ADMIN; `PATCH /api/organizations/current/members/{id}` acepta `can_authorize` (OWNER/ADMIN; nadie se lo quita al OWNER). `/api/me` expone `can_authorize` del miembro actual.
7. **Bandeja.** `GET /api/proposals` acepta `source=approval|agent|assistant|system` (derivado de `origin`/`agent_key_id`/`requested_by`) y devuelve `requested_by_name`. El conteo del badge de Propuestas incluye las de autorización.
8. **Montos pendientes no existen para nadie:** no entran en listas de gastos, CxP, movimientos, saldos, reportes ni en el asistente (el asistente las ve sólo a través de `list_proposals`, que ya existe). Las páginas de Gastos y Por pagar muestran un aviso "N operaciones esperan autorización" con enlace a Propuestas cuando el usuario puede autorizar.

## Interfaz

- **Configuración → "Autorizaciones"**: umbral (vacío = sin autorización), límite del auxiliar, y en la tarjeta de Equipo un interruptor "Autoriza" por miembro (OWNER aparece fijo). Texto de ayuda: "Lo que alcance el umbral se envía a quien autoriza antes de registrarse."
- **Formularios** de gasto, pago a proveedor y traspaso: al enviar, si la respuesta es 202, toast "Se envió a autorización de {nombre(s) de quien autoriza}" y el formulario se cierra. Si es 403 por límite, mensaje en el formulario.
- **Propuestas:** pestaña o filtro "Por autorizar" con quién la capturó, monto, concepto, cuenta; Aprobar / Rechazar con motivo (lo que ya existe), y el badge del nav sube.

## Pruebas (mínimo)

Umbral inclusive; gasto bajo el umbral se registra; igual o arriba va a bandeja con 202 y no mueve saldos; OWNER y `can_authorize` registran directo; MEMBER arriba de su límite 403 antes del umbral; aprobar ejecuta con `created_by` del capturador y saldos correctos; rechazar exige motivo; aprobar sin facultad 403; pago parcial a CxP arriba del umbral va a bandeja; traspaso arriba del umbral va a bandeja; propuesta ajena de otra empresa 404; `source=approval` filtra; gasto PENDING no se evalúa hasta pagarlo; mes cerrado al aprobar deja la propuesta viva con error en español.

## Lo que queda al implementador

Si el 202 devuelve el `OrganizationRead` completo o sólo la propuesta; cómo se calcula "quién autoriza" para el toast (nombres de miembros con facultad). Nada más.
