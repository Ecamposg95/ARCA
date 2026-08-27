# Guion del demo de foro — ARCA

**Duración objetivo:** 15 minutos (elástico entre 10 y 20).
**Tesis:** Atlas construye software serio. ARCA es la prueba.
**Audiencia:** mixta — hay quien entiende de contabilidad, quien entiende de software y quien no entiende de ninguna de las dos.

La regla que ordena todo el guion: **cada afirmación se demuestra en pantalla en los siguientes diez segundos.** Nada de láminas con promesas.

---

## Antes de subir al escenario

Checklist, en este orden. Toma cinco minutos.

1. **Sembrar el escenario** (una empresa nueva, con historia):

   ```bash
   python scripts/demo_forum.py --url https://arca-production-d769.up.railway.app
   ```

   Guarda lo que imprime: correo, contraseña, llave de agente y los dos folios que vas a citar en vivo.

2. **Registrar el MCP antes del demo, nunca en vivo:**

   ```bash
   claude mcp add arca \
       --env ARCA_URL=https://arca-production-d769.up.railway.app \
       --env ARCA_API_KEY=<la llave que imprimió el script> \
       -- /mnt/d/Devs/ARCA/.venv/bin/python /mnt/d/Devs/ARCA/tools/arca_mcp.py
   ```

   Rutas absolutas, no relativas: el servidor arranca con el directorio de trabajo
   de Claude Code, no con el del proyecto. Confirma con `claude mcp list` que diga
   `arca: ... ✔ Connected`, y **reinicia Claude Code** para que cargue las herramientas.

3. **Ensayar el acto 4 completo una vez** con el escenario recién sembrado, y después **volver a sembrar** para que la bandeja de Propuestas quede vacía al empezar.

4. **Dejar abiertas cuatro pestañas**, en este orden: Inicio · Gastos · Contabilidad · Propuestas. Una quinta con la terminal de Claude Code.

5. **Tema claro**, zoom del navegador al 110%, **ventana de 1600×900 o más** — abajo de eso la tabla de Por cobrar necesita scroll horizontal y se ve mal en proyector.

### Datos del escenario sembrado

| Dato | Valor |
|---|---|
| Empresa | Atlas Software Consulting |
| Correo | `demo08270644@atlas.mx` / `demoforo2026` |
| Disponible | $1,007,009 |
| Deuda en tarjetas | $34,800 |
| Por cobrar | $139,200 (vencido $52,200) |
| Por pagar | $15,080 |
| Proyección a 90 días | $1,131,129 |
| Pólizas en el libro | 57, balanza cuadrada |
| Activos fijos | $459,778 en libros |
| Deuda de créditos | $279,689 |
| Póliza de la tarjeta | `Eg-2026-08-0007` |
| Factura F-0087 | `Dr-2026-08-0004` (registro) e `Ig-2026-08-0004` (cobro parcial) |

Los montos son reproducibles: el script usa una semilla fija. Si un número no coincide con esta tabla, volviste a sembrar y cambió algo — vuelve a leer la salida del script antes de citar cifras.

---

## Acto 0 — La frase de apertura · 0:00 – 0:45

**En pantalla:** el tablero de Atlas Software Consulting, ya cargado.

> "Toda empresa hace dos cosas al mismo tiempo: opera y se contabiliza. El dueño sólo vive la primera. La segunda le llega dos meses tarde, en un PDF que no entiende, hecho por alguien que no estuvo ahí.
>
> Esto es ARCA. El dueño administra su negocio; ARCA traduce lo que hace a finanzas y contabilidad. Y lo va a hacer aquí, en vivo, con la aplicación que está corriendo en producción."

**Por qué funciona:** nombra el problema en el lenguaje de todos, y promete demostración en vez de argumento.

---

## Acto 1 — Nace una empresa · 0:45 – 3:00

**En pantalla:** cerrar sesión, ir al registro, crear una empresa en vivo. Tres campos: nombre del negocio, giro, efectivo con el que arranca.

> "Voy a fundar una empresa delante de ustedes. Nombre, giro, y con cuánto dinero empieza. Nada más."

Envía. **La pantalla lo dice sola**: "Tu contabilidad ya existe — no llenaste un solo campo contable, y aun así: 32 cuentas, póliza de apertura `Dr-2026-08-0001`, cargos = abonos ✓". Déjala respirar tres segundos: es el producto haciendo tu trabajo de presentador.

