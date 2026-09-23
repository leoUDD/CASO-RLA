# Comparación controlada: carga 1

RapidFuzz 3.14.6 se instaló en .vendor. Reproducción: instalar requirements-matching.txt
en el entorno Python, o usar `python -m pip install --target .vendor -r requirements-matching.txt`.
Ejecutar `python -m db.compare_rapidfuzz` desde la raíz del proyecto.

Se mantuvieron los mismos 77.179 pares, seis campos, reglas, normalización y redondeo a un decimal.
Se compararon SequenceMatcher, RapidFuzz fuzz.ratio y fuzz.token_sort_ratio, sin procesador adicional.
Los pares incluidos por marca/modelo o descripción exacta se mantienen independientemente del umbral.

Con umbral 80, el método anterior seleccionó 9.920 pares. ratio seleccionó 10.061:
conserva todos los anteriores y agrega 141. token_sort_ratio seleccionó 9.211: conserva 8.736,
agrega 475 y retira 1.184. Estas diferencias no indican aciertos ni errores sin etiquetas humanas.

Tiempo local mediano de tres ejecuciones de scores y redondeo: SequenceMatcher 4,3877 s,
ratio 0,0571 s y token_sort_ratio 0,2070 s. Excluye lectura de datos, generación de pares,
reglas de diferencias y generación del informe; no implica esa mejora en el flujo completo.

El informe comparacion.html permite examinar cambios y umbrales 75, 80, 85, 90 y 95.
comparacion.json contiene todos los cambios de score. rapidfuzz_candidatos.json contiene
los 10.061 candidatos obtenidos usando ratio con las reglas existentes.

Recomendación provisional: ratio como alternativa principal por velocidad y continuidad;
token_sort_ratio como señal complementaria a evaluar. Antes de cambiar la política de selección,
revisar una muestra de los nuevos candidatos, de los retirados por token_sort y de coincidencias
estables; etiquetar equivalentes, diferentes o inciertos y ajustar umbral con esas evidencias.

El informe anterior y las decisiones se conservaron. RapidFuzz se aplicó al experimento y produjo
su propia lista completa; el comando habitual de matching mantiene SequenceMatcher hasta decidir
el cambio de método. No se hicieron fusiones ni publicación del catálogo.
