# Catálogo de productos RLA — Problema 1: estandarización

Aplicación local que toma el Excel de productos de R2 y lo convierte en un **catálogo único para todos los
países**, con codificación, nomenclatura y categorización estandarizadas. Permite buscar productos, crear
productos nuevos sin duplicar fichas y exportar el catálogo a SQLite. Es repetible: cada mes se carga el
archivo nuevo y el proceso se ejecuta igual.

```
Cargar Excel (manual) → tratamiento → estandarización → exportación a SQLite (automáticos) → buscar / crear producto (manual)
```

## Cómo ejecutarlo

Requiere Python 3.10 o superior.

```powershell
python -m pip install -r requirements.txt
python -m catalogo
```

Abrir **http://127.0.0.1:8766/** y, en **1. Cargar Excel**, elegir `Lista_Productos.xlsx` (hoja *Lista de
productos*). No se piden más datos: el tratamiento, la estandarización y la exportación ocurren solos, en unos
24 segundos con el archivo real. Si la base no existe, se crea vacía.

| Qué | Dónde |
|---|---|
| Base operativa | `data/rla_modelo_v4.sqlite3` |
| Base exportada | `data/exports/catalogo_estandarizado.sqlite3`, también descargable desde la pestaña **4. Base SQLite** |
| Respaldos automáticos | `data/backups/` |

Pruebas: `python -m unittest discover -s tests`

## Qué hace cada paso

| Paso | Tipo | Qué ocurre |
|---|---|---|
| **1. Cargar Excel** | manual | Se elige el archivo. Se guarda su huella SHA-256 y cada fila original; un archivo idéntico no se reimporta. |
| **2. Tratamiento** | automático | Normaliza espacios, números en formato `5.000,00`, dominios y banderas. Las filas con error quedan en cuarentena con su motivo. |
| **3. Estandarización** | automático | Nombres, unidades, marcas, país y tipo de sitio, familia, código estándar `CAT-FAM-NNNNN` y duplicados. |
| **4. Base SQLite** | automático | La base exportada se regenera tras cada carga, alta, vinculación o cambio de administración. |
| **5. Buscar** | manual | Ignora tildes, mayúsculas y orden de palabras. Filtros por categoría, familia, país y estado. El detalle muestra el stock por país y por sitio, los códigos de cada país y los productos equivalentes, que se pueden vincular. |
| **6. Nuevo producto** | manual | Mientras se escribe muestra el nombre estandarizado, la familia sugerida y los productos iguales o parecidos. Al crearlo recibe su código. |
| **Administración** | opcional | Asignar país a sitios sin evidencia, revisar clasificaciones dudosas, excluir registros de sistema, publicar el inventario y volver a ejecutar las reglas. |

- **Responsable:** solo sirve para la auditoría y registra quién tomó cada decisión; no es un login. Se pide al
  vincular productos y en Administración. En el resto del flujo la auditoría registra "Usuario RLA".
- **Stock:** se muestra **por país** y nunca se suma entre países.

## Estructura

```
catalogo/                  Aplicación (python -m catalogo)
  app.py, app.html         Servidor local e interfaz
  import_excel.py          Carga del Excel, normalización, validación y cuarentena
  build_catalog.py         Productos maestros y revisiones
  std_rules.py             Reglas de estandarización (editables)
  standardize.py           Aplica las reglas en SQLite; búsqueda, altas y vinculación
  export_catalog.py        Exportación a SQLite (python -m catalogo.export_catalog)
  operations.py            Revisión, registros técnicos, publicación y respaldos
  init_db.py, migrate_v4.py, sql/   Esquema de la base y migraciones
tests/                     Pruebas automáticas
docs/                      Modelo de datos y reglas de estandarización
analisis/                  Análisis exploratorio del Excel (notebook)
data/                      Bases locales, generadas por la app (no se versionan)
```

## Documentación

- [Reglas de estandarización](docs/reglas_de_estandarizacion.md): qué hace cada regla y cómo editarla.
- [Modelo de datos](docs/modelo_de_datos.md): tablas de la base operativa y de la base exportada.
- [Análisis exploratorio](analisis/EDA_Lista_Productos.ipynb): hallazgos del Excel que dieron origen a las reglas.
  Se abre en VS Code con la extensión Jupyter. La ruta del Excel se configura en la primera celda o con la
  variable de entorno `RLA_EXCEL`.

## Límites conocidos

- La aplicación es local y para un solo usuario: el responsable se declara, no se autentica.
- El Excel no trae moneda: no se suman costos entre países.
- 41 sitios no tienen evidencia de país; se asignan en **Administración → Sitios sin país**.
- Alrededor del 15 % de los productos queda para revisión humana: sin regla, en conflicto o marcados "no usar".
