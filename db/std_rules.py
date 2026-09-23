"""Reglas de estandarización (versión std-1). Funciones puras de texto: sin base de datos.

Editar aquí para agregar sitios, marcas o patrones de familia. Las reglas proponen;
las decisiones de revisores guardadas en SQLite prevalecen sobre ellas.
"""
from functools import lru_cache
import re
import unicodedata

RULES_VERSION = 'std-1'


def key(text):
    """Clave compacta: mayúsculas, sin tildes, solo letras y dígitos (comparar marcas, modelos)."""
    if text is None:
        return ''
    t = unicodedata.normalize('NFKD', str(text).upper())
    return re.sub(r'[^A-Z0-9]', '', ''.join(c for c in t if not unicodedata.combining(c)))


def words(text):
    """Clave con espacios: mayúsculas, sin tildes ni signos (reglas por palabra y búsqueda)."""
    if text is None:
        return ''
    t = unicodedata.normalize('NFKD', str(text).upper())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9]+', ' ', t)).strip()


# ---------------------------------------------------------------- sitios
COUNTRIES = {'CL': 'Chile', 'CO': 'Colombia', 'PE': 'Perú', 'PA': 'Panamá', 'MX': 'México', 'US': 'Estados Unidos'}
COUNTRY_RULES = [  # (regex sobre código + nombre del sitio, país). Gana la primera coincidencia.
    (r'PANAM', 'PA'),
    (r'MEXICO', 'MX'),
    (r'MIAMI', 'US'),
    (r'PERU|LIMA|MIRAFLO|SAN ISIDRO|\bAQP\b|INKA|INCA OLD|CASA ANDINA|COSTA DEL SOL', 'PE'),
    (r'COLOM|BOGOTA|^H ?C |H\.C\.|CARTAGEN|MEDELLIN|EFCOL|\bCOL ?22\b|FONTANA|SUITE JONES|PARQUE 93', 'CO'),
    (r'CHILE|SANTIAGO|STGO|CONCEPCION|\bCNC\b|ANTOFAGAST|VINA DEL MAR|TEMUCO|VALDIVIA|PTO VARAS|PTA ARENAS|'
     r'PTO MONTT|RENACA|PUCON|COYHAIQUE|CHILLAN|VITACURA|LAS CONDES|LA DEHESA|PROVIDENCIA|RINCONADA|'
     r'O HIGGINS|PARQUE ARAUCO|MANQUEHUE|OFICINA CENTRAL', 'CL'),
]
SITE_TYPES = ['Bodega / CD', 'Sede de operación', 'Servicio técnico', 'Venta', 'Descarte / baja',
              'Ajuste / no ubicado', 'Administrativo']
SITE_TYPE_RULES = [  # (tipo, regex). Sin coincidencia → Sede de operación.
    ('Descarte / baja', r'BOTAR|REMATE|FUERA DE USO|EQUIPO MALO|REBAJAR'),
    ('Venta', r'\bVENTA\b'),
    ('Servicio técnico', r'SERVICIO TECNICO|SSTT|REPAIR|MERMA'),
    ('Ajuste / no ubicado', r'GHOST|INV 2023|INVENTARIO 20|DIFERENCIAS|AJUSTE|RASTREAR|FUERA COL|FUERA PERU|'
                            r'NO USAR|TRANSMET|TRANSITO|\bOLD\b|PROYECTOS 20'),
    ('Administrativo', r'ADMINISTRACI|CORPORATIVO|OFICINA CENTRAL|RLA MEXICO'),
    ('Bodega / CD', r'^CD |\bCD\b|BODEGA|REUTILIZAR|\bSAV\b'),
]
AVAILABLE_SITE_TYPES = {'Bodega / CD', 'Sede de operación'}  # stock que cuenta como disponible
CODE_COUNTRY = re.compile(r'^(CO|PE|CL|PA|MX)[\s_\-]|(?<=[_\d])(CO|CL|PE|PA|MX)$')


