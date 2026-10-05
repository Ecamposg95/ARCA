# Portal de despacho — la cartera del contador

> Sub-proyecto 1 de 7 del frente "ARCA para firmas contables". Aprobado en
> conversación el 2026-10-05.

## Para qué

Emmanuel le va a mostrar ARCA a su contador de confianza (usuario de CONTPAQi)
esta semana. La meta es una alianza con dos modelos posibles:

1. **Ofrecerlo a sus clientes:** el empresario usa ARCA y suma a su contador.
2. **Llevar a sus clientes:** el contador da de alta a sus clientes y los opera él.

Hoy el backend ya soporta que un usuario pertenezca a varias empresas
(`X-Organization-ID`, membresía validada en `app/security/deps.py`), pero la
interfaz sólo deja ver una. Sin una vista de cartera, el contador no puede
evaluar el modelo 2. Este sub-proyecto cierra ese hueco.

**Éxito:** el contador inicia sesión, ve todas sus empresas con un semáforo que
le dice dónde hay trabajo pendiente, entra a cualquiera con un clic y da de alta
una nueva sin cerrar sesión.

## Enfoque

La cartera de un usuario son **las empresas donde tiene membresía**. No hay
tablas ni migraciones nuevas.

Descartado:

- **Entidad "Despacho"** (firma con personal y asignación de clientes a
  auxiliares). Es lo correcto a largo plazo, pero pide migración y un modelo de
  permisos nuevo. Se puede agregar después encima de esto sin rehacerlo.
- **Sólo un selector de empresa.** No da la vista de cartera, que es lo que
  sostiene la alianza.

## Backend

Dominio nuevo `app/domains/portfolio/` (router, service, schemas), registrado en
el `api_router`.

### `GET /api/portfolio`

No usa `X-Organization-ID`: depende de `get_current_user` y recorre únicamente
las membresías de ese usuario. Ninguna consulta acepta un `organization_id` que
venga del cliente.

Respuesta con el sobre estándar `{items,total,limit,offset}`, sin paginar
(igual que la lista de miembros), ordenada por urgencia: rojo, ámbar, verde y
luego por nombre. Cada item:

| Campo | Tipo | Origen |
|---|---|---|
| `organization_id`, `name`, `tax_id`, `business_type` | str | `Organization` |
| `role` | str | `OrganizationMember.role` |
| `cash` | Decimal | saldo de instrumentos de activo, misma regla que `dashboard.summary` |
| `receivable` | Decimal | CxC abiertas y parciales |
| `payable_overdue` | Decimal | CxP abiertas y parciales con `due_date < hoy` |
| `last_closed_period` | `"AAAA-MM"` o null | `PeriodLock` vigente más reciente |
| `previous_month_closed` | bool | `periods.service.is_closed` del mes anterior |
| `pending_proposals` | int | `AgentProposal.status == "PROPOSED"` |
| `status` | `"red"`, `"amber"`, `"green"` | regla de abajo |
| `reasons` | list[str] | frases en español que explican el estado |

Los cálculos de caja y de saldos pendientes se extraen de
`app/domains/dashboard/service.py` a funciones reutilizables; el dashboard y la
cartera llaman a las mismas, para que ambas pantallas muestren la misma cifra.

Los montos se serializan como string, igual que el resto de la API.

### Semáforo

Se evalúa en este orden; gana el primero que aplique.

- **Rojo:** el mes anterior no está cerrado y hoy es después del día 17, o
  `payable_overdue > 0`.
- **Ámbar:** el mes anterior no está cerrado, o `pending_proposals > 0`.
- **Verde:** nada de lo anterior.

`reasons` lista todas las causas que aplican, no sólo la que decidió el color.
Ejemplos: "Septiembre sigue sin cerrar", "$12,400.00 por pagar vencidos",
"3 propuestas por revisar". Una empresa sin pólizas en el mes anterior no tiene
nada que cerrar y no se penaliza por ello (se decide por actividad en el libro,
no por la fecha de alta, para que una empresa migrada con historia sí cuente).

La regla es una función pura (`portfolio_status(...)`) que recibe los datos y la
fecha de hoy, para poder probarla sin base de datos.

### `POST /api/organizations`

Un usuario autenticado crea otra empresa. Cuerpo: `business_name`
(obligatorio), `business_type`, `tax_id`, `initial_cash` (opcionales;
`initial_cash` con `Field(ge=0, allow_inf_nan=False)`).

