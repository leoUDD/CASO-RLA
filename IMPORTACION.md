# Paso 3: carga y normalización

Actualización relacional: el destino predeterminado es ahora `data/rla_modelo_v4.sqlite3`.
Las bases existentes anteriores a v4 se rechazan con indicación de migrar en copia; no se
migran silenciosamente. Una base nueva se inicializa con las versiones 1–4.

Cada carga nueva registra hoja y versión del importador. Las 15 columnas de agrupación y
códigos contables alimentan `classification_values` (una etiqueta por fuente/campo/valor)
y `record_classifications` (una relación por fila/campo), conservando exactamente el texto
original. Vacíos no crean etiquetas. Se conservan etiquetas incluso de filas en cuarentena.
Estas relaciones se escriben en la misma transacción que las filas, normalización y auditoría.

Los maestros, países, fabricantes canónicos y familias no se crean desde etiquetas sin aprobar.
`snapshot_classifications` y `snapshot_commercial` se completarán cuando se implemente la
publicación de inventario; la importación sigue siendo staging y no publica parcialmente.
La fecha de corte queda NULL si no se proporciona evidencia; no se confunde con la recepción.

Pruebas adicionales: archivos posteriores reutilizan etiquetas, distintas fuentes mantienen
catálogos separados, recargas no duplican relaciones, errores revierten filas y etiquetas juntas,
y los productos manuales aprobados se conservan.

Ejecutar desde la raíz del proyecto:

```powershell
python -m db.import_excel --input "C:\Users\Soporte\Downloads\Lista_Productos.xlsx"
```

Dependencias: Python, pandas y openpyxl para lectura. SQLite viene incluido en Python.
El argumento `--db` permite otra base; `--source` identifica el alcance del archivo completo.
`--report` define el reporte JSON. El archivo debe contener la hoja `Lista de productos`.

## Resultado

Se guardan todas las filas en raw_records, con fila Excel y valores leídos como texto, sin convertir
tokens NA a celdas vacías. Esto conserva el contenido de datos, no estilos ni fórmulas del libro.
El SHA-256 se calcula sobre los mismos bytes que se leen, evitando cambios entre huella y lectura.

normalized_records guarda la representación limpia y la versión de reglas. Se normalizan espacios;
las claves de búsqueda usan mayúsculas y omiten tildes. No se eliminan signos, medidas ni números
de modelos. No se infiere fabricante, modelo, moneda, país ni categoría.

Los decimales se interpretan con Decimal, sin flotantes. Vacío y cero siguen siendo distintos.
Los formatos ambiguos bloquean la fila. Los negativos se conservan con advertencia.

validation_issues registra errores y advertencias con fila y campo. Los errores incluyen claves
incompletas, dominios inválidos, claves repetidas e identidad contradictoria dentro del mismo código.
Los posibles marcadores de ausencia y códigos cero se señalan sin corregirlos automáticamente.

Una carga repetida devuelve la carga ya registrada, sin repetir filas ni reactivar una fotografía.
Las importaciones se guardan en una transacción: un fallo inesperado revierte la escritura completa.
No se alteran maestros, decisiones humanas, inventario manual ni carga vigente.

## Publicación pendiente

Este paso prepara y valida datos; **no publica fotografías ni crea el catálogo maestro**.
La carga conserva estado pending. ready_for_publication indica únicamente que no se detectaron
errores bloqueantes y hay filas. published indica si existe una fotografía vigente de esa carga.
La publicación transaccional se implementará en el paso de construcción del catálogo.

Resolver errores requiere una corrección revisada y una nueva versión del archivo. No se ofrece
una opción para ignorarlos o descartar filas silenciosamente. El Excel original no se modifica.

## Verificación

```powershell
python -m unittest discover -s db -p "test_*.py" -v
```

Las pruebas utilizan bases temporales. Comprueban decimales, ceros iniciales, faltantes,
conflictos, repetición de cargas, persistencia de la fotografía anterior y conservación del inventario manual.