> "No llené un solo campo contable. Y esta empresa que tiene doce segundos de vida ya tiene catálogo, categorías y su póliza de apertura con la balanza cuadrada."

Entra al tablero y, si quieres rematar, abre **Contabilidad**: el libro diario ya muestra la póliza de apertura seleccionada a la derecha.

> "Esto no es cosmético. Es el punto de partida de una contabilidad formal, y se creó solo porque el sistema sabe qué significa 'fundar una empresa'."

**Vuelve a Atlas Software Consulting** (cerrar sesión, entrar con el correo sembrado).

> "Para no verlos operar cuatro meses en vivo, me cambio a una empresa que ya lleva un rato andando."

**Plan B:** si el registro falla, quédate en Atlas Software Consulting y muestra Contabilidad → la póliza de apertura de esa empresa. El punto es el mismo; sólo pierdes el efecto de verlo nacer.

**No digas:** "configuración cero". Alguien del público sabe que una empresa real necesita ajustar su catálogo, y tiene razón.

---

## Acto 2 — Hablo como empresario · 3:00 – 6:00

**En pantalla:** Inicio.

> "Esta consultora factura alrededor de 380 mil al mes. Miren cómo está contada la información: **Disponible, un millón siete mil. Deuda en tarjetas, treinta y cuatro mil ochocientos.** No dice 'activo circulante'. Dice cuánto tienes y cuánto debes."

Baja al panel de cartera.

> "Por cobrar: ciento treinta y nueve mil. **De esos, cincuenta y dos mil ya están vencidos** — y el sistema te lo dice en rojo sin que preguntes."

Baja a *Lo que viene · próximos 90 días*.

> "Y esta es la pregunta que de verdad quita el sueño: ¿me va a alcanzar? Aquí no hay pronóstico ni modelo predictivo: hay compromisos con fecha. Lo que ya facturaste, lo que ya te comprometiste a pagar, cada uno en su día de vencimiento. **Hoy tienes un millón siete mil; con lo comprometido, en 90 días quedarías con 1.13 millones.** Si en algún momento el saldo cruzara a cero, te diría exactamente qué día."

**La frase que ancla el acto:**

> "Ninguna de estas cuatro cifras usa una palabra de contabilidad. Y las cuatro salen de una contabilidad formal."

**Plan B:** si la proyección tarda en cargar, recarga una vez. Si no aparece, sáltala y anúnciala en el acto 5 como parte de lo construido — no la describas como si estuviera en pantalla.

---

## Acto 3 — El reveal contable · 6:00 – 9:30

Aquí se gana a la mitad del público que entiende de contabilidad. Tres golpes, en orden.

### Golpe 1 — La tarjeta es deuda, no gasto pagado

**En pantalla:** Gastos → "Licencias anuales del equipo", $34,800, pagado con AMEX. Abre **Póliza**.

> "Compré licencias con la tarjeta corporativa. Casi todos los sistemas de este tamaño te bajan el saldo del banco. Aquí no se tocó el banco: **cargo a Software 30,000, cargo a IVA acreditable 4,800, y abono a Tarjetas de crédito 34,800.** La tarjeta es un pasivo. Gasté dinero que todavía no salgo a pagar, y el sistema lo sabe."

Vuelve al tablero y señala *Deuda en tarjetas: $34,800*.

> "Por eso esa cifra existe en la pantalla principal. No es un adorno: es el otro lado de esta póliza."

### Golpe 2 — El IVA se causa cuando el dinero se mueve

**En pantalla:** Por cobrar → clic en el concepto de la factura F-0087 ($174,000, cobrada a la mitad). El panel lateral muestra los días al vencimiento, **el cobro de $87,000 en su historial**, y las dos pólizas: la del registro (`Dr-2026-08-0004`) y la del cobro parcial (`Ig-2026-08-0004`). Habla de la segunda.

> "Esta factura es de ciento setenta y cuatro mil, con veinticuatro mil de IVA. Me pagaron la mitad: ochenta y siete mil. Vean qué pasó con el impuesto: **de los veinticuatro mil, se movieron exactamente doce mil** de 'IVA trasladado pendiente de cobro' a 'IVA trasladado cobrado'."

