# Propuesta de estandarización — borrador 1

Estado: propuesta revisable; no aplicada al catálogo. La taxonomía y las equivalencias están
en outputs/estandarizacion/propuesta.json; la vista de consulta está en propuesta.html.
Se genera con `python -m db.propose_taxonomy` usando únicamente datos locales de la carga 1.

## Decisiones de estructura

Doce categorías: Audio; Video; Informática y redes; Iluminación; Energía; Interpretación y
comunicaciones; Conectividad; Montaje y soporte; Mobiliario y oficina; Consumibles y repuestos;
Servicios; Cargos comerciales. Contienen 36 familias detalladas en el archivo JSON.

Los cables se agrupan en Conectividad y se diferencian por función/señal y conectores. Es una
decisión propuesta para evitar repartir el mismo tipo de cable entre Audio, Video y Accesorios.
Adaptadores específicos de video permanecen provisionalmente en Accesorios de video: antes
de aprobar, decidir si todos los adaptadores físicos deben migrar a Conectividad.

No confundir familia con tipo ITEM/LABOR/MISCCHARGE/PARTS, paquete, serialización, país,
unidad comercial o subarriendo. Estas dimensiones se conservan por separado. Un PACKAGE no
se renombra como unidad individual; se conserva su composición pendiente si no está disponible.
Un servicio puede estar registrado como ITEM: señalar la discrepancia, nunca corregir Type por inferencia.

## Reglas propuestas para nombres

Separar nombre original, nombre propuesto y nombre aprobado. Plantilla por familia:
tipo específico + atributos discriminantes + fabricante + modelo. Omitir desconocidos sin inventarlos.
Las plantillas usan marcadores descriptivos y no son aún un motor de extracción.

Ejemplos reales, con propuestas editoriales aún no aplicadas:

- Código 10063, fila 720: “Microfono Alambrico Dinámico”, SHURE SM-58.
  Propuesta: **Micrófono dinámico alámbrico SHURE SM-58**. Patrón polar y frecuencia desconocidos.
- Código 10208, fila 2474: “Cable BNC M-M 30 metros”.
  Propuesta: **Cable BNC macho a BNC macho 30 m**. M-M requiere aprobar ese alias de género.
  La marca AMERICAN AUDIO y el modelo registrado “16 AWG” se conservan; revisar si ese modelo
  corresponde realmente a calibre antes de incluirlo como modelo canónico.
- Código 10209, fila 2540: “Cable BNC M-M 20 metros”.
  Propuesta: **Cable BNC macho a BNC macho 20 m**. No unir con 10208: distinta longitud.
- Código 11133, fila 12956: “Proyector 6.000 Ansilumenes / Formato 4:3 / XGA LCD”, NEC PA-600X.
  Propuesta: **Proyector LCD XGA 4:3 6000 ANSI lm NEC PA-600X**. Se conserva XGA tal como figura;
  no inferir resolución nativa ni relación de tiro. Normalizar Ansilumenes a ANSI lm requiere aprobar el alias.
- Código 02030405, fila 8: “Micrófono de Podio 18\"\"”, SHURE MX418D/C.
  Propuesta provisional: **Micrófono de podio SHURE MX418D/C**. Conservar la medida original en
  observaciones hasta confirmar que las comillas duplicadas significan pulgadas; no eliminarla del historial.

## Atributos y unidades

Cada atributo necesita nombre estable, tipo (texto/decimal/booleano/catálogo), unidad admitida,
valor original, valor propuesto, evidencia y estado. Longitud en m, dimensiones de panel en m,
pixel pitch en mm, diagonal en in y capacidad en GB; convertir solo con unidad explícita.
No convertir W a VA, no completar ANSI cuando la fuente solo dice lúmenes, no tratar números
de modelo como medidas. Mantener resolución observada separada de resolución nativa confirmada.

El país es una propiedad de un sitio mapeado por un responsable; no inferirlo por CO/PE/CL
en códigos. La moneda y la fecha de corte requieren fuente explícita. Fuente de carga y país
no son sinónimos. Un servicio de transporte necesita origen/destino propios, distintos del país del sitio.

## Equivalencias

Se revisaron 266 valores distintos por campo en cinco clasificaciones. Un mismo texto en dos
campos cuenta dos veces. El JSON conserva cada valor, conteo de códigos y hasta tres ejemplos.
Los alias explícitos de Report Group y EXCHANGEGROUP producen sugerencias. Los otros campos
aportan contexto y nunca prevalecen automáticamente. Se eliminan tildes/mayúsculas solo para comparar.

Consola, monitor, procesadores, control y accesorios genéricos requieren descripción adicional.
Etiquetas contables numéricas, 104728, RPG1, DEPT1, COMODIN y valores mixtos no se convierten
en categorías. FOTOGRAFIA, CABINAS, BATERIAS y otras etiquetas potencialmente amplias requieren
validar que el producto concreto corresponda a la familia sugerida. El mapeo de etiqueta por sí solo
no es suficiente para aprobar un registro.

Resultados: 3.344 propuestas por revisar; 4.541 pendientes; 1 conflicto entre familias; 4 en cuarentena.
Estos estados suman los 7.890 códigos. No representan cobertura de clasificación validada.
Conflicto: XXX317, fila 56744, “Microfono de Debate”: Report Group indica MIC DEBATE y
EXCHANGEGROUP indica MICROFONOS INALAMBRICOS. Propuesta de revisión: decidir si la función
de debate es la familia y la conectividad inalámbrica un atributo, sin borrar las etiquetas originales.

## Incorporación posterior a SQL

- categories: categoría y familia, con identificadores estables, estado y versión de taxonomía.
- manufacturers y manufacturer_aliases: marcas canónicas y equivalencias aprobadas.
- countries y relación sites.country_id opcional: poblar solo con evidencia validada.
- attribute_definitions y family_attributes: atributos tipados y unidades permitidas por familia.
- product_attribute_values: valor, unidad, evidencia de carga/fila y estado de revisión.
- classification_rules: campo/valor original, destino propuesto, condiciones, versión y aprobación.
- product_standardization: propuesta y aprobación por campo, sin sobrescribir el original.

Estas extensiones todavía no se aplican. La base actual y las decisiones de duplicidad se conservan.
Primero aprobar convenciones estructurales; después implementar y probar reglas por familias,
empezando con cables, micrófonos y proyectores. Medir cobertura y errores en una muestra antes
de aplicar masivamente. RapidFuzz queda como herramienta auxiliar después de estructurar atributos.
