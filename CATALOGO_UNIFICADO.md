# Catálogo y revisión unificada

Actualización operativa: interfaz con persistencia en http://127.0.0.1:8766/.
Consultar OPERACION_CATALOGO.md. Tras el control de muestra quedan 1.810 aplicadas por regla,
6.076 pendientes y cuatro cuarentenas. Los conteos siguientes documentan la construcción inicial.

Base operativa de esta etapa: data/rla_modelo_v4.sqlite3. Fuente: RLA_Productos, carga 1.
Se examinan los 7.890 códigos, no únicamente las tres familias iniciales.

## Qué se realizó

- Un maestro por cada código sin cuarentena: 7.886 maestros y correspondencias iniciales.
- Cuatro códigos técnicos permanecen sin maestro e impiden publicar la carga completa.
- 1.814 clasificaciones aplicadas por reglas; 6.072 pendientes y cuatro en cuarentena.
- La revisión unificada referencia al maestro, familia sugerida, estado y evidencia por código.
- Las propuestas anteriores se conservan. Para pendientes se prioriza la última propuesta
  de context-1 sobre conditional-1, incluida la categoría sin familia cuando corresponda.
- Sin fusiones entre códigos. Los nombres maestros son descripciones limpias provisionales,
  no nombres técnicos finales. No se infieren marcas, países, monedas ni atributos faltantes.

## Qué significa aplicada por regla

La familia debe ser la única identificada por el objeto principal de la descripción y coincidir
con la única familia de las etiquetas específicas Report Group, EXCHANGEGROUP o INVENTORYGROUP.
Paquetes, tipos distintos de ITEM, cuarentena y advertencias operacionales quedan pendientes.
No es una validación humana ni una medición de exactitud. Las reglas cubren las 36 familias
con patrones conservadores; que una regla exista no implica que todos sus productos sean clasificables.
Los maestros existentes/manuales no se reclasifican automáticamente.

Categorías y familias usadas en las clasificaciones aplicadas se activan. Las etiquetas genéricas,
numéricas y los grupos sin equivalencia conocida no se convierten en reglas aprobadas.
La aprobación no propaga equivalencias ni suma existencias.

## Consulta y reproducción

Abrir outputs/catalogo/revision_unificada.html. Permite búsqueda por código/maestro/descripción,
filtro por estado, evidencia e historial. JSON completo en revision_unificada.json.

Ejecutar `python -m db.build_catalog` para generar la revisión. La versión catalog-1 es estable:
repetirla no agrega maestros ni revisiones ni sobrescribe decisiones existentes. Las modificaciones
de reglas requieren una nueva versión y una política explícita de revisión de asignaciones previas.
No activar nuevas versiones para sobrescribir revisiones humanas sin procedimiento específico.

## Límites operativos

El catálogo maestro se construyó pero no se publicó inventario ni se cambió active_loads.
La vista current_catalog previa depende de una carga publicada para productos importados;
por eso esta revisión consulta master_products/unified_catalog_reviews directamente.
El formulario de revisión/altas y la publicación de inventario están implementados en db.catalog_app.
La primera publicación real sigue pendiente de decisiones técnicas y fecha de corte confirmada.
Las cuatro filas de sistema no se excluyeron por su nombre.

Se creó respaldo previo y se comprobaron FK, integridad e idempotencia en la base real.
La suite tiene 38 pruebas, incluyendo los controles anteriores y reglas conservadoras del catálogo.