> "En México el IVA se causa cuando efectivamente se cobra, no cuando se factura. Esa regla está aquí adentro, en cuatro cuentas separadas, y se aplica sola en cada cobro parcial."

### Golpe 3 — Todo cuadra

**En pantalla:** Contabilidad. El libro diario es lista + póliza lado a lado: baja con ↑↓ tres o cuatro pólizas para que se vea que TODAS cuadran, y cierra en la **Balanza**.

> "Cincuenta y siete pólizas. Cargos y abonos, iguales al centavo. Cada una nació de una operación que un empresario entendería: cobré, pagué, facturé. **Nadie escribió una póliza a mano en toda esta demostración**, y la contabilidad está completa."

**Plan B:** si el modal de la póliza no abre, ve a Contabilidad y busca el folio `Eg-2026-08-0007` en el libro diario. Es la misma póliza, dos clics más lejos.

**No digas:** "esto reemplaza a tu contador". Di, si te preguntan: *"esto le entrega a tu contador un libro que ya cuadra, en vez de una caja de tickets."*

---

## Acto 4 — El momento agéntico · 9:30 – 13:00

El acto que justifica la palabra "evolutiva". **El MCP ya debe estar registrado desde antes.**

**En pantalla:** la terminal de Claude Code.

> "ARCA publica sus operaciones como herramientas para agentes. No es un chat pegado encima: es la misma aplicación, con una llave que fija la empresa y los permisos."

Escribe en Claude Code, en voz alta:

> `¿Cómo va la empresa este mes? Y registra la suscripción anual de Figma, 18,560 con IVA, pagada con la AMEX.`

Mientras el agente trabaja:

> "El servidor MCP no tiene ninguna herramienta escrita a mano. Cuando arranca, **le pregunta a ARCA qué sabe hacer** y publica exactamente eso: hoy son dieciocho herramientas. El día que ARCA gane un módulo, el agente lo ve sin que nadie toque una línea de ese archivo. Eso es lo que quiere decir 'evolutiva'."

El agente responde con las cifras reales del mes y avisa que dejó una propuesta.

> "Y aquí está lo importante: **el agente no registró nada.** Su llave sólo le permite leer y proponer."

**Cambia a la pestaña de Propuestas.** Ahí está, con quién la hizo y por qué.

> "Escribir es una decisión humana. Yo la reviso —concepto, monto, IVA, con qué se paga— y yo apruebo."

Aprueba. Ve a **Contabilidad**.

> "Y en ese instante nació la póliza: **Software 16,000, IVA acreditable 2,560, contra Tarjetas de crédito 18,560.**"

Vuelve al tablero. Señala la deuda en tarjetas.

> "Y la deuda pasó de treinta y cuatro mil ochocientos a **cincuenta y tres mil trescientos sesenta**. Miren el disponible: **no se movió un peso**, porque se pagó con tarjeta. Un agente propuso, una persona aprobó, y la contabilidad se escribió sola. Ese es el orden correcto de las tres cosas."

**Ritmo medido en el ensayo:** el turno del agente contra producción tarda unos **4 segundos** de red (18 herramientas, cuatro llamadas), y la aprobación responde en **menos de un décimo de segundo**. Lo que marca el paso del acto es el modelo pensando, no ARCA. La póliza nueva queda **al tope del libro diario**, así que en Contabilidad se ve sin buscar.

### Plan B del acto 4 — en tres niveles

| Si falla | Haz esto | Qué se pierde |
|---|---|---|
| El modelo tarda o responde mal | Espera diez segundos y repite la instrucción una vez. | Nada. |
| El cliente MCP no conecta | En otra terminal: `python scripts/demo_plan_b.py --url https://arca-production-d769.up.railway.app --key <llave>` | Sólo el modelo eligiendo la herramienta. Es la misma llamada, con la misma llave y los mismos permisos — dilo así, en voz alta. |
| No hay red | Corre ARCA local con el escenario sembrado en `localhost:8000` y repite el plan B contra esa URL. | El detalle de que corre en producción. |

Frase para cubrir cualquiera de los tres, sin disimular:

> "El modelo no me está respondiendo, así que voy a hacer la llamada que el modelo haría. Lo que importa de este acto no es que la máquina adivine: es que **sólo puede proponer**."

---

