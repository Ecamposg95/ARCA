# Guion de la demo para el contador — ARCA

**Duración objetivo:** 20 minutos, más preguntas.
**Audiencia:** un contador que lleva a sus clientes en CONTPAQi.
**Tesis:** ARCA no reemplaza tu CONTPAQi; te quita la captura y te deja ver a todos tus clientes en una pantalla.
**Lo que se busca:** que acepte probarlo con un cliente real y que comparta un "bajado de pólizas" de su CONTPAQi.

La regla del guion: cada afirmación se demuestra en pantalla en los siguientes diez segundos. Y una segunda regla para esta audiencia: **lo que falta se dice antes de que lo pregunte.**

---

## Antes de la reunión

1. **Sembrar el mismo día**, con su nombre:

   ```bash
   python scripts/demo_despacho.py --url https://arca-production-d769.up.railway.app --contador "C.P. <su nombre>"
   ```

   Guarda el correo del contador y el de la dueña; la contraseña es `demodespacho2026`.
   La siembra caduca: después del día 17 la Ferretería sale en rojo en vez de ámbar, y al cambiar de mes ya no queda ninguna empresa en verde.

2. **Ensayar los actos 3, 5 y 6 una vez y volver a sembrar.** Esos tres actos cambian datos (cierran un mes, aprueban una propuesta, pagan una factura).

3. **Dos ventanas:** una con la sesión del contador y otra, en modo incógnito, con la de la dueña de la clínica. Tema claro, zoom 110 %, ventana de 1600×900 o más.

4. **Tener a la mano el Bloc de notas** para abrir el archivo de CONTPAQi en el acto 4.

### Lo que hay sembrado

| Empresa | Semáforo | Por qué | Rol del contador |
|---|---|---|---|
| Restaurante La Milpa | Urgente | $38,400 por pagar vencidos | Dueño (él la dio de alta) |
| Clínica Dental Sonríe | Por atender | 3 propuestas por revisar | Contador (la dueña lo invitó) |
| Ferretería El Tornillo | Por atender | Septiembre sin cerrar | Dueño |
| Despacho Contable del Valle | Al corriente | — | Dueño (su propio despacho) |

---

## Acto 1 · Tu cartera en una pantalla (2 min)

Inicia sesión como el contador. Aterriza en **Mis empresas**.

> "Esto es lo primero que ves en la mañana: todos tus clientes y dónde hay trabajo. No tienes que abrir empresa por empresa para saber quién no ha cerrado el mes."

Señala las causas escritas en cada fila y el conteo de arriba ("1 urgente · 2 por atender · 1 al corriente"). Señala el rol bajo cada nombre: en tres es dueño, en una es contador invitado. Son los dos modelos de trabajo, y vuelven al final.

## Acto 2 · Abajo hay contabilidad de verdad (4 min)

Clic en **Ferretería El Tornillo**. El encabezado cambia de empresa.

> "El dueño ve esto: cuánto tiene, cuánto le deben, cuánto debe. No ve cargos ni abonos. Tú sí."

1. **Contabilidad → Libro diario**, periodo "Mes anterior". Abre la póliza de la compra de mercancía: cargo a gastos, cargo a IVA acreditable, abono a bancos. Folio `Eg-2026-09-0001`.
   > "Cada operación que captura el dueño genera su póliza: Ingreso, Egreso o Diario, con folio por mes. No hay forma de registrar algo que no cuadre."
2. **Balanza**: "cargos = abonos ✓".
3. **Reportes → IVA**:
   > "El IVA va en flujo: se causa al cobrar y se acredita al pagar. Una factura a crédito queda como IVA pendiente hasta que se cobra."

## Acto 3 · Cerrar el mes (3 min)

**Contabilidad → Cierre de periodo.** Septiembre está abierto, con sus pólizas.

1. **Cerrar mes** en septiembre. Confirma.
   > "Un mes cerrado ya no acepta operaciones ni correcciones. Si el dueño intenta capturar algo de septiembre, ARCA se lo impide."
2. Clic en **Mis empresas** (barra lateral). La Ferretería pasó a "Al corriente".
3. Vuelve a la Ferretería → Cierre de periodo → **Reabrir**. Pide motivo.
   > "Se puede reabrir, pero a propósito y dejando escrito por qué. Ese rastro se queda." Cancela; no lo reabras.

## Acto 4 · Tu CONTPAQi sigue siendo tu CONTPAQi (4 min)

El acto que decide la reunión. Sigue en la Ferretería.

1. **Contabilidad → Catálogo de cuentas.** Columna "Cuenta en CONTPAQi".
   > "El catálogo de ARCA es sencillo a propósito. El tuyo no cambia: aquí le dices a ARCA cómo se llama cada cuenta en tu catálogo."

   Pídele el número de su cuenta de Ventas y de Bancos y captúralos en vivo (acepta guiones; los guarda sin ellos).