def code_country(code):
    m = CODE_COUNTRY.search(str(code or ''))
    return (m.group(1) or m.group(2)) if m else None


def site_country(site_code, site_name, prefixed_share=0.0, prefix_country=None, dominance=0.0):
    """(país, fuente). Palabra clave geográfica; si no, prefijo dominante de los códigos del sitio."""
    text = f'{site_code} {site_name}'
    for pattern, country in COUNTRY_RULES:
        if re.search(pattern, words(text)) or re.search(pattern, text.upper()):
            return country, 'palabra clave'
    if prefix_country and prefixed_share >= 0.30 and dominance >= 0.70:
        return prefix_country, 'prefijo de códigos'
    return None, 'sin evidencia'


def site_type(site_code, site_name):
    text = words(f'{site_code} {site_name}')
    for kind, pattern in SITE_TYPE_RULES:
        if re.search(pattern, text):
            return kind
    return 'Sede de operación'


# ---------------------------------------------------------------- nomenclatura
REPLACEMENTS = [  # (regex, reemplazo), en orden
    (r'ò', 'ó'), (r'à', 'á'), (r'è', 'é'), (r'ì', 'í'), (r'ù', 'ú'),
    (r'[–—]', '-'), (r'\\', '/'), (r'®|™', ''),
    (r'\s*\((?:CL|CO|PE|PA|MX)\)', ''),                                   # el país vive en el sitio
    (r'\(?\s*\bno\s*usar(?:\s*definitivo)?\s*\)?|\beliminar\b|\bficha mala\b', ' '),  # estado operativo
    (r'(\d)\s*(?:¨|\'\'|"+|”|pulgadas?\b|pulg\b\.?)', r'\1 in '),
    (r'(\d)\s*(?:mtrs?\.?|mts?\.?|metros?)(?=\W|$)', r'\1 m'),
    (r'(\d)\s*(?:cms?\.?|cent[ií]metros?)(?=\W|$)', r'\1 cm'),
    (r'\b(\d{1,2})\.(\d{3})\s*(?=ansi|l[uú]m)', r'\1\2 '),                # 6.000 lúmenes → 6000
    (r'\bansi\s*l[uú]menes\b|\bansil[uú]menes\b|\bl[uú]menes\s*ansi\b', 'ANSI lm'),
    (r'\bM\s*-\s*M\b', 'macho-macho'), (r'\bM\s*-\s*H\b', 'macho-hembra'), (r'\bH\s*-\s*H\b', 'hembra-hembra'),
    (r'\s*/\s*', ' / '), (r'\s*\|\s*', ' / '), (r'\(\s*\)', ''), (r'\s+', ' '), (r'^[\s\-/.,]+|[\s\-/.,]+$', ''),
]
ACRONYMS = {'HDMI', 'VGA', 'LED', 'LCD', 'USB', 'SDI', 'XGA', 'WXGA', 'WUXGA', 'DMX', 'UPS', 'TV', 'BNC', 'XLR',
            'RCA', 'DVI', 'HD', 'ANSI', 'AWG', 'PC', 'CPU', 'IP', 'POE', 'DJ', 'UHF', 'VHF', 'RF', 'AV', 'DVD',
            'PAR', 'RGB', 'RGBW', 'UTP', 'CAT', 'DSP', 'EDID', 'MIDI', 'PTZ', 'NFC', 'GB', 'TB', 'W', 'VA', 'ML'}
