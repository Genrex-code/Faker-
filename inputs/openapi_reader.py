"""
NAHUAL - OpenAPI / Swagger Reader (inputs/openapi_reader.py)
Responsabilidad: Leer especificaciones OpenAPI y generar configuraciones de datos

Soporta:
- OpenAPI 2.0 (Swagger) y 3.0/3.1
- Archivos locales (JSON/YAML) y URLs remotas
- Extracción de schemas, ejemplos y endpoints
- Timeout configurable para inestabilidades de red
- Generación de datos de prueba para stress testing
"""

import json
import yaml
import time
import logging
import requests
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ============================================================================
# ESTRUCTURAS DE DATOS
# ============================================================================

@dataclass
class OpenAPIConfig:
    """Configuración extraída de OpenAPI"""
    volumen: int = 100
    columnas: List[str] = field(default_factory=list)
    formato: str = 'json'
    motor: str = 'python'
    
    # Metadatos específicos
    schemas: Dict[str, Any] = field(default_factory=dict)
    endpoints: List[Dict] = field(default_factory=list)
    base_url: str = ""
    selected_endpoint: Optional[str] = None
    selected_schema: Optional[str] = None
    
    def to_pipeline_config(self) -> Dict[str, Any]:
        """Convierte a formato que entiende el pipeline"""
        return {
            'volumen': self.volumen,
            'columnas': self.columnas,
            'formato': self.formato,
            '_motor': self.motor,
            '_metadata': {
                'fuente': 'openapi',
                'schemas_count': len(self.schemas),
                'endpoints_count': len(self.endpoints),
                'base_url': self.base_url,
                'selected_endpoint': self.selected_endpoint,
                'selected_schema': self.selected_schema
            }
        }


@dataclass
class OpenAPIOptions:
    """Opciones de configuración para el lector"""
    timeout_segundos: int = 30
    retries: int = 3
    wait_between_retries: int = 5
    validate_ssl: bool = True
    extract_examples: bool = True
    generate_test_data: bool = True


# ============================================================================
# LECTOR PRINCIPAL
# ============================================================================