2. **Cierre de periodo → botón CONTPAQi** en septiembre. Muestra el resumen: pólizas, movimientos y las cuentas que todavía no tienen equivalente.
3. **Descargar archivo** y ábrelo en el Bloc de notas. Un renglón `P` por póliza, un renglón `M` por movimiento.
   > "Esto es lo que cargas con Cargado de pólizas. Lo que el dueño capturó en el mes entra a tu sistema sin que nadie lo recapture."

**Dilo tú antes de que lo pregunte:**

> "Este formato lo armé con la documentación pública que encontré, que es de una versión anterior. No lo he probado contra tu CONTPAQi. Si me pasas un bajado de pólizas de cualquier empresa tuya, lo dejo idéntico al tuyo esta misma semana."

Esa petición es la mitad del objetivo de la reunión.

## Acto 5 · El cliente que te invita (3 min)

Con el selector del encabezado, cambia a **Clínica Dental Sonríe**.

> "Esta empresa no la di de alta yo. La dueña ya usaba ARCA y me invitó como su contador. Veo su contabilidad, pero la empresa es suya."

Muestra la otra ventana con la sesión de la dueña: una sola empresa, sin selector.

De vuelta en la sesión del contador, **Propuestas** (marca 3):

> "Un agente revisó los movimientos y encontró tres cargos sin registrar. No los registró: los propuso, con su razón. Nada entra a la contabilidad sin que una persona lo apruebe."

**Aprobar** el cargo del laboratorio y enséñalo ya registrado en **Gastos**. **Rechazar** el del compresor ("falta la factura").

## Acto 6 · El que debe (2 min)

**Mis empresas → Restaurante La Milpa → Por pagar.** La factura de cárnicos lleva diez días vencida. **Registrar pago** completo. Vuelve a Mis empresas: el restaurante pasó a "Al corriente".

> "El semáforo no es un reporte que alguien llena. Sale del libro."

---

## Cierre · La propuesta (2 min)

> "Hay dos formas de trabajar juntos, y las acabas de ver. Una: tú das de alta a tu cliente y lo operas tú. Dos: tu cliente usa ARCA y te invita. En las dos, tú sigues declarando desde tu CONTPAQi."

Pide dos cosas concretas:

1. **Un cliente piloto** chico, de servicios o comercio, durante un mes.
2. **Un bajado de pólizas** de su CONTPAQi para dejar el formato exacto.

### Lo que viene, en el orden planeado

1. Importar CFDI (XML emitidos y recibidos) como propuestas con su UUID.
2. Cédula mensual de impuestos: IVA a cargo o a favor, retenciones por enterar, base para la DIOT.
3. Contabilidad electrónica del SAT: código agrupador, catálogo y balanza en XML.
4. Conciliación bancaria.
5. Checklist de cierre y calendario fiscal por cliente.

Pregúntale cuál le quitaría más trabajo. Su respuesta ordena lo que sigue.

---

## Preguntas difíciles

| Pregunta | Respuesta honesta |
|---|---|
| ¿Timbra facturas? | No. ARCA no es un PAC ni factura. Lo siguiente es importar los XML que ya existen. |
| ¿Descarga del SAT? | No todavía. Requiere la e.firma del cliente y eso se decide con cuidado. |
| ¿Nómina? | No. Se registra como gasto; el cálculo sigue en su sistema de nómina. |
| ¿DIOT, declaraciones? | No las genera. La cédula de impuestos es el siguiente paso; la declaración se sigue presentando desde donde hoy. |
| ¿Y mi catálogo de cuentas? | No se toca. Las equivalencias se capturan una vez por cliente. Importarlas desde CONTPAQi está pensado, no hecho. |
| ¿El archivo entra a mi versión? | No está probado contra ninguna. Con un bajado de pólizas suyo se deja exacto. |
| ¿Qué pasa con el saldo inicial? | El archivo trae TODAS las pólizas del mes, incluida la de saldo inicial que ARCA crea al dar de alta la empresa. Si ese saldo ya está en CONTPAQi, esa póliza se quita antes de cargar o se duplica. |
| ¿Y si ya tengo pólizas con ese folio? | Los folios salen con el consecutivo de ARCA por tipo y mes. Si en CONTPAQi ya hay pólizas capturadas en ese periodo, pueden chocar: la primera carga va en una empresa de prueba. |
| ¿Saldos iniciales de un cliente que ya opera? | Hoy sólo el saldo de caja y de cada cuenta de banco al darlas de alta. Una póliza de apertura completa no existe todavía. |
| ¿Un cliente ve los datos de otro? | No. Cada empresa está aislada y eso se prueba en cada cambio. Tú ves sólo las empresas donde tienes acceso. |
| ¿Cuánto cuesta? | Decisión de Emmanuel; llevar una respuesta preparada. |
| ¿Puedo tener a mis auxiliares? | Sí, invitándolos empresa por empresa. Un "despacho" con su personal y asignación de clientes no existe todavía. |

## Si algo falla en vivo

- **Sesión vencida o pantalla en blanco:** recarga; la sesión se renueva sola.
- **El semáforo no cambió:** entra de nuevo a Mis empresas desde la barra lateral.
- **Datos de un ensayo anterior:** resembrar toma un minuto y crea cuentas nuevas.
