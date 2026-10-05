# Puente a CONTPAQi — exportar las pólizas del mes

> Sub-proyecto 2 de 7 del frente "ARCA para firmas contables". Borrador del
> 2026-10-05, pendiente de aprobación.

## Para qué

El contador que va a ver ARCA lleva a sus clientes en CONTPAQi Contabilidad. La
primera objeción a una alianza es "yo ya tengo mi sistema". Este módulo la
quita: lo que el empresario registra en ARCA sale como un archivo que el
contador carga en CONTPAQi con su proceso de siempre (Cargado de pólizas), sin
recapturar nada.

**Éxito:** el contador elige un mes, descarga un archivo, lo carga en su
CONTPAQi y las pólizas entran cuadradas y en sus cuentas.

## Qué se sabe del formato y qué no

CONTPAQi Contabilidad carga pólizas desde un archivo de texto de ancho fijo,
con un renglón `P` por póliza y un renglón `M` por movimiento. Referencia
pública usada (foro ValidaCFD, "Generación de txt para importar a CONTPAQ i"):

| Renglón `P` | Ancho | Alineación | Valor |
|---|---|---|---|
| Marca | 2 | izquierda | `P` |
| Fecha | 8 | — | `AAAAMMDD` |
| Tipo de póliza | 4 | derecha | 1 Ingresos, 2 Egresos, 3 Diario |
| Folio | 9 | derecha | numérico |
| Clase | 1 | — | `1` |
| Id. de diario | 10 | izquierda | `0` |
| Concepto | 100 | izquierda | texto |
| Sistema de origen | 2 | derecha | `11` |
| Impresa | 1 | — | `0` |
| Ajuste | 1 | — | `0` |

| Renglón `M` | Ancho | Alineación | Valor |
|---|---|---|---|
| Marca | 2 | izquierda | `M` |
| Cuenta | 30 | izquierda | número de cuenta sin guiones |
| Referencia | 10 | izquierda | texto |
| Tipo de movimiento | 1 | — | 0 cargo, 1 abono |
| Importe | 20 | izquierda | decimal con punto |
| Id. de diario | 10 | izquierda | `0` |
| Importe en moneda extranjera | 20 | izquierda | `0.0` |
| Concepto | 100 | izquierda | texto |

Los campos van separados por un espacio.

**No verificado:** esa referencia es de una versión antigua. Las versiones
recientes usan renglones `M1` con otros anchos y renglones `AD` para asociar el
UUID del CFDI. No hay documentación oficial pública del layout. Por eso:

- El layout vive en una tabla declarativa de campos (nombre, ancho, alineación);
  ajustarlo al CONTPAQi del contador es cambiar esa tabla, no la lógica.
- La forma segura de cerrarlo es pedirle al contador un **bajado de pólizas**
  de su propio CONTPAQi (es el mismo formato en sentido inverso) y calcar ese
  archivo. Hasta tenerlo, el export se presenta como "formato de referencia".
- Codificación Windows-1252 y fin de línea CRLF, que es lo que espera un
  programa de Windows; también se confirma con la muestra.

## Diseño

### Cuenta equivalente en CONTPAQi

El catálogo de ARCA (1100 Caja y Bancos, 4100 Ventas…) no es el del contador.
Cada cuenta de ARCA guarda su equivalente:

- Columna nueva `accounts.contpaqi_code` (`String(30)`, nullable). Migración
  `20261005_01_cuenta_contpaqi.py`, aditiva.
- `PATCH /api/accounting/accounts/{id}` con `{"contpaqi_code": "..."}`; sólo
  roles de contabilidad (`ACCOUNTING_ROLES`). Se guarda sin guiones ni espacios.
- En Contabilidad → Catálogo, una columna editable "Cuenta en CONTPAQi".

Una cuenta sin equivalente se exporta con su propio código de ARCA, y el
archivo se entrega igual: el contador puede preferir dar de alta esas cuentas
en CONTPAQi.

### Exportación

`GET /api/accounting/contpaqi?year=AAAA&month=MM`, roles de contabilidad.

- Incluye todas las pólizas `POSTED` del mes de la empresa activa, en orden de
  fecha y folio. Las pólizas de reversa se exportan como cualquier otra: en
  CONTPAQi la cancelación también es una póliza.
- Tipo: `INGRESO` → 1, `EGRESO` → 2, `DIARIO` → 3.
- Folio: el consecutivo del folio de ARCA (`Ig-2026-09-0007` → `7`). El folio
  completo de ARCA viaja en la Referencia de cada movimiento para rastrear.
- Importe con dos decimales, desde `Decimal`, sin pasar por `float`.
- Textos recortados al ancho del campo y sin saltos de línea; lo que
  Windows-1252 no pueda representar se sustituye por `?`.
- Antes de escribir, cada póliza se revalida: cargos = abonos. Si alguna no
  cuadra, el export falla completo con el folio; nunca se entrega un archivo a
  medias.
- Un mes sin pólizas responde 404 con "No hay pólizas en ese mes."
- Nombre del archivo: `polizas-contpaqi-AAAA-MM.txt`.

`GET /api/accounting/contpaqi/preview?year=&month=` devuelve cuántas pólizas y
movimientos saldrían y qué cuentas usadas ese mes no tienen equivalente, para
avisar antes de descargar.

### Interfaz

En Contabilidad → Libro diario, botón "Exportar a CONTPAQi": elige el mes,
muestra el resumen del preview ("42 pólizas · 118 movimientos · 3 cuentas sin
equivalente") y descarga. El aviso de cuentas sin equivalente enlaza al
catálogo.

### Código

- `app/services/accounting/contpaqi.py`: tabla del layout y función pura
  `render(entries) -> str`. Sin base de datos, para probar renglón por renglón.
- Consulta y endpoints en `app/domains/accounting/` (router y service
  existentes).

## Pruebas

- El renglón `P` y los `M` de una póliza conocida salen idénticos, carácter por
  carácter, a un archivo esperado; cada renglón mide lo que suma el layout.
- Cargos y abonos de cada póliza exportada suman igual.
- Tipo y folio se traducen bien para Ingreso, Egreso y Diario.
- Una cuenta con equivalente sale con él; una sin equivalente, con su código.
- Concepto más largo que el campo, con acentos, con salto de línea y con un
  carácter fuera de Windows-1252.
- Sólo salen pólizas de la empresa activa y del mes pedido.
- Un rol sin acceso a contabilidad recibe 403.
- La migración corre en PostgreSQL (CI) y deja un solo head.

## Fuera de alcance

- Renglones `AD` con UUID del CFDI: llegan con el módulo de importación de CFDI.
- Importar el catálogo de CONTPAQi para sugerir equivalencias.
- Carga directa por SDK o base de datos de CONTPAQi.
- Exportar a otros sistemas (Aspel COI).
