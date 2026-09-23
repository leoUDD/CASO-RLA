# Paso 4: candidatos a duplicado

Se analiza la capa normalizada de la carga 1, incluso mientras no esté publicada. No se fusiona
ni elimina ningún producto. Se genera un registro por código; se agregan sus filas de procedencia.
Los códigos con incidencias de identidad permanecen marcados como cuarentena.

Ejecutar desde la raíz: `python -m db.matching --load 1`.
Consultar `outputs/duplicados/revision.html` y el detalle completo `candidatos.json`.
El informe permite búsqueda, filtros de prioridad y decisión, y páginas de 20 pares.

## Reglas

1. Comparar todos los pares con fabricante y modelo coincidentes y no vacíos.
   NA, N/A, NULL, NONE, S/N, SIN DATO, guion y GENERICO/GENERICA no cuentan como identidad.
2. Comparar todos los pares con descripción normalizada exactamente igual.
3. Buscar pares adicionales con palabras presentes en 2 a 60 códigos, tipo igual y sin
   contradicción entre marcas/modelos conocidos. Conservar similitud de caracteres >=80/100,
   calculada con SequenceMatcher. No representa una probabilidad ni está calibrada.
4. Señalar diferencias de fabricante, modelo, tipo, paquete y serialización, números descriptivos,
   clase B, metro cuadrado, kit/conjunto, advertencias de uso y cuarentena.
5. Sin esas señales, la marca/modelo común se etiqueta coincidencia fuerte. No autoriza fusionar.
   El resto queda para revisión descriptiva. Ninguna categoría existente se toma como verdad canónica.

El bloqueo reduce comparaciones, pero puede omitir candidatos sin vocabulario compartido o con
abreviaciones. No se expanden sinónimos ni se convierten unidades; 1 m y 100 cm requieren revisión.
Las cifras representan pares, no productos únicos ni grupos disjuntos. No aplicar cierre transitivo:
que A se parezca a B y B a C no permite unir A, B y C automáticamente.

## Guardar una decisión

Usar códigos reales del informe y un motivo específico:

```powershell
python -m db.matching --load 1 --codes CODIGO_A CODIGO_B --decision separate --reason "Medidas diferentes confirmadas" --actor "Nombre del revisor"
```

Valores: `separate` (mantener separados), `equivalent` (equivalencia aprobada), `pending` (reabrir).
No ejecutar el ejemplo sin reemplazar los códigos y confirmar la decisión. El HTML es de consulta;
no guarda cambios. El comando actualiza la revisión, registra auditoría y regenera el informe.
Las decisiones persisten por fuente/par de códigos, sin requerir maestros todavía. Se muestran
separadas de los pendientes; no se crean equivalencias automáticamente. Si cambia el significado
de un código en otra carga, su decisión debe revisarse nuevamente; aún no hay invalidación automática.

## Cuatro registros sin sitio

DEFAULTITEM, DEFAULTLABOR y DEFAULTMISC coinciden con los tipos ITEM, LABOR y MISCCHARGE.
SYSTEMDEFAULT carece de tipo. Los cuatro carecen de sitio y stock. Esto sugiere plantillas del
sistema, pero el nombre no prueba su función. Propuesta: clasificarlos explícitamente como registros
técnicos fuera del inventario, conservando su origen, después de validar ese criterio con RLA o el
responsable del proyecto. Hasta esa decisión permanecen en cuarentena y bloquean la publicación.

## Pruebas

`python -m unittest discover -s db -p "test_*.py" -v`

Incluye diferencias de medidas y modelos, marcadores de ausencia, unicidad de pares y persistencia
auditada de decisiones sin fusiones. No sustituye la evaluación humana de precisión del matching.
