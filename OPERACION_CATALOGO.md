# Operación local del catálogo

Ejecutar desde la raíz del proyecto: `python -m db.catalog_app`.
Abrir http://127.0.0.1:8766/. Usa `data/rla_modelo_v4.sqlite3`.
El servidor anterior de informes en 8765 puede seguir abierto: sus HTML son fotografías estáticas.
La aplicación nueva lee y escribe SQLite. No debe abrirse como archivo HTML local.

## Flujos disponibles

1. **Revisión:** buscar y filtrar por estado y motivo. Elegir familia, aprobar, rechazar o reabrir.
   Se exige responsable y motivo, se registra antes/después en auditoría y se rechazan escrituras
   sobre una revisión desactualizada. Una carga vieja no puede reclasificar un maestro con revisión posterior.
   Rechazar/reabrir retira la familia que esa revisión había aplicado; conserva el producto.
2. **Muestra:** hasta cinco códigos por familia con clasificación automática, orden SHA256 reproducible.
   La selección se conserva en `quality_samples`, incluso después de revisar sus códigos.
3. **Registros técnicos:** decisión explícita por fila y por carga. Los códigos DEFAULTITEM,
   DEFAULTLABOR, DEFAULTMISC y SYSTEMDEFAULT admiten exclusión justificada. No se elimina su información
   ni se borran los errores originales. Otros errores requieren corregir un nuevo archivo completo.
4. **Cargar archivo:** XLSX, hoja `Lista de productos`, fuente explícita, máximo 70 MB en la interfaz.
   Conserva originales, valida, prepara maestros y revisiones. No publica automáticamente.
   El hash por fuente hace idempotente una carga repetida. También recupera una preparación interrumpida.
5. **Publicar:** muestra aceptadas, exclusiones, bloqueos, ausencias y carga vigente anterior.
   Requiere confirmar archivo completo. Por defecto usa la fecha original de carga como referencia provisional; publications.date_basis=received_at deja explícito que no es un corte confirmado. También admite fecha de corte confirmada ISO con zona horaria.
   Publica en una transacción las existencias, importes, condiciones y clasificaciones por sitio.
   Cambia únicamente la carga vigente de esa fuente y conserva las anteriores.
   No reactiva una carga ya reemplazada. Compara fechas de corte cuando ambas están confirmadas; con fechas provisionales conserva el orden de cargas, sin afirmar vigencia del inventario.
   Una familia pendiente no bloquea inventario; una fila inválida sin resolución sí.
6. **Alta manual:** nombre y tipo obligatorios; familia, modelo, paquete, serialización y sitio opcionales.
   Existencia sin sitio se rechaza; vacío no equivale a cero. Cada solicitud tiene clave idempotente.
   Las altas manuales sobreviven a las importaciones; sus existencias no se suman al inventario importado.

## Control realizado

Se revisaron semánticamente 142 códigos de 31 familias por el asistente: 138 compatibles con la
descripción y cuatro reabiertos para confirmación (11280, 10763, 11254 y PE MISC07).
No es aprobación humana ni medición de exactitud poblacional. No verifica existencia física ni vigencia.
Detalle: `outputs/catalogo/control_muestra.json`.
Estado posterior: 1.810 aplicadas por regla, 6.076 pendientes y cuatro cuarentenas; 7.886 maestros.

El ensayo integral en una copia temporal publicó 57.007 filas de 137 sitios y 268.561 relaciones de
clasificación. Verificó importes, alta manual, integridad y claves foráneas.
La base real continúa sin publicación ni exclusiones técnicas aprobadas.
Detalle: `outputs/catalogo/verificacion_operaciones.json`.

## Respaldo, comprobación y límites

Respaldo SQLite consistente al arrancar y antes de importar/publicar en `data/backups`.
Revisiones, altas y decisiones técnicas usan transacciones y auditoría.
Pruebas: `python -m unittest discover -s db -p "test_*.py"`.
Ensayo real sobre copia temporal: `python -m db.verify_operations`.

Aplicación local monousuario: escucha únicamente en 127.0.0.1, valida Host, Origin y token CSRF.
El nombre del responsable es declarado, no una identidad autenticada. No desplegar este servidor
como aplicación multiusuario sin incorporar autenticación, permisos y operación de producción.
País y moneda desconocidos siguen vacíos. No se incorporaron inferencias de marcas ni nomenclatura
técnica final. La taxonomía pendiente y las fusiones de códigos requieren revisiones específicas.
