# Reglas de estandarización

Todas las reglas están en `catalogo/std_rules.py`: son listas y diccionarios editables. Después de modificarlas,
**Administración → Re-ejecutar** las aplica de nuevo a la carga vigente. Las reglas **proponen**; lo que decide
una persona (revisiones, país de un sitio, vinculaciones, altas manuales) prevalece y se conserva en las
cargas siguientes.

Las reglas salen del análisis exploratorio del Excel (`analisis/EDA_Lista_Productos.ipynb`).

## Codificación

- **Formato:** `CAT-FAM-NNNNN`, igual para todos los países. Por ejemplo, `AUD-MIC-00012` = Audio / Micrófonos / correlativo.
- **País:** no forma parte del código; es un dato del sitio. Un mismo equipo tiene un solo código en todos los países.
- **Asignación:** el código se asigna una vez y **no cambia** en cargas futuras, aunque el producto cambie de
  familia, para no romper cotizaciones ni el historial.
- **Sin código:** no reciben código los productos sin familia ni los marcados "no usar / eliminar". Lo reciben
  al clasificarse o al resolver su estado.
- **Códigos de origen:** los códigos de cada país (`10063`, `CO PRV07`, `PALED2.9_M2CO`…) se conservan como equivalencias.

## Nomenclatura

A partir de la descripción original se arma el nombre estándar: **nombre base + marca + modelo**. Marca y
modelo no se repiten si ya estaban en la descripción.

| Qué | Ejemplo |
|---|---|
| Unidades | `30 metros` → `30 m`, `42¨` → `42 in`, `10 cms` → `10 cm` |
| Luminosidad | `6.000 Ansilumenes` → `6000 ANSI lm` |
| Conectores | `M-M` → `macho-macho`, `M-H` → `macho-hembra` |
| Mayúsculas | `SISTEMA DE SONORIZACION` → `Sistema de sonorización`, respetando siglas (HDMI, LED, XGA…) |
| Tildes | `Microfono inalambrico` → `Micrófono inalámbrico`; errores como `Iluminaciòn` → `Iluminación` |
| País en el nombre | `Panel LED … (CL)` → se quita: el país vive en el sitio |
| Estado en el nombre | `NO USAR`, `eliminar`, `ficha mala` → se quitan del nombre y el producto queda marcado para revisión |
| Descripción vacía o "." | Queda como `Revisar: descripción inválida` |

## Marcas y modelos

- **Unión automática:** se unen las escrituras que coinciden al comparar sin espacios, signos ni tildes
  (`DA-LITE`, `DA LITE` y `DALITE`), y se usa la escritura más frecuente.
- **Alias explícitos:** `BRAND_ALIASES` corrige lo que la comparación no detecta: `BLACK MAGIC` → `BLACKMAGIC DESIGN`,
  `ALLEN & HEAT` → `ALLEN & HEATH`, `SENHEIZER` → `SENNHEISER`.
- **Sin marca:** `GENERICO`, `S/M`, `N/A`, `.` y `----` significan "sin marca".
- **Resultado:** con el archivo actual, 619 escrituras de marca quedan en 571 marcas.

## Categorización

- **Taxonomía:** 13 categorías y 37 familias (`TAXONOMY`).
- **Dos fuentes de evidencia:**
  - el **nombre**, con patrones sobre el objeto principal (`NAME_PATTERNS`), por ejemplo `^MICROFONO`;
  - las **etiquetas originales** de R2 (`Report Group`, `EXCHANGEGROUP`), traducidas con `LABEL_ALIASES`.

| Resultado | Cuándo |
|---|---|
| Alta confianza | Nombre y etiqueta indican la misma familia |
| Por nombre | Solo el nombre indica familia, o la etiqueta es un cajón genérico ("Accesorios de video") |
| Por etiqueta | Solo la etiqueta indica familia |
| Por tipo | `Type = LABOR` → Personal; `Package = PACKAGE` → Paquetes y soluciones |
| Revisar: conflicto | Nombre y etiqueta indican familias distintas |
| Revisar: sin regla | Ninguna regla aplica |

Con el archivo actual se clasifica automáticamente el **84,7 %** de los productos; el resto queda para revisión.

## Sitios

- **País, en orden de prioridad:**
  1. asignación manual;
  2. palabra clave geográfica en el nombre (`BOGOTA`, `LIMA`, `SANTIAGO`…);
  3. prefijo de país de los códigos del sitio: al menos 30 % de las filas con prefijo y 70 % de ellos del mismo país.

  Lo que no cumple nada queda **sin país** para asignarlo a mano.
- **Tipo:** bodega / CD, sede de operación, servicio técnico, venta, descarte / baja, ajuste / no ubicado o
  administrativo. Solo el stock en **bodegas y sedes** cuenta como disponible.

## Duplicados y equivalentes

- **Agrupación:** se agrupan los productos con el mismo nombre base, marca y modelo estandarizados.
- **Duplicado en el mismo país:** dos fichas del mismo producto conviven en un país. Es la ficha duplicada que
  el catálogo busca evitar.
- **Equivalente en otro país:** cada país tiene su propio código del mismo producto.
- **Qué es "presente":** un país está presente si el código tiene al menos un registro en un sitio de ese país.
  Un alta manual, sin país, se trata como posible duplicado de todos.
- **Vincular:** desde el detalle del producto, dos productos pueden pasar a compartir un código estándar. Los
  códigos de origen quedan como equivalencias, el código retirado se sigue encontrando al buscar y la
  vinculación se puede deshacer. **Nunca se fusiona nada automáticamente.**
- **Stock:** se mantiene **por país** y nunca se suma entre países.

## Nuevo producto

Mientras se escribe se aplican las mismas reglas: nombre estándar, marca canónica y familia sugerida. Además
se muestran los productos iguales o parecidos. Si ya existe uno con el mismo nombre, marca y modelo, el alta
se bloquea hasta confirmar que es distinto.