ACCENTS = {
    'microfono': 'micrófono', 'microfonos': 'micrófonos', 'inalambrico': 'inalámbrico', 'alambrico': 'alámbrico',
    'dinamico': 'dinámico', 'camara': 'cámara', 'telon': 'telón', 'energia': 'energía', 'iluminacion': 'iluminación',
    'traduccion': 'traducción', 'interpretacion': 'interpretación', 'proyeccion': 'proyección', 'conexion': 'conexión',
    'extension': 'extensión', 'bateria': 'batería', 'audifono': 'audífono', 'audifonos': 'audífonos', 'tripode': 'trípode',
    'electrico': 'eléctrico', 'electrica': 'eléctrica', 'optica': 'óptica', 'senal': 'señal', 'modulo': 'módulo',
    'modulos': 'módulos', 'salon': 'salón', 'lamina': 'lámina', 'metalico': 'metálico', 'plastico': 'plástico',
    'tactil': 'táctil', 'portatil': 'portátil', 'computacion': 'computación', 'edicion': 'edición', 'grafica': 'gráfica',
    'tecnico': 'técnico', 'sonorizacion': 'sonorización', 'informatica': 'informática', 'musica': 'música',
    'transmision': 'transmisión', 'votacion': 'votación', 'direccion': 'dirección',
}
OPERATIONAL_FLAG = re.compile(r'\bno\s*usar|\belimin|\bficha mala\b|\bobsolet|\bprobar\b|item missing', re.I)
PLACEHOLDERS = {'NA', 'N/A', 'NULL', 'NONE', 'S/N', 'SN', 'S/M', 'SM', 'SIN MARCA', 'SIN DATO', '-', '--', '---',
                '----', '.', 'GENERICO', 'GENERICA', '0'}
EMPTY_KEYS = {key(p) for p in PLACEHOLDERS} | {'', 'SINMARCA'}


def _casing(text):
    letters = [c for c in text if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) >= 0.7:  # TODO EN MAYÚSCULAS → oración
        text = ' '.join(w if words(w) in ACRONYMS or re.search(r'\d', w) else w.lower() for w in text.split(' '))
    return text[:1].upper() + text[1:]


def _word(w):
    if words(w) in ACRONYMS:
        return re.sub(r'[A-Za-z]+', lambda m: m.group().upper(), w)
    fixed = ACCENTS.get(w.lower())
    if fixed:
        return fixed.capitalize() if w[:1].isupper() else fixed
    return w


@lru_cache(maxsize=None)
def normalize_name(description):
    """Descripción → nombre base estándar. None si no hay texto útil ('.', vacío)."""
    if description is None or len(key(description)) < 3:
        return None
    t = str(description)
    for pattern, repl in REPLACEMENTS:
        t = re.sub(pattern, repl, t, flags=re.IGNORECASE)
    t = ' '.join(_word(w) for w in _casing(t.strip()).split(' ')).strip()
    return (t[:1].upper() + t[1:]) or None


def standard_name(description, brand=None, model=None):
    """Nombre base + marca + modelo, sin repetirlos si ya están en la descripción."""
    base = normalize_name(description)
    if base is None:
        return None
    k, extra = key(base), []
    for x in (brand, model):
        if x and key(x) and key(x) not in k:
            extra.append(x)
            k += key(x)  # evita "AKG AKG" cuando marca y modelo coinciden
    return ' '.join([base] + extra)


def operational_status(description):
    if normalize_name(description) is None:
        return 'Revisar: descripción inválida'
    if OPERATIONAL_FLAG.search(str(description)):
        return 'Revisar: marcado no usar / eliminar'
    return 'Activo'


# ---------------------------------------------------------------- marcas y modelos
BRAND_ALIASES = {  # clave → nombre canónico, para lo que la clave no une sola
    'BLACKMAGIC': 'BLACKMAGIC DESIGN', 'BLACKMAGICDESIGN': 'BLACKMAGIC DESIGN',
    'ALLENHEAT': 'ALLEN & HEATH', 'ALLENHEATH': 'ALLEN & HEATH', 'POLARLIGTH': 'POLAR LIGHT',
    'DALITE': 'DA-LITE', 'TPLINK': 'TP-LINK', 'DLINK': 'D-LINK', 'ELECTROVOICE': 'ELECTRO-VOICE',
    'TVONE': 'TV ONE', 'DSAN': 'DSAN', 'ANALOGWAY': 'ANALOG WAY',
    'SENHEIZER': 'SENNHEISER', 'SENHEISER': 'SENNHEISER', 'SENNHEIZER': 'SENNHEISER',
    'BOSH': 'BOSCH',
}


