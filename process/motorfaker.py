"""
NAHUAL - Motor de Generación Orgánica (Process/MotorFaker.py)
Responsabilidad: Generar datos realistas y coherentes usando Faker (es_MX).
Optimizado para rendimiento en volúmenes bajos/medios mediante pre-resolución de callbacks.

CARACTERÍSTICAS:
- Fusiona capacidades base con diccionarios temáticos externos
- Soporta lambdas, funciones Faker, y valores estáticos
- Detección inteligente de tipos de columna
"""

import logging
import random
import sys
from pathlib import Path
from typing import List, Dict, Any, Callable, Union
from faker import Faker

logger = logging.getLogger(__name__)

# Inicializamos el Faker 100% mexicano
try:
    fake = Faker('es_MX')
    logger.debug("✅ Faker inicializado con locale 'es_MX'")
except Exception as e:
    logger.warning(f"⚠️ No se pudo cargar 'es_MX', usando default: {e}")
    fake = Faker()


# ============================================================================
# CARGA DE DICCIONARIOS TEMÁTICOS EXTERNOS
# ============================================================================
def _cargar_diccionarios_tematicos() -> Dict[str, Callable]:
    """
    Intenta cargar el diccionario temático desde 'generables/faker_chingadere.py'
    o 'generables/generables_faker.py' (el nombre que decidas).
    
    Returns:
        Diccionario con capacidades adicionales o vacío si no encuentra
    """
    tematicas = {}
    
    # Posibles rutas del archivo de diccionarios temáticos
    posibles_rutas = [
        Path("generables/capacidades_faker.py"),
        #recordar añadir un extra en caso de que la gente quiera usar sus propios diccionarios temáticos sin tocar el repo original
    ]
    
    for ruta in posibles_rutas:
        if ruta.exists():
            logger.info(f"📚 Cargando diccionario temático desde: {ruta}")
            try:
                # Importación dinámica del módulo
                import importlib.util
                spec = importlib.util.spec_from_file_location("tematicas", ruta)
                if spec and spec.loader:
                    modulo_tematicas = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(modulo_tematicas)
                    
                    # Buscar el diccionario principal (puede llamarse CAPACIDADES, DATOS, o TEMATICAS)
                    for nombre_var in ['CAPACIDADES', 'DATOS', 'TEMATICAS', 'generadores']:
                        if hasattr(modulo_tematicas, nombre_var):
                            tematicas = getattr(modulo_tematicas, nombre_var)
                            logger.info(f"   ✅ Cargadas {len(tematicas)} capacidades temáticas")
                            break
                    
                    # Si no encontró variable específica, buscar cualquier dict grande
                    if not tematicas:
                        for attr_name in dir(modulo_tematicas):
                            attr = getattr(modulo_tematicas, attr_name)
                            if isinstance(attr, dict) and len(attr) > 5:
                                tematicas = attr
                                logger.info(f"   ✅ Cargado diccionario temático '{attr_name}' con {len(tematicas)} items")
                                break
                    
                    return tematicas
                    
            except Exception as e:
                logger.warning(f"   ⚠️ Error cargando {ruta}: {e}")
            break  # Si encontró el archivo pero falló, no seguir buscando
    
    logger.info("📚 No se encontró diccionario temático externo. Usando solo capacidades base.")
    return tematicas


# ============================================================================
# DICCIONARIO BASE DE CAPACIDADES
# ============================================================================
CAPACIDADES_BASE: Dict[str, Callable] = {
    # === Personales Básicas ===
    'nombre': fake.name,
    'nombre_completo': fake.name,
    'primer_nombre': fake.first_name,
    'apellido': fake.last_name,
    'email': fake.email,
    'telefono': fake.phone_number,
    'direccion': fake.address,
    'ciudad': fake.city,
    'estado': fake.state,
    'pais': fake.country,
    'codigo_postal': fake.postcode,
    'rfc': fake.rfc,
    'curp': fake.curp,
    'fecha_nacimiento': fake.date_of_birth,
    'edad': lambda: random.randint(18, 90),
    'genero': lambda: random.choice(['Masculino', 'Femenino', 'Otro', 'Prefiero no decirlo']),
    'estado_civil': lambda: random.choice(['Soltero/a', 'Casado/a', 'Divorciado/a', 'Viudo/a', 'Unión libre']),
    
    # === Entorno Laboral / Financiero ===
    'empresa': fake.company,
    'cargo': fake.job,
    'departamento': lambda: random.choice(['Ventas', 'Sistemas', 'Recursos Humanos', 'Contabilidad', 'Marketing', 'Operaciones', 'Legal']),
    'salario': lambda: round(random.uniform(8000.0, 150000.0), 2),
    'salario_anual': lambda: round(random.uniform(96000.0, 1800000.0), 2),
    'tarjeta_credito': fake.credit_card_number,
    'clabe': lambda: ''.join([str(random.randint(0, 9)) for _ in range(18)]),
    'banco': lambda: random.choice(['BBVA', 'Santander', 'Banamex', 'Banorte', 'Scotiabank', 'HSBC']),
    
    # === Sistemas / Ciberseguridad ===
    'id': fake.uuid4,
    'uuid': fake.uuid4,
    'ip': fake.ipv4,
    'ipv6': fake.ipv6,
    'mac': fake.mac_address,
    'password': fake.password,
    'username': fake.user_name,
    'user_agent': fake.user_agent,
    'url': fake.url,
    'dominio': fake.domain_name,
    
    # === Fechas y Tiempo ===
    'fecha': fake.date,
    'fecha_hora': fake.date_time,
    'fecha_futura': fake.future_date,
    'fecha_pasada': fake.past_date,
    'hora': fake.time,
    'mes': lambda: random.choice(['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']),
    'dia_semana': lambda: random.choice(['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']),
    
    # === Texto y Lenguaje ===
    'texto': fake.text,
    'oracion': fake.sentence,
    'parrafo': fake.paragraph,
    'palabra': fake.word,
    'titulo': fake.sentence,
    'descripcion': fake.paragraph,
    
    # === Números y Estadísticas ===
    'entero': lambda: random.randint(0, 10000),
    'decimal': lambda: round(random.uniform(0, 1000), 2),
    'porcentaje': lambda: random.randint(0, 100),
    'booleano': lambda: random.choice([True, False]),
    
    # === Caos / Pruebas de estrés ===
    'id_caos': lambda: fake.bothify(text='????-########-????'),
    'basura': lambda: fake.lexify(text='???????????????'),
    'regex': lambda: fake.bothify(text='???-###-???')
}

