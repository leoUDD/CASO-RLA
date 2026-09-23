# Mapeo de las 42 columnas del Excel al modelo objetivo

Diseño propuesto; no representa una migración aplicada. Todas las columnas permanecen también en raw_records.raw_json y normalized_records.normalized_json.

Fuente: Lista_Productos.xlsx, hoja Lista de productos. Orden original de las columnas.

## 1. Product ID
Destino: **legacy_products.legacy_code**.
Texto; clave única junto con source_id. No es master_id.

## 2. Description
Destino: **standardization_proposals → master_products.standard_name**.
Conservar original; nombre aprobado por reglas de familia.

## 3. Stock
Destino: **inventory_snapshots.stock**.
Decimal; NULL distinto de cero; negativo se señala.

## 4. Type
Destino: **master_products.product_type**.
CHECK ITEM/LABOR/MISCCHARGE/PARTS; conflicto requiere revisión.

## 5. ITEMCATEGORY
Destino: **master_products.serialization**.
SERIAL/NONSERIAL; no representa número de serie de activo.

## 6. Package
Destino: **master_products.package_type**.
ITEM/PACKAGE; no inventar componentes ni cantidades.

## 7. Cost
Destino: **snapshot_commercial.cost**.
Decimal; moneda desconocida permanece NULL.

## 8. Replacement Cost
Destino: **snapshot_commercial.replacement_cost**.
Decimal observado por sitio/carga hasta confirmar alcance.

## 9. SITENAME
Destino: **sites.name**.
Nombre vigente; conservar nombre observado en raw_records.

## 10. MANUFACTURER
Destino: **manufacturer_aliases → manufacturers → master_products.manufacturer_id**.
Alias aprobado; no fusionar marcas por similitud automática.

## 11. MODEL
Destino: **master_products.model**.
Texto; conservar signos, sufijos y números.

## 12. SITEID
Destino: **sites.source_site_code**.
Clave dentro de fuente; faltante bloquea publicación.

## 13. Availability Group
Destino: **classification_values + snapshot_classifications**.
Clasificación operativa original; no es familia canónica.

## 14. ACCUMULATEDDEPRECIATIONGLCODE
Destino: **classification_values + snapshot_classifications**.
Código contable como texto; hoy vacío, no generar etiqueta para NULL.

## 15. Report Group
Destino: **classification_values + snapshot_classifications**.
Puede alimentar propuesta de familia mediante regla aprobada.

## 16. WRITEOFFGLCODE
Destino: **classification_values + snapshot_classifications**.
Código contable como texto; confirmar significado, no inferirlo.

## 17. Bin Loaction
Destino: **inventory_snapshots.bin_location**.
Preservar encabezado original mal escrito en raw_json; semántica pendiente.

## 18. CANRENT
Destino: **inventory_snapshots.can_rent**.
RENTABLE/NOTRENTABLE → 1/0; condición local.

## 19. CANSELL
Destino: **inventory_snapshots.can_sell**.
SELLABLE/NOTSELLABLE → 1/0; condición local.

## 20. CANSUBRENT
Destino: **inventory_snapshots.can_subrent**.
SUBRENT/NOTSUBRENT → 1/0; preservar granularidad de origen.

## 21. COGSGROUP
Destino: **classification_values + snapshot_classifications**.
Grupo contable original; vacío no crea categoría.

## 22. TAXGROUP
Destino: **classification_values + snapshot_classifications**.
Etiqueta tributaria, no tasa calculada ni país confirmado.

## 23. CostoTotal
Destino: **snapshot_commercial.reported_total_cost**.
Conservar importe informado; no sustituir por Stock × Cost.

## 24. DEPARTMENT
Destino: **classification_values + snapshot_classifications**.
Departamento original; contexto, no familia automática.

## 25. DEPRCIATIONGLCODE
Destino: **classification_values + snapshot_classifications**.
Código original textual; no corregir su contenido por nombre de columna.

## 26. DISCOUNTGROUP
Destino: **classification_values + snapshot_classifications**.
Grupo comercial; 57% se conserva como etiqueta, no descuento aplicado.

## 27. AFFECTSAVAILABILITY
Destino: **inventory_snapshots.affects_availability**.
TRUE/FALSE → 1/0; no calcula disponibilidad futura.

## 28. REVENUEGROUP
Destino: **classification_values + snapshot_classifications**.
Clasificación de ingreso original; conservar códigos numéricos como texto.

## 29. RETAILPRICE
Destino: **snapshot_commercial.retail_price**.
Decimal; moneda y alcance no inferidos.

## 30. EXCHANGEGROUP
Destino: **classification_values + snapshot_classifications**.
Agrupación original; evidencia para propuesta, no prueba de equivalencia.

## 31. INVENTORYGROUP
Destino: **classification_values + snapshot_classifications**.
Agrupación original de inventario.

## 32. ISFREIGHT
Destino: **inventory_snapshots.is_freight**.
FREIGHT/NOTFREIGHT → 1/0; provisionalmente por observación.

## 33. ISMISCITEM
Destino: **inventory_snapshots.is_misc_item**.
MISCITEM → 1; vacío → NULL. No inferir False.

## 34. LOWRETAILPRICE
Destino: **snapshot_commercial.low_retail_price**.
Decimal observado; no validar como mínimo contractual sin definición.

## 35. Shelf Location
Destino: **inventory_snapshots.shelf_location**.
Ubicación textual; hoy vacía.

## 36. MAXIMUMQTY
Destino: **inventory_snapshots.maximum_qty**.
Decimal observado; cero se conserva, interpretación operacional pendiente.

## 37. MINIMUMQTY
Destino: **inventory_snapshots.minimum_qty**.
Decimal observado; no derivar alertas hasta confirmar significado.

## 38. SUBRENTGLCODE
Destino: **classification_values + snapshot_classifications**.
Código contable textual, puede contener VIDEO; no forzar número.

## 39. MSRP
Destino: **snapshot_commercial.msrp**.
Decimal; precio de referencia informado, moneda no inferida.

## 40. SELLGLCODE
Destino: **classification_values + snapshot_classifications**.
Código contable como texto, no medida numérica.

## 41. Price Group
Destino: **classification_values + snapshot_classifications**.
Grupo comercial original; hoy vacío.

## 42. REORDERQTY
Destino: **inventory_snapshots.reorder_qty**.
Decimal observado; no calcular pedidos automáticamente.

## Datos nuevos que no vienen del Excel
master_id/código maestro, fuente, carga, huella y auditoría son generados por el sistema. País, moneda, fecha de corte y atributos técnicos ausentes quedan pendientes de evidencia. Categoría/familia canónica y nombre estándar requieren reglas o aprobación; no se copian indiscriminadamente de un grupo original.
