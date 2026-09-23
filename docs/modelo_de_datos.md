# Modelo de datos

La aplicación usa dos bases SQLite:

| Base | Ruta | Para qué |
|---|---|---|
| **Operativa** | `data/rla_modelo_v4.sqlite3` | Guarda cada carga, el tratamiento, la estandarización, las decisiones de personas y la auditoría. Es la fuente de verdad. |
| **Exportada** | `data/exports/catalogo_estandarizado.sqlite3` | Fotografía limpia y relacional del catálogo, lista para BI, Excel o R2. Se regenera sola tras cada cambio. |

Las dos se crean automáticamente. El esquema está en `catalogo/sql/`: `schema.sql` más las migraciones 002–004,
que se aplican al crear una base nueva. La estandarización agrega sus tablas al iniciar (`catalogo/standardize.py`).

## Base operativa

Una fila del Excel es una **observación de un código en un sitio**. Hay tres identidades distintas:
**producto maestro**, **código de origen** (el de cada país en R2) y **sitio**. El inventario siempre
queda por código × sitio, y el país lo aporta el sitio.

### 1. Carga y tratamiento

| Tabla | Contenido |
|---|---|
| `sources`, `loads` | Fuente (`RLA_Productos`) y cada archivo recibido: SHA-256, filas, hoja, versión del importador. Un archivo idéntico no crea otra carga. |
| `raw_records` | Cada fila original del Excel, tal como vino (JSON), con su estado: `accepted` o `quarantined`, y el motivo. |
| `normalized_records` | La misma fila normalizada: espacios, decimales con `Decimal`, dominios y banderas. |
| `validation_issues` | Errores y advertencias por fila y campo. Un error deja la fila en cuarentena. |
| `classification_values`, `record_classifications` | Etiquetas originales de R2 (Report Group, EXCHANGEGROUP…) y qué fila tiene cada una. |
| `technical_decisions` | Exclusión justificada de registros de sistema (DEFAULTITEM…). |

### 2. Catálogo

| Tabla | Contenido |
|---|---|
| `legacy_products` | Código de origen por fuente (`10063`, `CO PRV07`). |
| `master_products` | Producto maestro (`PRD-000001`): nombre, tipo, marca, modelo, familia y origen (`import` o `manual`). |
| `product_mappings` | Código de origen → maestro. Varios códigos pueden compartir maestro (`method='reviewed'`, tras una vinculación). |
| `categories`, `families` | Taxonomía: 13 categorías y 37 familias. |
| `manufacturers`, `manufacturer_aliases` | Marca canónica y cada escritura original que se unificó en ella. |
| `countries`, `sites` | País y sitio. `sites` guarda `site_type` y el origen del país y del tipo (`regla` o `manual`). |
| `unified_catalog_reviews` | Revisión de la clasificación por código: `pending`, `approved_by_rule`, `approved_by_reviewer` o `rejected`. |
| `manual_requests`, `manual_site_entries` | Altas manuales: evitan duplicar una solicitud y guardan el stock declarado por sitio. |

### 3. Estandarización

| Tabla | Contenido |
|---|---|
| `product_standards` | Una fila por maestro con el resultado de las reglas: código estándar `CAT-FAM-NNNNN`, nombre estándar, marca, modelo, familia, método de clasificación, estado operativo, grupo y tipo de duplicado, códigos de origen, países donde está presente, stock disponible por país (JSON) y texto de búsqueda. |
| `standard_code_links` | Vinculaciones entre productos: qué se vinculó a qué, el código estándar retirado, quién lo hizo y por qué. Se pueden deshacer. |
| `standardization_runs` | Resumen de cada ejecución de las reglas. |
| `audit_events` | Toda acción con su autor, motivo, fecha y valores de antes y después. |

### 4. Publicación de inventario (opcional)

| Tabla | Contenido |
|---|---|
| `active_loads`, `publications` | Carga vigente por fuente y la fecha de corte con que se publicó. |
| `inventory_snapshots`, `snapshot_commercial`, `snapshot_classifications` | Inventario publicado por código × sitio, con importes y etiquetas. |
| Vistas `current_inventory`, `current_catalog`, `manual_import_overlaps` | Inventario y catálogo vigentes, y coincidencias entre altas manuales e importadas. |

**Reservadas.** El modelo v4 incluye tablas que la aplicación todavía no usa: `attribute_definitions`, `units`,
`attribute_units`, `family_attributes`, `product_attribute_values`, `standardization_rules`,
`field_standardization_proposals`, `candidate_reviews` y `review_decisions`. Quedan listas para un siguiente
paso: atributos tipados por familia (longitud, lúmenes, pulgadas).

## Base exportada

| Tabla o vista | Contenido |
|---|---|
| `productos` | Código estándar, código maestro, nombre, marca, modelo, familia, tipo, estado, método, grupo y tipo de duplicado, países de presencia y `stock_por_pais` (texto, por ejemplo `CL: 13 · CO: 5`). |
| `stock_disponible_por_pais` | Stock disponible por producto y país, una fila por país. **No se suma entre países.** |
| `codigos_origen` | Equivalencias: código de cada país → producto, con su descripción original. |
| `codigos_estandar_retirados` | Códigos estándar retirados al vincular productos, y el producto que los reemplaza. |
| `categorias`, `familias`, `marcas`, `marca_alias`, `paises`, `sitios` | Taxonomía, marcas unificadas, países y sitios con tipo y disponibilidad. |
| `inventario` | Stock y costos por código × sitio de la última carga. |
| `metadatos` | Fecha de exportación, carga, archivo, SHA-256 y versión de reglas. |
| Vistas `v_catalogo`, `v_stock_por_pais` | Catálogo listo para consultar y stock por país y tipo de sitio. |

## Reglas de integridad

- **Claves foráneas:** se activan en cada conexión (`PRAGMA foreign_keys=ON`).
- **Transacciones:** toda carga, estandarización, vinculación y alta se hace en una transacción; si falla, se revierte completa.
- **Respaldo:** la app respalda la base operativa en `data/backups/` al iniciar y antes de cada carga.
- **Importes:** se guardan como texto decimal canónico (`1234.50`). El Excel no trae moneda, por eso nunca se suman costos entre países.