def brand_key(brand):
    """Clave canónica de marca; None si es relleno ('GENERICO', 'S/M', '.')."""
    k = key(brand)
    if k in EMPTY_KEYS:
        return None
    alias = BRAND_ALIASES.get(k)
    return key(alias) if alias else k


def standard_model(model):
    if model is None:
        return None
    m = re.sub(r'\s+', ' ', re.sub(r'\s*[-–]\s*', '-', str(model).upper())).strip()
    return None if key(m) in EMPTY_KEYS else m


# ---------------------------------------------------------------- taxonomía y código
TAXONOMY = {  # familia → (categoría, código categoría, código familia)
    'Micrófonos': ('Audio', 'AUD', 'MIC'), 'Altavoces': ('Audio', 'AUD', 'ALT'),
    'Consolas de audio': ('Audio', 'AUD', 'CSL'), 'Amplificadores': ('Audio', 'AUD', 'AMP'),
    'Procesamiento de audio': ('Audio', 'AUD', 'PRA'), 'Accesorios de audio': ('Audio', 'AUD', 'ACA'),
    'Proyectores': ('Video', 'VID', 'PRY'), 'Monitores y televisores': ('Video', 'VID', 'MON'),
    'Pantallas LED': ('Video', 'VID', 'LED'), 'Pantallas de proyección': ('Video', 'VID', 'TEL'),
    'Cámaras': ('Video', 'VID', 'CAM'), 'Procesamiento y distribución de video': ('Video', 'VID', 'PRV'),
    'Reproducción de video': ('Video', 'VID', 'REP'), 'Accesorios de video': ('Video', 'VID', 'ACV'),
    'Computadores': ('Informática y redes', 'INF', 'COM'), 'Redes': ('Informática y redes', 'INF', 'RED'),
    'Impresoras': ('Informática y redes', 'INF', 'IMP'), 'Periféricos y almacenamiento': ('Informática y redes', 'INF', 'PER'),
    'Luminarias': ('Iluminación', 'ILU', 'LUM'), 'Control de iluminación': ('Iluminación', 'ILU', 'CTL'),
    'Accesorios de iluminación': ('Iluminación', 'ILU', 'ACI'),
    'Distribución eléctrica': ('Energía', 'ENE', 'DIS'), 'Respaldo y generación': ('Energía', 'ENE', 'RES'),
    'Interpretación simultánea': ('Interpretación y comunicaciones', 'ITC', 'SIM'),
    'Debate y votación': ('Interpretación y comunicaciones', 'ITC', 'DEB'),
    'Conferencia e intercomunicación': ('Interpretación y comunicaciones', 'ITC', 'CNF'),
    'Cables y adaptadores': ('Conectividad', 'CNX', 'CAB'),
    'Estructuras y montaje': ('Montaje y soporte', 'MNT', 'EST'),
    'Transporte y protección de equipos': ('Montaje y soporte', 'MNT', 'CAS'),
    'Mobiliario y oficina': ('Mobiliario y oficina', 'MOB', 'MOB'),
    'Consumibles y repuestos': ('Consumibles y repuestos', 'CSM', 'CSM'),
    'Servicios técnicos': ('Servicios', 'SRV', 'TEC'), 'Personal': ('Servicios', 'SRV', 'PSN'),
    'Transporte y viajes': ('Servicios', 'SRV', 'TRV'), 'Licencias': ('Servicios', 'SRV', 'LIC'),
    'Gastos y cargos': ('Cargos comerciales', 'CAR', 'GAS'),
    'Paquetes y soluciones': ('Paquetes y soluciones', 'PAQ', 'SOL'),
}
NAME_PATTERNS = {  # sobre el inicio del nombre estándar (words())
    'Debate y votación': r'^(MICROFONO.*DEBATE|UNIDAD (DE )?(DEBATE|VOTACION)|SISTEMA DE (DEBATE|VOTACION)|DICENTIS)\b',
    'Micrófonos': r'^MICROFONO\b',
    'Altavoces': r'^(ALTAVOZ|ALTAVOCES|PARLANTE|SUBWOOFER|SUB BAJO|SOUNDBAR|LINE ARRAY)\b',
    'Consolas de audio': r'^(CONSOLA (DE )?AUDIO|MEZCLADORA? (DE )?AUDIO|POWER MIXER|MIXER)\b',
    'Amplificadores': r'^AMPLIFICADOR\b',
    'Procesamiento de audio': r'^(PROCESADOR (DE )?AUDIO|CAJA DIRECTA|COMPRESOR|ECUALIZADOR|MATRIZ (DE )?AUDIO)\b',
    'Accesorios de audio': r'^(RECEPTOR.*(MICROFONO|MIC\b)|ATRIL (DE )?MICROFONO|SOPORTE (DE )?(MICROFONO|PARLANTE)|ANTENA|AUDIFONO)',
    'Proyectores': r'^(PROYECTOR|VIDEOPROYECTOR)\b',
    'Monitores y televisores': r'^(MONITOR|TELEVISOR|TV|PANTALLA TACTIL|PANTALLA \d|PLASMA|TOTEM)\b',
    'Pantallas LED': r'^(PANTALLA LED|PANEL LED|MODULOS? (DE )?LED|PANTALLA PIXEL)\b',
    'Pantallas de proyección': r'^(TELON|ECRAN|PANTALLA (DE )?PROYECCION|PANTALLA INFLABLE)\b',
    'Cámaras': r'^(CAMARA|VIDEOCAMARA|CCTV)\b',
    'Procesamiento y distribución de video': r'^(SWITCHER|ESCALADOR|MATRIZ (DE )?VIDEO|DISTRIBUIDOR (DE )?(VIDEO|VGA|HDMI|SDI)|PROCESADOR (DE )?VIDEO|EXTENSOR|CAPTURADORA|(CONVERSOR|CONVERTIDOR))\b',
    'Reproducción de video': r'^(REPRODUCTOR|SISTEMA WATCHOUT)\b',
    'Accesorios de video': r'^(LENTE|SOPORTE (DE )?(PROYECTOR|PLASMA|LCD|MONITOR|TV))\b',
    'Computadores': r'^(NOTEBOOK|LAPTOP|COMPUTADORA?|SERVIDOR|CPU|MAC ?BOOK|IMAC)\b',
    'Redes': r'^(SWITCH (DE )?RED|SWITCH \d|ROUTER|ACCESS POINT|PUNTO DE ACCESO)\b',
    'Impresoras': r'^(IMPRESORA|MULTIFUNCIONAL)\b',
    'Periféricos y almacenamiento': r'^(MOUSE|TECLADO|MEMORIA|PENDRIVE|DISCO DURO|LECTOR|TABLET|IPAD|PUNTERO)\b',
    'Luminarias': r'^(FOCO|LUMINARIA|CABEZA MOVIL|OPTIPAR|PAR LED|PAR \d|ROBOTICO|ROBOTIZADO|LASER|WASH|BEAM|REFLECTOR|FRESNEL)\b',
    'Control de iluminación': r'^(CONSOLA (DE )?ILUMINACION|DIMMER|SPLITTER|CONTROLADOR DMX)\b',
    'Accesorios de iluminación': r'^SOPORTE (DE )?ILUMINACION\b',
    'Distribución eléctrica': r'^(TABLERO|DISTRIBUIDOR (ELECTRICO|DE CORRIENTE)|CAJA DE DISTRIBUCION|ZAPATILLA)\b',
    'Respaldo y generación': r'^(UPS|GENERADOR)\b',
    'Interpretación simultánea': r'^(RECEPTOR (DE )?(TRADUCCION|INFRARROJO|SENAL)|PUPITRE|CABINA|RADIADOR|TRANSMISOR (DE )?(TRADUCCION|INFRARROJO)|AUDIFONO PARA RECEPTOR|IDIOMA)',
    'Conferencia e intercomunicación': r'^(INTERCOMUNICADOR|RADIO|TELEFONO|SISTEMA (DE )?VIDEOCONFERENCIA|VIDEOCONFERENCIA)\b',
    'Cables y adaptadores': r'^(CABLE|CHICOTE|EXTENSION|CORDON|COPLA|ADAPTADOR|CONECTOR)\b',
    'Estructuras y montaje': r'^(TRUSS|ESTRUCTURA|TORRE|BASE (DE )?PISO|TRIPODE|PEDESTAL|RIGGING|RACK)\b',
    'Transporte y protección de equipos': r'^(CASE|FLIGHT CASE|BOLSO|MALETA|ESTUCHE|GABINETE)\b',
    'Mobiliario y oficina': r'^(MESA|SILLA|PAPELOGRAFO|ROTAFOLIO|PIZARRA|PODIO|ATRIL(?! DE MICROFONO)|BIOMBO|HOJAS)\b',
    'Consumibles y repuestos': r'^(TINTA|TONER|REPUESTO|PILA|BATERIA|CINTA|HUINCHA|AMARRA|AMPOLLETA|LAMPARA)\b',
    'Servicios técnicos': r'^(SERVICIO|CONFIGURACION|EDICION|HORA DE EDICION|MAPPING|MAPING|REGISTRO|GRABACION|STREAMING|ELECTROMONTAJE|DISENO|LANDING)\b',
    'Personal': r'^(OPERADOR|TECNICO|INTERPRETE|PERSONAL|COORDINADOR|DJ|PRODUCTOR|ASISTENTE)\b',
    'Transporte y viajes': r'^(TRANSPORTE|VIAJE|FLETE|TRASLADO)\b',
    'Licencias': r'^LICENCIA\b',
    'Gastos y cargos': r'^(COMISION|ALOJAMIENTO|ALIMENTACION|IMPREVISTOS|VIATICO|SUBARRIENDO)\b',
}
# Soluciones armadas ("Sistema de amplificación…", "Salón…", "Kit…"): solo si ninguna familia específica coincide.
FALLBACK_PATTERN = r'^(SISTEMA|SALON|SALA|KIT|PAQUETE|PACK|PLAN|SET|PROYECCION|AMPLIFICACION|SONIDO|AV|AUDIO Y VIDEO|ILUMINACION|AUDIO|VIDEO|STUDIO|ESTUDIO)\b'
LABEL_ALIASES = {  # etiqueta original de R2 (Report Group / EXCHANGEGROUP) → familia
    'Micrófonos': ['MICROFONOS', 'AUDIO MICROPHONE', 'MICROFONOS INALAMBRICOS', 'MICROFONOS ALAMBRICOS', 'MICROFONOS DE PODIUM', 'MICROFONO PODIUM', 'MIC PODIUM', 'MICROFONO HEADSET', 'MICROFONO DE CAMARA'],
    'Altavoces': ['ALTAVOCES', 'SUB BAJO ACTIVO', 'SOUNDBAR', 'SISTEMA ARRAY', 'LINE ARRY'],
    'Consolas de audio': ['CONSOLAS AUDIO', 'CONSOLAS DE AUDIO', 'POWER MIXER'],
    'Amplificadores': ['AMPLIFICADOREWS', 'SISTEMA DE AMPLIFICACION', 'AMPLIFICADORES'],
    'Procesamiento de audio': ['PROCESADORES DE AUDIO', 'CAJA DIRECTA', 'MATRIZ DE AUDIO', 'CONTROLADOR MIDI'],
    'Accesorios de audio': ['ACCESORIOS AUDIO', 'ACCESORIOS DE AUDIO', 'PERIFERICOS AUDIO', 'RECEPTOR MIC', 'ANTENA AUDIO', 'DISTRIBUIDOR DE ANTENAS', 'ATRIL DE MICROFONO', 'SOPORTE PARLANTE', 'AUDIFONOS'],
    'Proyectores': ['PROYECTORES', 'PROJECTOR', 'PROYECTORES LASER'],
    'Monitores y televisores': ['MONITORES Y TV', 'TELEVISORES MONITORES', 'PANTALLA TACTIL', 'PANTALLAS TACTILES', 'MONITORES'],
    'Pantallas LED': ['PANTALLA LED'],
    'Pantallas de proyección': ['TELONES', 'TELON ELECTRICO', 'TELON MECANO', 'TELON MANUAL', 'PANTALLA INFLABLE'],
    'Cámaras': ['CAMARA DE VIDEO', 'FOTOGRAFIA'],
    'Procesamiento y distribución de video': ['DISTRIBUIDOR DE VIDEO', 'EXTENSORES DE VIDEO', 'PROCESADOR DE VIDEO', 'SWITH DE VIDEO', 'MATRIZ DE VIDEO', 'ESCALADORES', 'ESCALER', 'SWITCHER/DISTRIBUIDOR'],
    'Reproducción de video': ['REPRODUCTORES VIDEO', 'SISTEMA WATCHOUT', 'DIGITAL SIGNAGE'],
    'Accesorios de video': ['ACCESORIOS DE VIDEO', 'ADAPTADORES DE VIDEO', 'SOPORTE PLASMA', 'SOPORTE LCD', 'SOPORTE PROYECTOR', 'SOPORTE WALL 4'],
    'Computadores': ['NOTEBOOK', 'LAPTOP', 'CPU', 'COMPUTADORES', 'SERVIDORES'],
    'Redes': ['REDES', 'SWITCH DE RED', 'ROUTERS', 'NETWORKING'],
    'Impresoras': ['IMPRESORA', 'IMPRESORAS'],
    'Periféricos y almacenamiento': ['PERIFERICOS PC', 'MOUSE INALAMBRICO', 'MEMRORIAS', 'DISPOSITIVOS MOVILES', 'LECTORES CODIGOS', 'ACCESORIOS INFORMATICOS'],
    'Luminarias': ['FOCOS LED', 'FOCO PAR 64', 'ROBOTIZADO', 'LASER'],
    'Control de iluminación': ['CONSOLA DE ILUMINACION', 'SPLITTER ILUMINACION', 'POWER DIMMER', 'DIMMER'],
    'Accesorios de iluminación': ['PERIFERICO ILUMINACION', 'SOPORTE ILUMINACION'],
    'Distribución eléctrica': ['TABLERO ELECTRICO', 'PERIFERICOS ELECTRICIDAD'],
    'Respaldo y generación': ['UPS', 'GENERADOR'],
    'Interpretación simultánea': ['SISTEMA DE INTERPRETACION SIMULTANEA', 'TRADUCCION SIMULTANEA', 'AUDIFONO TRADUCCION', 'RECEPTOR DE TRADUCCION', 'PUPITRE', 'CABINAS'],
    'Debate y votación': ['MIC DEBATE', 'SISTEMA DE DEBATE', 'SISTEMA DEBATE', 'SISTEMA DE VOTACION'],
    'Conferencia e intercomunicación': ['VIDEOCONFERENCIA', 'VIDEO CONFERENCIA', 'TELEFONO CONFERENCIA', 'INTERCOMUNICADORES', 'RADIOS'],
    'Cables y adaptadores': ['CABLES', 'CABLE', 'CABLES DE AUDIO', 'CABLES VIDEO', 'CABLES DE ENERGIA', 'CABLES DE RED', 'CABLES DE DATOS', 'CABLES TRADUCCION', 'CABLES ILUMINACION', 'CABLE S'],
    'Estructuras y montaje': ['ACCESORIOS MONTAJE', 'RIGGING PANTALLA LED', 'ESTRUCTURA', 'BASE PISO'],
    'Transporte y protección de equipos': ['CASES', 'BOLSOS'],
    'Mobiliario y oficina': ['MOBILIARIO', 'ARTICULOS DE OFICINA', 'PAPELOGRAFO'],
    'Consumibles y repuestos': ['INSUMOS', 'REPUESTOS', 'TINTA IMPRESORA', 'BATERIAS'],
    'Servicios técnicos': ['SERVICIO TECNICO', 'CONFIGURACION REDES', 'EDICION', 'REGISTRO AUDIO', 'MAPING'],
    'Personal': ['LABOR', 'PERSONAL', 'OPERADOR', 'INTERPRETES', 'DJ'],
    'Transporte y viajes': ['TRANSPORTE', 'VIAJES', 'VIAJE SUR'],
    'Licencias': ['LICENCIA'],
    'Gastos y cargos': ['IMPREVISTOS', 'COMISION AGENCIA', 'ALOJAMIENTO', 'ALIMENTACION'],
}
# Etiquetas originales que son cajones genéricos: si contradicen un nombre específico, gana el nombre.
GENERIC_FAMILIES = {'Accesorios de video', 'Accesorios de audio', 'Periféricos y almacenamiento',
                    'Accesorios de iluminación', 'Estructuras y montaje', 'Consumibles y repuestos'}
