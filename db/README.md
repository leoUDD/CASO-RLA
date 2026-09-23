# Paso 2: modelo de datos

Decisiones acordadas: SQLite; Excel completos por fuente; alta manual individual;
identificadores maestros persistentes; revisión antes de vincular códigos distintos.

## Relaciones

- Una fuente tiene muchas cargas y una sola carga vigente.
- Cada carga conserva todas sus filas originales en JSON con su número de fila.
- Un código legado pertenece a una fuente y puede aparecer en muchos sitios y cargas.
- Cada código legado tiene como máximo un maestro vigente; un maestro puede agrupar varios códigos.
- Cada fotografía de inventario corresponde a carga, código legado y sitio, con referencia a la fila original.
- Un maestro puede existir sin código legado, sin sitio y sin stock: es el caso de un alta manual.
- Categorías admiten padres e hijos; la aplicación deberá impedir ciclos y validar la taxonomía.

## Importación completa

1. Identificar explícitamente la fuente y calcular SHA-256. La misma huella por fuente no crea otra carga.
2. Registrar la carga pendiente y todas sus filas originales. No cambiar todavía la carga vigente.
3. Validar estructura y claves. Conservar filas inválidas en cuarentena con motivo. Por defecto,
   una fila sin SITEID, una clave repetida o un dato obligatorio inválido bloquea la publicación completa.
   Los cuatro registros sin sitio del Excel actual requieren resolución explícita antes de publicar.
4. Preparar códigos, sitios, maestros iniciales y fotografías en una transacción de publicación.
   Inicialmente un código nuevo recibe su propio maestro, salvo equivalencia revisada.
5. Validar conteos y marcar la carga válida. Actualizar active_loads dentro de la misma transacción.
   Si falla, revertir la publicación; el historial de la carga fallida y su diagnóstico se guardan aparte.
6. Los registros ausentes desaparecen de current_inventory; permanecen en el historial.
   No se convierten en stock cero ni provocan la eliminación del maestro.

Las cargas completas solo reemplazan su fuente. No se infiere el país por el código.
Una carga ya conocida no reactiva una fotografía antigua. Restaurar una carga anterior será
una acción explícita y auditada. Los maestros y correcciones aprobadas no se sobrescriben
automáticamente con descripciones del Excel; los nuevos valores quedan en la evidencia original.

## Alta manual

Requerir nombre, tipo, autor y motivo. Fabricante, modelo y categoría pueden quedar pendientes
cuando no se conocen o no aplican. Buscar similares antes de crear. Si ya existe un producto,
usar su maestro y, cuando corresponda, agregar su asociación con el sitio.

SQLite genera master_id y su representación PRD-000001. No se regeneran por orden de archivo.
Un alta manual aparece en current_catalog sin requerir inventario. Las cargas no la eliminan.
El stock manual es opcional y se registra por separado en manual_site_entries. NULL significa
desconocido; cero significa cero informado. No inferir disponibilidad de arriendo desde stock.

Si posteriormente aparece un código equivalente en Excel, un revisor vincula el código al maestro
manual en una transacción, conservando su identidad. manual_import_overlaps señala coincidencias
de maestro y sitio entre ambos orígenes. No hay una vista que sume ambos stocks: el revisor debe
decidir si la entrada manual queda reconciliada o representa existencias distintas.

## Historial y controles

Las decisiones guardan autor, motivo y fecha. Las actualizaciones de equivalencias y los cambios
manuales deberán escribir audit_events en la misma transacción. review_decisions registra decisiones;
no ejecuta fusiones por sí sola. Mantener las decisiones de separación al generar nuevos candidatos.
El historial de inventario utiliza las equivalencias actuales; para reconstruir las equivalencias tal como
eran en una fecha se usará el historial de auditoría, no current_inventory.

Activar PRAGMA foreign_keys=ON en cada conexión. La base impide relaciones entre fuentes distintas,
cargas vigentes no validadas, códigos repetidos por fuente e inventario repetido por carga/código/sitio.
La validación de cobertura completa, la escritura de auditoría, la normalización de decimales y la
revisión de equivalencias corresponden al servicio de aplicación, aún por implementar.

Stock y costos usan texto decimal canónico (ejemplo: 1234.50), interpretado con Decimal por la aplicación;
evita redondeo binario. No almacenar símbolos o separadores de miles. La moneda queda NULL cuando
la fuente no la declara. Nunca sumar costos de moneda desconocida. Conservar texto original en raw_json.

## Archivos y ejecución

- schema.sql: esquema versionado, índices, restricciones y vistas.
- init_db.py: crea la base vacía y comprueba su integridad.
- ../data/rla.sqlite3: base inicial, únicamente con versión y fuente RLA_Productos.

Desde la raíz del proyecto, ejecutar `python db/init_db.py`. Solo requiere Python con SQLite.
El inicializador es repetible para la versión 1; futuras modificaciones requieren migraciones explícitas.
El Excel todavía no está importado. La importación y el formulario corresponden a los siguientes pasos.