class OpenAPIReader:
    """Lector de especificaciones OpenAPI/Swagger con soporte para stress testing"""
    
    def __init__(self, options: Optional[OpenAPIOptions] = None):
        """
        Inicializa el lector OpenAPI
        
        Args:
            options: Opciones de configuración (timeout, retries, etc.)
        """
        self.options = options or OpenAPIOptions()
        self.spec = None
        self.spec_source = None
        self._endpoints_cache = None
        self._schemas_cache = None
    
    def cargar_configuracion(
        self, 
        fuente: str, 
        es_url: bool = False,
        mostrar_previa: bool = True
    ) -> OpenAPIConfig:
        """
        Carga configuración desde archivo o URL
        
        Args:
            fuente: Ruta del archivo o URL
            es_url: True si es URL, False si es archivo local
            mostrar_previa: Mostrar resumen de lo encontrado
        """
        logger.info(f"📖 Cargando especificación OpenAPI desde: {fuente}")
        
        # Mostrar tiempo de espera configurado
        if es_url:
            logger.info(f"   ⏱️  Timeout configurado: {self.options.timeout_segundos}s")
            logger.info(f"   🔄 Reintentos: {self.options.retries}")
        
        # Cargar la especificación (con reintentos si es URL)
        if es_url:
            self.spec = self._cargar_desde_url_con_reintentos(fuente)
            self.spec_source = 'url'
        else:
            self.spec = self._cargar_desde_archivo(fuente)
            self.spec_source = 'file'
        
        if not self.spec:
            logger.error("❌ No se pudo cargar la especificación")
            return OpenAPIConfig()
        
        # Validar versión de OpenAPI
        self._validar_version()
        
        # Extraer información
        base_url = self._extraer_base_url()
        schemas = self._extraer_schemas()
        endpoints = self._extraer_endpoints()
        
        if mostrar_previa:
            self._mostrar_resumen(base_url, schemas, endpoints)
        
        # Interactuar con usuario para seleccionar
        return self._seleccionar_configuracion(base_url, schemas, endpoints)
    
    def _cargar_desde_archivo(self, ruta: str) -> Optional[Dict]:
        """Carga especificación desde archivo local (JSON/YAML)"""
        try:
            ruta_path = Path(ruta)
            
            if not ruta_path.exists():
                logger.error(f"❌ Archivo no encontrado: {ruta}")
                return None
            
            with open(ruta_path, 'r', encoding='utf-8') as f:
                contenido = f.read()
            
            # Detectar formato por extensión o contenido
            if ruta_path.suffix == '.json':
                return json.loads(contenido)
            elif ruta_path.suffix in ['.yml', '.yaml']:
                return yaml.safe_load(contenido)
            else:
                # Intentar detectar por contenido
                if contenido.strip().startswith('{'):
                    return json.loads(contenido)
                else:
                    return yaml.safe_load(contenido)
                    
        except Exception as e:
            logger.error(f"❌ Error cargando archivo {ruta}: {e}")
            return None
    
    def _cargar_desde_url_con_reintentos(self, url: str) -> Optional[Dict]:
        """Carga especificación desde URL con reintentos y timeout"""
        for intento in range(self.options.retries):
            try:
                logger.info(f"   📡 Intento {intento + 1}/{self.options.retries}...")
                
                response = requests.get(
                    url,
                    timeout=self.options.timeout_segundos,
                    verify=self.options.validate_ssl,
                    headers={
                        'Accept': 'application/json, application/yaml, text/yaml, text/plain',
                        'User-Agent': 'NAHUAL-OpenAPI-Reader/1.0'
                    }
                )
                
                response.raise_for_status()
                
                # Detectar formato por Content-Type o contenido
                content_type = response.headers.get('Content-Type', '')
                contenido = response.text
                
                if 'json' in content_type or contenido.strip().startswith('{'):
                    return response.json()
                else:
                    return yaml.safe_load(contenido)
                
            except requests.Timeout:
                logger.warning(f"   ⚠️ Timeout después de {self.options.timeout_segundos}s")
                if intento < self.options.retries - 1:
                    logger.info(f"   ⏳ Esperando {self.options.wait_between_retries}s antes de reintentar...")
                    time.sleep(self.options.wait_between_retries)
                    
            except requests.RequestException as e:
                logger.warning(f"   ⚠️ Error de conexión: {e}")
                if intento < self.options.retries - 1:
                    time.sleep(self.options.wait_between_retries)
                    
            except Exception as e:
                logger.error(f"❌ Error inesperado: {e}")
                return None
        
        logger.error(f"❌ Fallaron todos los reintentos para: {url}")
        return None
    
    def _validar_version(self):
        """Valida y muestra la versión de OpenAPI"""
        version = None
        
        if 'openapi' in self.spec:
            version = self.spec.get('openapi')
            logger.info(f"📌 OpenAPI v{version} detectado")
        elif 'swagger' in self.spec:
            version = self.spec.get('swagger')
            logger.info(f"📌 Swagger v{version} detectado")
        else:
            logger.warning("⚠️ No se pudo detectar la versión de OpenAPI/Swagger")
    
    def _extraer_base_url(self) -> str:
        """Extrae la URL base de la especificación"""
        # OpenAPI 3.0+
        if 'servers' in self.spec and self.spec['servers']:
            return self.spec['servers'][0].get('url', '')
        
        # Swagger 2.0
        if 'host' in self.spec:
            scheme = self.spec.get('schemes', ['https'])[0]
            base_path = self.spec.get('basePath', '')
            return f"{scheme}://{self.spec['host']}{base_path}"
        
        return ""
    
    def _extraer_schemas(self) -> Dict[str, Any]:
        """Extrae todos los schemas/componentes de la especificación"""
        schemas = {}
        
        # OpenAPI 3.0+ - component schemas
        if 'components' in self.spec and 'schemas' in self.spec['components']:
            schemas.update(self.spec['components']['schemas'])
        
        # Swagger 2.0 - definitions
        if 'definitions' in self.spec:
            schemas.update(self.spec['definitions'])
        
        # También buscar en parámetros y respuestas
        self._schemas_cache = schemas
        return schemas
    
    def _extraer_endpoints(self) -> List[Dict]:
        """Extrae todos los endpoints/paths de la especificación"""
        endpoints = []
        
        paths = self.spec.get('paths', {})
        
        for path, methods in paths.items():
            for method, details in methods.items():
                if method.lower() not in ['get', 'post', 'put', 'delete', 'patch', 'options', 'head']:
                    continue
                
                endpoints.append({
                    'path': path,
                    'method': method.upper(),
                    'summary': details.get('summary', ''),
                    'description': details.get('description', ''),
                    'parameters': details.get('parameters', []),
                    'requestBody': details.get('requestBody', {}),
                    'responses': details.get('responses', {})
                })
        
        self._endpoints_cache = endpoints
        return endpoints
    
    def _mostrar_resumen(self, base_url: str, schemas: Dict, endpoints: List):
        """Muestra un resumen de lo encontrado"""
        print("\n" + "="*60)
        print("📊 RESUMEN DE ESPECIFICACIÓN OPENAPI")
        print("="*60)
        
        if base_url:
            print(f"   🌐 Base URL: {base_url}")
        
        print(f"   📦 Schemas/Modelos: {len(schemas)}")
        print(f"   🔗 Endpoints: {len(endpoints)}")
        
        # Mostrar algunos ejemplos
        if schemas:
            print(f"\n   📋 PRINCIPALES SCHEMAS:")
            for i, (name, schema) in enumerate(list(schemas.items())[:5]):
                props = len(schema.get('properties', {})) if isinstance(schema, dict) else 0
                print(f"      {i+1}. {name} ({props} propiedades)")
            if len(schemas) > 5:
                print(f"      ... y {len(schemas) - 5} más")
        
        if endpoints:
            print(f"\n   🔗 PRINCIPALES ENDPOINTS:")
            for i, ep in enumerate(endpoints[:5]):
                print(f"      {i+1}. {ep['method']} {ep['path']}")
            if len(endpoints) > 5:
                print(f"      ... y {len(endpoints) - 5} más")
        
        print("="*60)
    
    def _seleccionar_configuracion(self, base_url: str, schemas: Dict, endpoints: List) -> OpenAPIConfig:
        """Interactúa con el usuario para seleccionar la configuración"""
        config = OpenAPIConfig(
            base_url=base_url,
            schemas=schemas,
            endpoints=endpoints
        )
        
        print("\n🎯 CONFIGURACIÓN PARA GENERACIÓN")
        print("-" * 40)
        
        # Preguntar si quiere usar un schema existente o definir columnas manualmente
        if schemas:
            print("\n📌 ¿Cómo quieres definir las columnas?")
            print("   1) Usar un schema existente (recomendado)")
            print("   2) Definir columnas manualmente")
            
            opcion = input("\n👉 Elige (1-2, default: 1): ").strip() or '1'
            
            if opcion == '1':
                config = self._seleccionar_schema(config, schemas)
            else:
                config.columnas = self._pedir_columnas_manual()
        else:
            config.columnas = self._pedir_columnas_manual()
        
        # Preguntar por volumen
        config.volumen = self._pedir_volumen()
        
        # Preguntar por formato
        config.formato = self._pedir_formato()
        
        # Preguntar si quiere generar datos de prueba para stress testing
        if self.options.generate_test_data:
            generar_stress = input("\n🔥 ¿Generar datos para STRESS TESTING? (s/n, default: n): ").strip().lower()
            if generar_stress == 's':
                config.motor = 'python'
                config._metadata['stress_test_mode'] = True
                config._metadata['volumen_recomendado'] = min(config.volumen * 10, 1000000)
                logger.info("   ⚡ Modo stress testing activado - se generarán volúmenes mayores")
        
        return config
    
    def _seleccionar_schema(self, config: OpenAPIConfig, schemas: Dict) -> OpenAPIConfig:
        """Permite al usuario seleccionar un schema existente"""
        print("\n📋 SCHEMAS DISPONIBLES:")
        
        schema_list = list(schemas.keys())
        for i, name in enumerate(schema_list, 1):
            schema = schemas[name]
            props = len(schema.get('properties', {})) if isinstance(schema, dict) else 0
            print(f"   {i}. {name} ({props} propiedades)")
        
        while True:
            try:
                seleccion = input(f"\n👉 Selecciona schema (1-{len(schema_list)}): ").strip()
                idx = int(seleccion) - 1
                if 0 <= idx < len(schema_list):
                    schema_name = schema_list[idx]
                    config.selected_schema = schema_name
                    
                    # Extraer propiedades como columnas
                    schema = schemas[schema_name]
                    if isinstance(schema, dict) and 'properties' in schema:
                        config.columnas = list(schema['properties'].keys())
                        logger.info(f"   ✅ Extraídas {len(config.columnas)} columnas del schema '{schema_name}'")
                    else:
                        config.columnas = self._pedir_columnas_manual()
                    
                    # Preguntar si quiere seleccionar un endpoint también
                    if config.endpoints:
                        sel_endpoint = input("\n   ¿Seleccionar un endpoint relacionado? (s/n, default: n): ").strip().lower()
                        if sel_endpoint == 's':
                            config = self._seleccionar_endpoint(config)
                    
                    return config
                else:
                    print(f"❌ Número inválido")
            except ValueError:
                print("❌ Ingresa un número válido")
    
    def _seleccionar_endpoint(self, config: OpenAPIConfig) -> OpenAPIConfig:
        """Permite al usuario seleccionar un endpoint"""
        print("\n🔗 ENDPOINTS DISPONIBLES:")
        
        for i, ep in enumerate(config.endpoints, 1):
            print(f"   {i}. {ep['method']} {ep['path']}")
            if ep['summary']:
                print(f"      └─ {ep['summary'][:60]}")
        
        while True:
            try:
                seleccion = input(f"\n👉 Selecciona endpoint (1-{len(config.endpoints)}): ").strip()
                idx = int(seleccion) - 1
                if 0 <= idx < len(config.endpoints):
                    config.selected_endpoint = config.endpoints[idx]['path']
                    logger.info(f"   ✅ Endpoint seleccionado: {config.endpoints[idx]['method']} {config.selected_endpoint}")
                    return config
                else:
                    print(f"❌ Número inválido")
            except ValueError:
                print("❌ Ingresa un número válido")
    
    def _pedir_columnas_manual(self) -> List[str]:
        """Pide columnas manualmente al usuario"""
        print("\n✏️  DEFINICIÓN MANUAL DE COLUMNAS")
        print("   💡 Ejemplo: nombre, email, edad, ciudad")
        
        while True:
            col_input = input("   Columnas: ").strip()
            if col_input:
                columnas = [c.strip().lower() for c in col_input.split(',') if c.strip()]
                if columnas:
                    return columnas
            print("   ❌ Debes especificar al menos una columna")
    
    def _pedir_volumen(self) -> int:
        """Pide el volumen de datos"""
        print("\n📊 VOLUMEN DE DATOS")
        
        while True:
            try:
                volumen = input("   ¿Cuántos registros generar? (default: 100): ").strip()
                if not volumen:
                    return 100
                volumen_int = int(volumen)
                if volumen_int > 0:
                    return volumen_int
                print("   ❌ El volumen debe ser mayor a 0")
            except ValueError:
                print("   ❌ Ingresa un número válido")
    
    def _pedir_formato(self) -> str:
        """Pide el formato de salida"""
        print("\n💾 FORMATO DE SALIDA")
        print("   1) JSON (recomendado para APIs)")
        print("   2) Excel (.xlsx)")
        print("   3) CSV (.csv)")
        
        while True:
            opcion = input("\n👉 Elige (1-3, default: 1): ").strip() or '1'
            if opcion == '1':
                return 'json'
            elif opcion == '2':
                return 'excel'
            elif opcion == '3':
                return 'csv'
            print("❌ Opción inválida")
    
    def generar_request_body(self, schema_name: str) -> Dict:
        """
        Genera un body de request de ejemplo basado en un schema
        
        Útil para pruebas de estrés de APIs
        """
        if schema_name not in self._schemas_cache:
            logger.warning(f"⚠️ Schema '{schema_name}' no encontrado")
            return {}
        
        schema = self._schemas_cache[schema_name]
        return self._generar_desde_schema(schema)
    
    def _generar_desde_schema(self, schema: Dict) -> Dict:
        """Recursivamente genera datos desde un schema JSON"""
        # Por ahora implementación básica
        result = {}
        
        if 'properties' in schema:
            for prop_name, prop_schema in schema['properties'].items():
                prop_type = prop_schema.get('type', 'string')
                
                if 'example' in prop_schema:
                    result[prop_name] = prop_schema['example']
                elif 'enum' in prop_schema:
                    import random
                    result[prop_name] = random.choice(prop_schema['enum'])
                elif prop_type == 'string':
                    result[prop_name] = f"test_{prop_name}"
                elif prop_type == 'integer':
                    result[prop_name] = 0
                elif prop_type == 'boolean':
                    result[prop_name] = False
                else:
                    result[prop_name] = None
        
        return result


