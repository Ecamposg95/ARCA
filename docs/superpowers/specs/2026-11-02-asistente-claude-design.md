# Asistente ONE Finance sobre Claude (plataforma agéntica)

_Spec 2026-11-02. Dominio ONE Intelligence. Calcado del agente en plataforma de Atlas Cortex (`atlas-cortex/app/agents/runtime.py`, `cortex_prompt.py`, `routers/agente.py`, `models/agente.py`); la referencia del API es la skill `claude-api` (modelos, thinking adaptativo, caché, strict tools)._

## Intención

Que cualquier usuario de ONE Finance pregunte en español sobre su negocio ("¿cuánto hay en caja?", "¿qué vence esta semana?", "registra el gasto de la renta de Morelos") y el sistema conteste con datos reales del libro y proponga acciones que el humano aprueba. Es la primera pieza de "todo el sistema agéntico": todo lo que después automatice (resumen del lunes, clasificar importaciones, narrar briefs) corre sobre este runtime, este catálogo de herramientas, esta bandeja y este medidor de costo.

LaFe aporta $200 USD de API. La llave se conecta **al final**: toda la plataforma se construye, prueba y despliega sin llave, y al ponerla en Railway (`ANTHROPIC_API_KEY`) el asistente aparece.

## Decisiones tomadas

- **Vive en ARCA**, no detrás de Cortex. Cortex sigue consumiendo `GET /api/agent/tools` por su conexión; nada de eso cambia.
- **Modelo `claude-opus-5-5`**, esfuerzo `medium`, thinking adaptativo (sin `budget_tokens`), `max_tokens` 16000, sin `temperature`. Variables `AI_MODEL`, `AI_EFFORT` para cambiarlo sin código. Loop manual (no el tool runner del SDK): cada llamada a herramienta pasa por el dispatch autorizado y queda auditada antes de volver al modelo, igual que Cortex.
- **Caché de prompt**: el `system` (estable, sin fecha dentro) y la lista de herramientas (orden determinista) llevan `cache_control`; la fecha de hoy y el contexto de la empresa van en el primer mensaje de usuario, no en el system, para no invalidar la caché.
- **Herramientas**: el catálogo de 18 que ya expone `app/domains/agent_api` (14 lectura + 4 `propose_*`), con `strict: true` y `additionalProperties: false`. El asistente corre **como el usuario logueado** con su membresía y rol, no con una llave `ak_`. Las `propose_*` crean `AgentProposal` con `agent_key_id` nulo y `origin = "assistant:{conversation_id}:{tool_use_id}"`; aprobar y rechazar es lo que ya hace la bandeja.
- **Escrituras**: una propuesta por turno; el modelo recibe como `tool_result` "Propuesta creada, pendiente de aprobación: {summary}" y termina el turno. La tarjeta en el chat aprueba o rechaza llamando a los endpoints de propuestas existentes. Nunca se escribe al libro desde el loop.
- **Presupuesto medido en USD por empresa y mes.** Tabla de uso con tokens y costo; tope por empresa; al agotarse, el asistente responde con un mensaje claro y no llama al API.
- **Sin llave**: `GET /api/assistant/status` responde `available: false, reason: "sin_llave"`; la página muestra "El asistente se activa cuando se conecte la llave de Claude" y no hay 500 en ningún lado.
- **Sin red en pruebas**: el runtime recibe `client` inyectable; las pruebas usan un cliente falso con respuestas guionadas (texto, `tool_use`, `max_tokens`, `refusal`).

## Fuera de alcance (olas siguientes)

Streaming al navegador; briefs narrados; resumen del lunes; clasificación asistida de importaciones; memoria entre conversaciones; subida de archivos al chat; llave por empresa cifrada.

## Modelo

`app/models/assistant.py` (registrar en `__init__`):
- `assistant_conversations`: `id`, `organization_id`, `user_id`, `title` (120, nullable; se deriva del primer mensaje), `busy_since` (timestamp nullable: un turno en curso bloquea otro en la misma conversación), AuditMixin.
- `assistant_messages`: `id`, `conversation_id`, `organization_id`, `role` (`user | assistant`), `blocks` JSON (el contenido tal cual se manda y se recibe del API, incluidos bloques `thinking` y `tool_use`/`tool_result`, para reenviar el historial íntegro), `text` (lo que se muestra), `steps` JSON (`[{name, ok, summary}]`), `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `cost_usd` Numeric(10,6), `stop_reason` (30), `created_at`.
- `assistant_actions`: `id`, `message_id`, `conversation_id`, `organization_id`, `tool_use_id`, `tool_name`, `args` JSON, `summary` (300), `proposal_id` (FK `agent_proposals`, nullable), `status` (`PENDING | APPROVED | REJECTED`), `resolved_at`.
- `ai_usage`: `id`, `organization_id`, `user_id` nullable, `feature` (`assistant` por ahora), `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `cost_usd`, `created_at` con índice `(organization_id, created_at)`. Una fila por llamada al API (no por turno).
- `organizations.ai_budget_usd` Numeric(10,2) nullable; `null` = usa `AI_BUDGET_DEFAULT_USD` (config, default 20). `organizations.ai_enabled` bool default true.

Migración `20261102_02_asistente.py` (misma cadena que la de unidades; un solo head).

## Costo

`app/services/ai/pricing.py`: tabla por modelo en USD por millón (opus-5-5: entrada 4, salida 20, lectura de caché 0.20, escritura de caché 5 = 1.25×; sonnet-5-5: 2 / 10 / 0.20 / 2.5; haiku-5-5: 0.10 / 0.50 / 0.01 / 0.125). `cost_usd(model, usage)` con Decimal. Un modelo desconocido cobra como opus.

