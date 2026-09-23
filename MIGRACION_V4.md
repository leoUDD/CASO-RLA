# Migración relacional v4

Implementación aditiva y compatible: se crea una copia nueva, sin reemplazar data/rla.sqlite3.
La copia validada es data/rla_modelo_v4.sqlite3. El respaldo y los controles exactos están
en outputs/migracion/verificacion_v4.json. La copia data/rla_v4.sqlite3 corresponde al primer
intento revertido y no debe usarse como versión migrada.

Incluye fabricantes/alias, países, familias, atributos/unidades, reglas/propuestas por campo,
clasificaciones originales y extensión comercial. Sitios, maestros, cargas e inventario
reciben nuevas columnas opcionales. No se asignan países, fabricantes ni taxonomía sin aprobación.

Se encontraron propuestas previas en standardization_proposals: se conservan completas.
Las nuevas propuestas con regla, campo y revisión usan field_standardization_proposals.
record_classifications permite normalizar las etiquetas de todas las filas, incluso si no hay
inventario publicado. Cada relación apunta a su fila y a una etiqueta de la misma fuente.

Compatibilidad deliberada: categories.parent_id, master_products.manufacturer/category_id y
inventory_snapshots.cost/replacement_cost/currency siguen existiendo. No se borran ni se
sincronizan automáticamente con sus alternativas nuevas. Son columnas legadas a retirar
cuando el servicio de aplicación use las nuevas relaciones. Esto es la primera fase de la
migración, no una afirmación de 3FN completa del esquema operativo.

El catálogo e inventario actuales están vacíos. Por eso no hay atributos de producto ni importes
publicados que trasladar; los originales y normalizados permanecen completos en staging.
No se publica la carga ni se resuelven sus cuatro filas en cuarentena durante la migración.

Reproducir en otro destino nuevo:

```powershell
python -m db.migrate_v4 --source data/rla.sqlite3 --target data/otra_copia_v4.sqlite3
python -m unittest discover -s db -p "test_*.py" -v
```

El programa rechaza sobrescribir destinos. Usa backup de SQLite, transacción para esquema y
datos, fingerprints de todas las columnas originales y controles de integridad/FK. Una nueva
invocación de apply_migration sobre la versión 4 no repite la migración.

Siguiente integración: adaptar importación/publicación para poblar las nuevas relaciones en
cargas futuras, validar decimal canónico y atributos por familia, poblar equivalencias aprobadas,
retirar columnas legadas y cambiar la base activa solo después de probar el flujo completo.
El importador ahora apunta por defecto a data/rla_modelo_v4.sqlite3 y completa las relaciones
de etiquetas por cada nueva carga. Los comandos de análisis/matching conservan sus destinos
anteriores; no se ha publicado inventario ni cambiado sus fuentes automáticamente.