# ============================================================================
# FUNCIÓN PRINCIPAL PARA INPUT_MANAGER
# ============================================================================

def obtener_configuracion_openapi(
    fuente: Optional[str] = None,
    es_url: bool = False,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Interfaz para integrar con input_manager.py
    
    Args:
        fuente: Ruta del archivo o URL (si es None, pide interactivamente)
        es_url: True si es URL, False si es archivo
        timeout: Timeout en segundos para conexiones
    
    Returns:
        Diccionario de configuración listo para el pipeline
    """
    options = OpenAPIOptions(timeout_segundos=timeout)
    reader = OpenAPIReader(options)
    
    # Si no hay fuente, preguntar interactivamente
    if not fuente:
        print("\n" + "="*60)
        print("📖 LECTOR DE ESPECIFICACIONES OPENAPI/SWAGGER")
        print("="*60)
        print("\n¿Cómo quieres cargar la especificación?")
        print("   1) Desde archivo local (JSON/YAML)")
        print("   2) Desde URL remota")
        
        opcion = input("\n👉 Elige (1-2): ").strip()
        
        if opcion == '1':
            fuente = input("📁 Ruta del archivo: ").strip()
            es_url = False
        else:
            fuente = input("🌐 URL de la especificación: ").strip()
            es_url = True
    
    config_obj = reader.cargar_configuracion(fuente, es_url)
    return config_obj.to_pipeline_config()


# ============================================================================
# PRUEBA DEL MÓDULO
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    print("\n" + "🧪"*20)
    print("   Probando OpenAPI Reader")
    print("🧪"*20)
    
    # Prueba con archivo de ejemplo (crea uno si no existe)
    ejemplo = {
        "openapi": "3.0.0",
        "info": {"title": "API de Prueba", "version": "1.0.0"},
        "servers": [{"url": "https://api.ejemplo.com/v1"}],
        "paths": {
            "/usuarios": {
                "get": {"summary": "Obtener usuarios"},
                "post": {"summary": "Crear usuario"}
            }
        },
        "components": {
            "schemas": {
                "Usuario": {
                    "properties": {
                        "nombre": {"type": "string"},
                        "email": {"type": "string"},
                        "edad": {"type": "integer"}
                    }
                }
            }
        }
    }
    
    # Guardar ejemplo
    import json
    Path("configs").mkdir(exist_ok=True)
    with open("configs/openapi_ejemplo.json", "w") as f:
        json.dump(ejemplo, f, indent=2)
    
    print("\n📌 Prueba con archivo de ejemplo")
    config = obtener_configuracion_openapi("configs/openapi_ejemplo.json", es_url=False)
    print(f"\n✅ Configuración obtenida: {config}")