# Cargar diccionarios temáticos externos
CAPACIDADES_TEMATICAS = _cargar_diccionarios_tematicos()

# Fusionar: Base + Temáticas (las temáticas sobreescriben en caso de conflicto)
CAPACIDADES = {**CAPACIDADES_BASE, **CAPACIDADES_TEMATICAS}

logger.info(f"🎯 Motor Faker inicializado con {len(CAPACIDADES)} tipos de datos disponibles")


# ============================================================================
# PROCESAMIENTO INTELIGENTE DE COLUMNAS
# ============================================================================
def _parsear_lambda_string(expresion: str) -> Callable:
    """
    Convierte un string como "lambda: random.choice(['A', 'B'])" en una función ejecutable.
    Útil si los diccionarios externos vienen como strings.
    """
    import re
    
    expresion = expresion.strip()
    
    # Si ya es un callable, devolverlo
    if callable(expresion):
        return expresion
    
    # Si es string, intentar parsear
    if isinstance(expresion, str):
        # Detectar patrones comunes
        if 'random.choice' in expresion:
            # Extraer la lista de opciones
            import ast
            match = re.search(r"random\.choice\(\[(.*?)\]\)", expresion)
            if match:
                opciones_str = match.group(1)
                # Parsear las opciones (pueden ser strings o números)
                try:
                    opciones = ast.literal_eval(f"[{opciones_str}]")
                    return lambda: random.choice(opciones)
                except:
                    pass
        
        elif 'random.randint' in expresion:
            match = re.search(r"random\.randint\((\d+),\s*(\d+)\)", expresion)
            if match:
                min_val, max_val = int(match.group(1)), int(match.group(2))
                return lambda: random.randint(min_val, max_val)
        
        elif 'fake.' in expresion:
            # Delegar a Faker si es posible
            attr_name = expresion.split('fake.')[-1].split('(')[0]
            if hasattr(fake, attr_name):
                return getattr(fake, attr_name)
    
    # Fallback: devolver el valor como constante
    return lambda: expresion


def _resolver_funcion(columna: str) -> Callable:
    """
    Intenta adivinar qué función usar si el usuario no escribe el nombre exacto.
    Soporta búsqueda fuzzy y valores estáticos.
    """
    col_limpia = columna.lower().strip()
    
    # 1. Búsqueda exacta en el diccionario fusionado
    if col_limpia in CAPACIDADES:
        valor = CAPACIDADES[col_limpia]
        # Si es string con lambda, parsearlo
        if isinstance(valor, str) and ('lambda' in valor or 'random.' in valor):
            return _parsear_lambda_string(valor)
        return valor if callable(valor) else lambda: valor
    
    # 2. Búsqueda por palabras clave (Fuzzy matching)
    mapeo_fuzzy = {
        'correo': 'email',
        'mail': 'email',
        'tel': 'telefono',
        'cel': 'telefono',
        'fecha': 'fecha',
        'texto': 'texto',
        'desc': 'descripcion',
        'descrip': 'descripcion',
        'nombre': 'nombre',
        'name': 'nombre',
        'edad': 'edad',
        'age': 'edad',
        'dir': 'direccion',
        'address': 'direccion',
        'emp': 'empresa',
        'company': 'empresa',
        'puesto': 'cargo',
        'job': 'cargo'
    }
    
    for clave, mapeo in mapeo_fuzzy.items():
        if clave in col_limpia:
            logger.debug(f"   Fuzzy match: '{columna}' -> '{mapeo}'")
            return _resolver_funcion(mapeo)
    
    # 3. Fallback: Si Nahual no sabe qué es, escupe una palabra random
    logger.warning(f"⚠️ Nahual no reconoce la columna '{columna}'. Asignando texto aleatorio.")
    return fake.word