LABEL_TO_FAMILY = {words(alias): family for family, aliases in LABEL_ALIASES.items() for alias in aliases}
assert set(NAME_PATTERNS) | {'Paquetes y soluciones'} == set(TAXONOMY)
assert set(LABEL_ALIASES) <= set(TAXONOMY)

# Métodos que dan una clasificación automática (el resto queda para revisión humana).
AUTO_METHODS = {'Alta confianza', 'Por nombre', 'Por nombre (etiqueta genérica)', 'Por etiqueta', 'Por tipo'}


def family_by_name(name):
    """Familia sugerida por el nombre: nombre, None o 'CONFLICTO:a/b'."""
    k = words(name)
    hits = [f for f, p in NAME_PATTERNS.items() if re.search(p, k)]
    if 'Debate y votación' in hits:  # más específica que "Micrófonos"
        hits = ['Debate y votación']
    if not hits and re.search(FALLBACK_PATTERN, k):
        return 'Paquetes y soluciones'
    if len(hits) > 1:
        return 'CONFLICTO:' + '/'.join(hits)
    return hits[0] if hits else None


def family_by_labels(*labels):
    families = {LABEL_TO_FAMILY.get(words(v)) for v in labels if v}
    families.discard(None)
    if len(families) > 1:
        return 'CONFLICTO:' + '/'.join(sorted(families))
    return families.pop() if families else None