`consumo_del_mes(org)` = suma de `ai_usage.cost_usd` del mes calendario en `America/Mexico_City`. Antes de cada llamada al API: si `consumo + estimación mínima >= tope` → no llama y el turno termina con texto "Se agotó el presupuesto del asistente de este mes ({consumo} de {tope} USD). Pídele a Atlas que lo amplíe." Estado `stop_reason = "budget"`.

## Runtime (`app/services/ai/`)

- `client.py`: `build_client()` devuelve `anthropic.Anthropic()` si hay `ANTHROPIC_API_KEY`, si no `None`. `anthropic>=0.69` en `requirements.txt`.
- `prompt.py`: `system_prompt(tools)` en español, estable: quién es (el asistente de ONE Finance, corre sobre Claude de Anthropic y lo dice si le preguntan), reglas de Cortex adaptadas (fundamentar en herramientas, nunca inventar ids ni cifras, una escritura por turno con argumentos resueltos, errores de autorización no se reintentan, errores de argumentos se corrigen una vez, respuestas breves en markdown ligero, cifras con dos decimales y signo de pesos, fechas AAAA-MM-DD), y el listado de herramientas con una línea cada una (lectura y escritura separadas).
- `runtime.py`: `run_turn(db, user, org_id, conversation, user_text, client, *, max_iterations=12)`. Arma el historial desde `assistant_messages.blocks`; mensaje inicial de contexto ("Hoy es lunes 2026-11-02. Empresa: Laboratorios La Fe. Usuario: Liza (ADMIN)."); llama `client.messages.create(model, max_tokens, system=[{text, cache_control}], thinking={"type":"adaptive"}, output_config={"effort"}, tools=[... último con cache_control], messages)`. Por cada `tool_use`: valida el input contra el schema, despacha por el registro de `agent_api` con un `AgentContext` construido desde la membresía del usuario (scopes completos de lectura; `propose` permitido), audita en `AgentActionLog` con `agent_key_id` nulo, devuelve `tool_result` (`is_error` cuando falla). Todas las `tool_result` de una iteración van en un solo mensaje de usuario. Si la herramienta es `propose_*`: crea la `AssistantAction` y corta el loop después de esa iteración. `stop_reason` `max_tokens` → texto "Me quedé sin espacio; pregunta de nuevo más acotado."; `refusal` → "No puedo ayudar con eso."; tope de iteraciones → "No logré terminar; intenta con una pregunta más corta.". Cada llamada registra `ai_usage`.
- Thinking blocks se guardan y reenvían tal cual (modelo fijo por conversación; si `AI_MODEL` cambia, las conversaciones viejas se siguen pero el API descarta esos bloques sin cobrar).

## API (`app/domains/assistant/`)

- `GET /api/assistant/status` → `{available, reason, model, budget_usd, spent_usd, remaining_usd}` (cualquier miembro).
- `GET /api/assistant/conversations` (del usuario, en la empresa actual; `{items,total,...}`), `POST` (crea vacía), `GET /{id}` (mensajes con `text`, `steps`, acciones y costo), `DELETE /{id}`.
- `POST /api/assistant/conversations/{id}/messages` `{text}` → síncrono, devuelve el mensaje del asistente. 409 si la conversación está `busy`; 503 si no hay llave; 402 si no hay presupuesto (con el mismo texto que el mensaje).
- `POST /api/assistant/actions/{id}/approve` y `/reject` → delegan en el service de propuestas; devuelven la acción actualizada. Después de aprobar, el siguiente turno recibe como contexto "La propuesta X fue aprobada y ejecutada (folio …)".
- `GET /api/assistant/usage?month=AAAA-MM` (OWNER/ADMIN): total y desglose por usuario y por día.
- `PATCH /api/organizations/current` acepta `ai_budget_usd` y `ai_enabled` (solo OWNER).

## Interfaz

- Página `/asistente` (ruta en el nav, sección principal, ícono `Sparkles`): lista de conversaciones a la izquierda (móvil: cajón), hilo a la derecha. Mensaje del asistente en markdown ligero; debajo, chips de pasos ("Consulté saldos · Busqué por pagar"); tarjeta de acción pendiente con resumen, Aprobar / Rechazar, y estado después. Caja de texto con Enter para enviar; mientras responde, indicador "pensando…" y la caja bloqueada.
- Empty state con tres preguntas de ejemplo clicables ("¿Cuánto dinero tengo disponible?", "¿Qué pagos vencen esta semana?", "Registra un gasto de $1,200 de papelería pagado de caja").
- Sin llave: la página existe y muestra el aviso; el botón del encabezado también.
- Configuración → Agentes: tarjeta "Asistente de Claude" con modelo, gasto del mes vs tope, barra, y edición del tope para OWNER.
- Botón "Asistente" en el encabezado (icono) que navega a `/asistente`.

## Pruebas (mínimo)

Sin llave: `status.available=false` y 503 en mensajes. Cliente falso: turno de solo texto; turno con dos lecturas en paralelo (una sola `tool_result` message); turno con `propose_expense` crea `AssistantAction` + `AgentProposal` y corta; aprobar ejecuta el service real y el gasto existe; tenant isolation (otra empresa no ve la conversación; una herramienta no cruza datos); presupuesto agotado no llama al cliente (el fake registra 0 llamadas) y devuelve 402; `ai_usage` registra una fila por llamada con el costo correcto según la tabla; `max_tokens` y `refusal` producen los textos definidos; conversación ocupada responde 409.

## Lo que queda al implementador

Estilo de la página dentro de los tokens; cómo se deriva el título; si el historial largo se recorta por número de mensajes (sugerido: últimos 40 bloques) antes de pensar en compaction. No cambiar el catálogo de herramientas ni sus schemas en esta ola.