## Acto 5 — La evidencia de ingeniería · 13:00 – 15:00

**En pantalla:** la terminal. Corre la suite: `pytest -q`.

Mientras corre:

> "Todo lo que vieron se construyó en dos días, y no es un prototipo. Son **205 pruebas automatizadas**, doce migraciones de base de datos, más de 80 endpoints — y del otro lado **Atlas Cortex con 1,650 pruebas**: dos productos que se hablan."

Cuando termina en verde:

> "Doscientas cinco en verde."

> "Y quiero mostrarles la que más orgullo me da. Cuando descubrimos que las tarjetas de crédito estaban contadas como si fueran efectivo, **no borramos la base de datos**: escribimos una migración que corrige los saldos históricos, la ensayamos contra datos que ya existían, y la subimos. Los datos anteriores siguen ahí y ahora están bien."

**Cierre:**

> "Push a la rama principal, y en tres minutos está en producción. La aplicación que acaban de ver es la que está corriendo ahora mismo.
>
> Esto es lo que quería decirles: **una plataforma financiera completa, con contabilidad formal, abierta a agentes, se puede construir en días.** No porque el problema sea fácil, sino porque así trabajamos en Atlas. Si su empresa tiene un problema de este tamaño, ya saben cómo se ve la respuesta."

**Plan B:** si la suite falla o tarda, no la corras en vivo — ten una captura de la última corrida en verde. Nunca corras pruebas en escenario sin haberlas corrido cinco minutos antes.

---

## Si tienes más tiempo · dos actos opcionales

El guion de 15 minutos no los incluye. Van aquí porque en una sesión de 20 o en
una reunión uno a uno son los que más preguntas provocan.

### Patrimonio · 2 minutos

**En pantalla:** Patrimonio → Activos fijos.

> "Una camioneta de 420 mil no es gasto de marzo. Se usa cuatro años, y ARCA la
> lleva a resultados poco a poco: **nueve mil ciento once pesos al mes** entre
> los dos activos. Aquí dice lo que costó, lo que llevas depreciado y **lo que
> vale hoy**."

Cambia a Préstamos, abre **Tabla**.

> "Y aquí está la que más gente se equivoca: el pago de un crédito **no es
> gasto**. De estos quince mil quinientos, cinco mil quinientos son intereses y
> diez mil bajan la deuda. Miren cómo el interés va cayendo mes con mes mientras
> la cuota sigue igual. Si tratas el pago completo como gasto, tu resultado está
> mal y tu deuda nunca baja en los libros."

### Proyectos · 1 minuto

**En pantalla:** Proyectos.

> "Dos trabajos del mismo trimestre. Este dejó **51% de margen**. Este otro
> **perdió 40%**. Misma empresa, mismo equipo. Sin esta pantalla, los dos se
> mezclan en el estado de resultados y el mes se ve bien."

Señala el panel de abajo.

> "Y esto es honestidad del sistema: dice cuánta parte del negocio **todavía no
> se mide** por proyecto."

---

## Preguntas que van a hacer

**"¿Esto sustituye a mi contador?"**
No. Le entrega un libro que ya cuadra en vez de una caja de tickets. El contador deja de capturar y empieza a revisar.

**"¿Es CFDI? ¿Timbra facturas?"**
Todavía no. Hoy registra la operación y la contabilidad; la conexión con el SAT es el siguiente paso natural, y la arquitectura ya la contempla.

**"¿Y si el agente se equivoca?"**
No puede registrar. Su llave sólo lee y propone; escribir requiere que una persona apruebe. Además, cada propuesta queda con su autor y su motivo.

**"¿Multiempresa?"**
Sí, desde el primer día. Cada dato lleva su organización y hay pruebas específicas de que una empresa no puede ver la otra.

**"¿Cuánto costaría para mi empresa?"**
No lo contestes con un número en el escenario. *"Depende del alcance; con gusto lo vemos con calma."*

---

## Lo que no debes decir

- "Inteligencia artificial que lleva tu contabilidad sola." Es falso y contradice el acto 4.
- "Reemplaza a tu ERP." No lo hace, y hay alguien en el público que lo sabe.
- "Cero configuración." Una empresa real ajusta su catálogo.
- Cualquier cifra que no esté en la tabla de arriba o que no estés viendo en pantalla en ese momento.