def classify(name, labels=(), product_type=None, package=None):
    """(familia o None, método). Método 'Revisar: …' significa que requiere decisión humana."""
    if name is None:
        return None, 'Revisar: descripción inválida'
    n, e = family_by_name(name), family_by_labels(*labels)
    n_ok = n is not None and not n.startswith('CONFLICTO')
    e_ok = e is not None and not e.startswith('CONFLICTO')
    if n is not None and not n_ok:
        return None, 'Revisar: conflicto (' + n[10:] + ')'
    if n_ok and e_ok:
        if n == e:
            return n, 'Alta confianza'
        if e in GENERIC_FAMILIES and n not in GENERIC_FAMILIES:
            return n, 'Por nombre (etiqueta genérica)'
        if n == 'Paquetes y soluciones':
            return e, 'Por etiqueta'
        return None, f'Revisar: conflicto ({n} / {e})'
    if package == 'PACKAGE' and not n_ok and not e_ok:
        return 'Paquetes y soluciones', 'Por tipo'
    if n_ok:
        return n, 'Por nombre'
    if e_ok:
        return e, 'Por etiqueta'
    if e is not None:
        return None, 'Revisar: conflicto (' + e[10:] + ')'
    if product_type == 'LABOR':
        return 'Personal', 'Por tipo'
    return None, 'Revisar: sin regla'


def code_prefix(family):
    _, cat, fam = TAXONOMY[family]
    return f'{cat}-{fam}'


def duplicate_key(name, brand_k, model):
    """Clave para candidatos a duplicado: mismo nombre base, marca y modelo estandarizados."""
    return f'{key(name)}|{brand_k or ""}|{key(model)}'