# ============================================================================
# GENERADOR PRINCIPAL
# ============================================================================
def generar_con_faker(volumen: int, columnas: List[str]) -> Dict[str, List[Any]]:
    """
    Ejecuta la generación masiva de datos usando List Comprehensions para máxima velocidad.
    
    Args:
        volumen: Número de registros a generar
        columnas: Lista de nombres de columnas
        
    Returns:
        Diccionario orientado a columnas: {'nombre': ['A', 'B'], 'edad': [20, 21]}
    """
    logger.info(f"⚙️ [MOTOR FAKER] Generando {volumen:,} registros × {len(columnas)} columnas...")
    
    dataset = {}
    
    # Pre-calculamos las funciones ANTES del bucle para optimizar
    funciones_mapeadas = {}
    for col in columnas:
        try:
            funciones_mapeadas[col] = _resolver_funcion(col)
        except Exception as e:
            logger.error(f"   ❌ Error resolviendo columna '{col}': {e}")
            funciones_mapeadas[col] = lambda: f"ERROR_{col}"
    
    # Generación por columnas (más eficiente para pandas)
    for col in columnas:
        func = funciones_mapeadas[col]
        logger.debug(f"   Generando {volumen:,} valores para: {col}")
        
        try:
            # List comprehension optimizada
            dataset[col] = [func() for _ in range(volumen)]
        except Exception as e:
            logger.error(f"❌ Error generando datos para '{col}': {e}")
            dataset[col] = [f"ERROR_{col}"] * volumen
    
    # Verificar consistencia
    if dataset and columnas:
        filas_generadas = len(dataset[columnas[0]])
        logger.info(f"✅ [MOTOR FAKER] Generación completada: {filas_generadas:,} registros × {len(columnas)} campos")
    else:
        logger.warning("⚠️ [MOTOR FAKER] No se generaron datos")
    
    return dataset


# ============================================================================
# GENERACIÓN POR FILAS (ALTERNATIVA para datos correlacionados)
# ============================================================================
def generar_con_faker_por_filas(volumen: int, columnas: List[str]) -> List[Dict[str, Any]]:
    """
    Genera datos registro por registro (útil si necesitas correlaciones entre campos).
    Más lento que la versión por columnas, pero permite lógica interdependiente.
    
    Example:
        Si necesitas que 'fecha_inicio' < 'fecha_fin'
    """
    logger.info(f"⚙️ [MOTOR FAKER - FILAS] Generando {volumen:,} registros...")
    
    funciones = {col: _resolver_funcion(col) for col in columnas}
    dataset = []
    
    for i in range(volumen):
        if i % 10000 == 0 and i > 0:
            logger.debug(f"   Progreso: {i:,}/{volumen:,} registros")
        
        registro = {col: func() for col, func in funciones.items()}
        dataset.append(registro)
    
    logger.info(f"✅ [MOTOR FAKER] Generación completada: {len(dataset):,} registros")
    return dataset


# ============================================================================
# PRUEBA RÁPIDA DEL MOTOR
# ============================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    print("\n" + "🧪"*20)
    print("   Probando Motor Faker Nahual v2.0")
    print("🧪"*20)
    
    # Prueba 1: Capacidades base
    print("\n📋 [PRUEBA 1] Columnas básicas:")
    columnas_base = ['nombre', 'email', 'edad', 'ciudad', 'rfc']
    datos_base = generar_con_faker(3, columnas_base)
    
    for col, valores in datos_base.items():
        print(f"   👉 {col}: {valores}")
    
    # Prueba 2: Ver cuántas capacidades hay
    print(f"\n📊 [INFO] Total capacidades cargadas: {len(CAPACIDADES)}")
    
    # Mostrar algunas temáticas si se cargaron
    if CAPACIDADES_TEMATICAS:
        print(f"\n🎨 [INFO] Diccionario temático cargado con {len(CAPACIDADES_TEMATICAS)} items")
        print("   Ejemplos de temáticas:")
        for i, (key, value) in enumerate(list(CAPACIDADES_TEMATICAS.items())[:5]):
            print(f"      - {key}: {type(value).__name__}")
    
    # Prueba 3: Probar columna inventada (debe fallback a fake.word)
    print("\n🔧 [PRUEBA 2] Columna inventada (fallback):")
    datos_fallback = generar_con_faker(2, ['columna_que_no_existe'])
    print(f"   👉 columna_que_no_existe: {datos_fallback['columna_que_no_existe']}")
    
    print("\n✅ Motor Faker funcionando correctamente!")