Llama a `provision_organization` (el mismo arranque del registro: catálogo
contable, categorías, cuenta "Caja") y hace commit. Quien la crea queda como
`OWNER`. Devuelve `OrganizationRead` con 201.

## Frontend

### Empresa activa y rol

- `authStore` guarda la lista de empresas y membresías de `/api/me` además de la
  empresa activa.
- `AppLayout` deja de asumir `OWNER`: el rol sale de la membresía de la empresa
  activa. El backend sigue siendo la autoridad; esto sólo decide qué navegación
  se muestra.
- Cambiar de empresa actualiza `authStore.organization` y **reinicia la caché de
  TanStack Query** (`queryClient.resetQueries()`, que además vuelve a pedir lo
  que esté en pantalla), para que nunca se pinte una cifra de la empresa
  anterior.
- Si la empresa activa guardada en el navegador ya no está entre las del
  usuario (lo sacaron del equipo), se activa la primera que sí tenga.

### Selector de empresa

En el encabezado superior (`AppHeader`), donde hoy va el nombre de la empresa:
la barra lateral sólo navega. Muestra la empresa activa; al abrirlo
lista las demás y un enlace "Ver todas" a `/despacho`. Con una sola empresa se
muestra el nombre sin desplegable.

### Página `/despacho` — "Mis empresas"

- Tabla con una fila por empresa: semáforo, nombre y RFC, rol, caja, por
  cobrar, por pagar vencido, último mes cerrado, propuestas pendientes. Las
  causas del semáforo se leen en la fila, no sólo en un tooltip.
- Clic en la fila: activa esa empresa y lleva a su dashboard.
- Encabezado con conteo por estado ("2 al corriente · 1 por atender · 1 urgente").
- Botón "Nueva empresa" que abre un formulario corto y, al guardar, la agrega a
  la cartera.
- Estado vacío no aplica (todo usuario tiene al menos una empresa); con una sola
  se invita a agregar la segunda.
- Entrada "Mis empresas" en la navegación, visible para todos los roles.
- Al iniciar sesión, un usuario con más de una empresa aterriza en `/despacho`.

Convenciones del repo: tokens semánticos de Tailwind, cifras con `.figures`,
semáforo con la semántica pos/warn/neg (no con el acento teal), copy en español.

## Demo

`scripts/demo_despacho.py` siembra un usuario contador con cuatro empresas, una
por estado:

| Empresa | Estado | Causa sembrada |
|---|---|---|
| A, el propio despacho | verde | mes anterior cerrado, sin pendientes |
| B | ámbar | mes anterior sin cerrar |
| C | rojo | cuentas por pagar vencidas |
| D | ámbar | propuestas de agentes por revisar |

En D el contador entra con rol `ACCOUNTANT` invitado por la dueña (modelo 1);
B y C las dio de alta él y es `OWNER` (modelo 2). Las cuatro llevan operaciones
fechadas en el mes anterior, para que el cierre de mes sea exigible. El script
imprime las credenciales. Como hoy es antes del día 17, B queda en ámbar; después del 17
pasaría a rojo, y el guion lo debe tener en cuenta.

## Pruebas

- `GET /api/portfolio` devuelve sólo las empresas del usuario; otro usuario no
  ve ninguna de ellas.
- Las cifras de la cartera coinciden con las del dashboard de cada empresa.
- `portfolio_status`: un caso por cada regla, incluido el corte del día 17 y la
  empresa sin pólizas en el mes anterior.
- `POST /api/organizations`: la empresa nueva nace con catálogo, categorías y
  "Caja"; el creador es `OWNER`; el saldo inicial entra por el motor contable y
  la balanza cuadra.
- Un `ACCOUNTANT` invitado ve la empresa en su cartera con ese rol.
- Suite completa, `ruff`, `typecheck` y `build` del frontend, y captura de
  pantalla de `/despacho` antes de desplegar.

## Fuera de alcance

- Transferir la propiedad de una empresa del contador al empresario.
- Entidad "Despacho" con personal y asignación de clientes.
- Cifras consolidadas entre empresas.
- Marca del despacho en la interfaz.

## Lo que sigue

Sub-proyecto 2, puente a CONTPAQi (exportar pólizas en el layout de carga por
lotes), con su propia spec. Después, el guion de la demo sobre lo construido.
Importación de CFDI, cédula de impuestos, contabilidad electrónica,
conciliación bancaria y cierre mensual quedan como hoja de ruta para la reunión.
