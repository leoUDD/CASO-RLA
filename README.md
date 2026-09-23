# Catálogo de productos RLA — Problema 1: estandarización

Aplicación local que toma el Excel de productos de R2 y lo convierte en un **catálogo único para todos los
países**, con codificación, nomenclatura y categorización estandarizadas, búsqueda, alta de productos sin
duplicados y exportación a SQLite. Es repetible: cada mes se carga el archivo nuevo y el proceso se ejecuta igual.

```
Cargar Excel (manual) → tratamiento → estandarización → exportación a SQLite (automáticos) → buscar / crear producto (manual)
```

## Cómo ejecutarlo

Requiere Python 3.10 o superior.

```powershell
python -m pip install -r requirements.txt
python -m db.catalog_app
```

Abrir **http://127.0.0.1:8766/** y, en **1. Cargar Excel**, elegir `Lista_Productos.xlsx` (hoja *Lista de
productos*). No se piden más datos: tratamiento, estandarización y exportación ocurren solos, en unos 35 segundos
con el archivo real. Si la base `data/rla_modelo_v4.sqlite3` no existe, se crea vacía. La base exportada queda en
`data/exports/catalogo_estandarizado.sqlite3` y se puede descargar desde la pestaña **4. Base SQLite**.

Pruebas: `python -m unittest discover -s db -p "test_*.py"`.

## Qué hace cada paso

| Paso | Tipo | Qué ocurre |
|---|---|---|
| **1. Cargar Excel** | manual | Se elige el archivo. Se guarda su huella SHA-256 y cada fila original; un archivo idéntico no se reimporta. |
| **2. Tratamiento** | automático | Espacios, números en formato `5.000,00` con `Decimal`, dominios y banderas. Las filas con error quedan en cuarentena con su motivo. |
| **3. Estandarización** | automático | Nombres, unidades, marcas, país y tipo de sitio, familia, código estándar y duplicados. |
| **4. Base SQLite** | automático | La base exportada se regenera tras cada carga, alta de producto o cambio de administración. |
| **5. Buscar** | manual | Ignora tildes, mayúsculas y orden de palabras; filtros por categoría, familia, país y estado; detalle con stock por sitio y códigos de cada país. |
| **6. Nuevo producto** | manual | Mientras se escribe se muestran el nombre estandarizado, la familia sugerida y los productos iguales o parecidos. Al crearlo recibe su código. |
| **Administración** | opcional | Asignar país a sitios sin evidencia, revisar clasificaciones dudosas, excluir registros de sistema, publicar el inventario, volver a ejecutar las reglas. Aquí el responsable es obligatorio. |

En el flujo, el responsable es opcional: si se deja vacío, la auditoría registra "Usuario RLA".

### Reglas de estandarización (`db/std_rules.py`)

- **Codificación**: `CAT-FAM-NNNNN`, igual en todos los países (por ejemplo, `AUD-MIC-00012`). El país no va en
  el código: es un dato del sitio. El código se asigna una vez y no cambia en cargas futuras. Los códigos de
  cada país (`10063`, `CO PRV07`…) quedan como equivalencias del producto.
- **Nomenclatura**: corrige tildes y mayúsculas, unifica unidades (`mts` → `m`, `¨` → `in`,
  `Ansilumenes` → `ANSI lm`) y conectores (`M-M` → `macho-macho`). Saca del nombre la etiqueta de país
  `(CL)` y las marcas de estado ("NO USAR"). Agrega marca y modelo al final.
- **Marcas**: une las escrituras que coinciden al comparar sin espacios ni signos (`DA-LITE` = `DA LITE`)
  y usa una lista de alias para lo demás (`BLACK MAGIC` → `BLACKMAGIC DESIGN`). `GENERICO` y `S/M` se
  tratan como "sin marca".
- **Categorización**: 13 categorías y 37 familias. Se combinan patrones sobre el nombre con las etiquetas
  originales de R2. Si coinciden, la confianza es alta; si se contradicen, el producto va a revisión.
- **Sitios**: el país se deduce por palabras clave o por el prefijo de país de los códigos del sitio. El tipo
  de sitio es uno de estos: bodega, sede, servicio técnico, venta, descarte, ajuste o administrativo. Solo el
  stock de bodegas y sedes cuenta como disponible.
- **Duplicados**: se marcan los productos con el mismo nombre, marca y modelo. Nunca se fusionan solos.

Las decisiones de las personas (revisiones, país asignado a un sitio, altas manuales) prevalecen sobre las
reglas y se conservan al volver a estandarizar. Todo queda en `audit_events`.

## Estructura

| Archivo | Rol |
|---|---|
| `db/catalog_app.py`, `db/catalog_app.html` | Servidor local y la interfaz |
| `db/import_excel.py` | Carga, normalización, validación y cuarentena |
| `db/build_catalog.py` | Productos maestros y revisiones |
| `db/std_rules.py` | Reglas de estandarización (editable) |
| `db/standardize.py` | Aplica las reglas en SQLite, búsqueda y altas |
| `db/export_catalog.py` | Exportación a SQLite (`python -m db.export_catalog`) |
| `db/operations.py` | Revisión, registros técnicos, publicación de inventario y respaldos |
| `db/schema.sql`, `db/migrations/` | Modelo relacional (ver `MODELO_ENTIDAD_RELACION.md`) |
| `outputs/`, `*.md` | Análisis previos: perfilamiento, duplicados, taxonomía |

## Base exportada

`productos`, `codigos_origen`, `categorias`, `familias`, `marcas`, `marca_alias`, `paises`, `sitios`,
`inventario`, `metadatos` y las vistas `v_catalogo` y `v_stock_por_pais`.

## Límites conocidos

- La aplicación es local y para un solo usuario: el responsable se declara, no se autentica.
- El Excel no trae moneda: no se suman costos entre países.
- 41 sitios no tienen evidencia de país; se asignan en Administración → Sitios sin país.
- Alrededor del 15 % de los productos queda para revisión humana: sin regla, en conflicto o marcados "no usar".
