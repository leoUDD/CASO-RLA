"""Genera mapeo completo y verifica cobertura contra el perfil real; sin escrituras SQL."""
import json
from pathlib import Path

MAPPING = {
'Product ID':('legacy_products.legacy_code','Texto; clave única junto con source_id. No es master_id.'),
'Description':('standardization_proposals → master_products.standard_name','Conservar original; nombre aprobado por reglas de familia.'),
'Stock':('inventory_snapshots.stock','Decimal; NULL distinto de cero; negativo se señala.'),
'Type':('master_products.product_type','CHECK ITEM/LABOR/MISCCHARGE/PARTS; conflicto requiere revisión.'),
'ITEMCATEGORY':('master_products.serialization','SERIAL/NONSERIAL; no representa número de serie de activo.'),
'Package':('master_products.package_type','ITEM/PACKAGE; no inventar componentes ni cantidades.'),
'Cost':('snapshot_commercial.cost','Decimal; moneda desconocida permanece NULL.'),
'Replacement Cost':('snapshot_commercial.replacement_cost','Decimal observado por sitio/carga hasta confirmar alcance.'),
'SITENAME':('sites.name','Nombre vigente; conservar nombre observado en raw_records.'),
'MANUFACTURER':('manufacturer_aliases → manufacturers → master_products.manufacturer_id','Alias aprobado; no fusionar marcas por similitud automática.'),
'MODEL':('master_products.model','Texto; conservar signos, sufijos y números.'),
'SITEID':('sites.source_site_code','Clave dentro de fuente; faltante bloquea publicación.'),
'Availability Group':('classification_values + snapshot_classifications','Clasificación operativa original; no es familia canónica.'),
'ACCUMULATEDDEPRECIATIONGLCODE':('classification_values + snapshot_classifications','Código contable como texto; hoy vacío, no generar etiqueta para NULL.'),
'Report Group':('classification_values + snapshot_classifications','Puede alimentar propuesta de familia mediante regla aprobada.'),
'WRITEOFFGLCODE':('classification_values + snapshot_classifications','Código contable como texto; confirmar significado, no inferirlo.'),
'Bin Loaction':('inventory_snapshots.bin_location','Preservar encabezado original mal escrito en raw_json; semántica pendiente.'),
'CANRENT':('inventory_snapshots.can_rent','RENTABLE/NOTRENTABLE → 1/0; condición local.'),
'CANSELL':('inventory_snapshots.can_sell','SELLABLE/NOTSELLABLE → 1/0; condición local.'),
'CANSUBRENT':('inventory_snapshots.can_subrent','SUBRENT/NOTSUBRENT → 1/0; preservar granularidad de origen.'),
'COGSGROUP':('classification_values + snapshot_classifications','Grupo contable original; vacío no crea categoría.'),
'TAXGROUP':('classification_values + snapshot_classifications','Etiqueta tributaria, no tasa calculada ni país confirmado.'),
'CostoTotal':('snapshot_commercial.reported_total_cost','Conservar importe informado; no sustituir por Stock × Cost.'),
'DEPARTMENT':('classification_values + snapshot_classifications','Departamento original; contexto, no familia automática.'),
'DEPRCIATIONGLCODE':('classification_values + snapshot_classifications','Código original textual; no corregir su contenido por nombre de columna.'),
'DISCOUNTGROUP':('classification_values + snapshot_classifications','Grupo comercial; 57% se conserva como etiqueta, no descuento aplicado.'),
'AFFECTSAVAILABILITY':('inventory_snapshots.affects_availability','TRUE/FALSE → 1/0; no calcula disponibilidad futura.'),
'REVENUEGROUP':('classification_values + snapshot_classifications','Clasificación de ingreso original; conservar códigos numéricos como texto.'),
'RETAILPRICE':('snapshot_commercial.retail_price','Decimal; moneda y alcance no inferidos.'),
'EXCHANGEGROUP':('classification_values + snapshot_classifications','Agrupación original; evidencia para propuesta, no prueba de equivalencia.'),
'INVENTORYGROUP':('classification_values + snapshot_classifications','Agrupación original de inventario.'),
'ISFREIGHT':('inventory_snapshots.is_freight','FREIGHT/NOTFREIGHT → 1/0; provisionalmente por observación.'),
'ISMISCITEM':('inventory_snapshots.is_misc_item','MISCITEM → 1; vacío → NULL. No inferir False.'),
'LOWRETAILPRICE':('snapshot_commercial.low_retail_price','Decimal observado; no validar como mínimo contractual sin definición.'),
'Shelf Location':('inventory_snapshots.shelf_location','Ubicación textual; hoy vacía.'),
'MAXIMUMQTY':('inventory_snapshots.maximum_qty','Decimal observado; cero se conserva, interpretación operacional pendiente.'),
'MINIMUMQTY':('inventory_snapshots.minimum_qty','Decimal observado; no derivar alertas hasta confirmar significado.'),
'SUBRENTGLCODE':('classification_values + snapshot_classifications','Código contable textual, puede contener VIDEO; no forzar número.'),
'MSRP':('snapshot_commercial.msrp','Decimal; precio de referencia informado, moneda no inferida.'),
'SELLGLCODE':('classification_values + snapshot_classifications','Código contable como texto, no medida numérica.'),
'Price Group':('classification_values + snapshot_classifications','Grupo comercial original; hoy vacío.'),
'REORDERQTY':('inventory_snapshots.reorder_qty','Decimal observado; no calcular pedidos automáticamente.')}


def main():
    profile=json.loads(Path('outputs/perfilamiento/diagnostico.json').read_text(encoding='utf-8'))
    fields=[p['campo'] for p in profile['perfil_columnas']]
    assert len(fields)==42 and set(fields)==set(MAPPING), 'Mapeo incompleto o columna inventada'
    lines=['# Mapeo de las 42 columnas del Excel al modelo objetivo','',
           'Diseño propuesto; no representa una migración aplicada. Todas las columnas permanecen también en raw_records.raw_json y normalized_records.normalized_json.','',
           'Fuente: Lista_Productos.xlsx, hoja Lista de productos. Orden original de las columnas.','']
    for i,field in enumerate(fields,1):
        destination,rule=MAPPING[field]
        lines.extend([f'## {i}. {field}',f'Destino: **{destination}**.',rule,''])
    lines.extend(['## Datos nuevos que no vienen del Excel',
                  'master_id/código maestro, fuente, carga, huella y auditoría son generados por el sistema. País, moneda, fecha de corte y atributos técnicos ausentes quedan pendientes de evidencia. Categoría/familia canónica y nombre estándar requieren reglas o aprobación; no se copian indiscriminadamente de un grupo original.',''])
    Path('MAPEO_EXCEL.md').write_text('\n'.join(lines),encoding='utf-8')
    Path('outputs/estandarizacion/mapeo_modelo.json').write_text(json.dumps([{'column':f,'target':MAPPING[f][0],'rule':MAPPING[f][1]} for f in fields],ensure_ascii=False,indent=2),encoding='utf-8')
    print('Cobertura verificada: 42/42 columnas, una entrada por columna.')


if __name__=='__main__':main()
