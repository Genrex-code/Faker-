"""
NAHUAL - Input Manager (inputs/input_manager.py)
Responsabilidad: Gestionar TODAS las fuentes de entrada de configuración.

Soporta:
- Modo interactivo (usuario)
- Archivos YAML
- Archivos JSON  
- Archivos TXT (columnas por línea)
- Configuración por código (dict)
"""

import json
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ConfiguracionGeneracion:
    """Estructura estandarizada de configuración para el pipeline"""
    volumen: int = 1000
    columnas: List[str] = field(default_factory=lambda: ['nombre', 'email']) # chingaderia anti tronar activa fiummm 
    formato: str = 'excel'
    motor: str = 'python'  # 'python' o 'rust'
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.columnas is None:
            self.columnas = ['nombre', 'email']
        if self.metadata is None:
            self.metadata = {}
        self.metadata['fuente'] = self.metadata.get('fuente', 'desconocida')
        self.metadata['timestamp'] = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario para el pipeline"""
        return {
            'volumen': self.volumen,
            'columnas': self.columnas,
            'formato': self.formato,
            '_motor': self.motor,
            '_metadata': self.metadata
        }


class InputManager:
    """Gestor unificado de entradas de configuración"""
    
    def __init__(self):
        self.configuracion = None
    
    def cargar_desde_usuario(self) -> ConfiguracionGeneracion:
        """Carga configuración mediante interfaz interactiva"""
        from inputs.user import menu_interactivo
        
        logger.info("👤 Modo interactivo activado")
        config_dict = menu_interactivo()
        
        if not config_dict:
            raise ValueError("Usuario canceló la configuración")
        
        return ConfiguracionGeneracion(
            volumen=config_dict.get('volumen', 1000),
            columnas=config_dict.get('columnas', []),
            formato=config_dict.get('formato', 'excel'),
            motor=config_dict.get('_motor', 'python'),
            metadata={'fuente': 'usuario_interactivo'}
        )
    
    def cargar_desde_json(self, ruta: str) -> ConfiguracionGeneracion:
        """Carga configuración desde archivo JSON"""
        ruta_path = Path(ruta)
        
        if not ruta_path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {ruta}")
        
        with open(ruta_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logger.info(f"📄 Configuración cargada desde JSON: {ruta}")
        
        return ConfiguracionGeneracion(
            volumen=data.get('volumen', 1000),
            columnas=data.get('columnas', []),
            formato=data.get('formato', 'excel'),
            motor=data.get('motor', 'python'),
            metadata={'fuente': f'json:{ruta}', 'archivo_original': str(ruta)}
        )
    
    def cargar_desde_yaml(self, ruta: str) -> ConfiguracionGeneracion:
        """Carga configuración desde archivo YAML"""
        ruta_path = Path(ruta)
        
        if not ruta_path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {ruta}")
        
        with open(ruta_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        logger.info(f"📄 Configuración cargada desde YAML: {ruta}")
        
        return ConfiguracionGeneracion(
            volumen=data.get('volumen', 1000),
            columnas=data.get('columnas', []),
            formato=data.get('formato', 'excel'),
            motor=data.get('motor', 'python'),
            metadata={'fuente': f'yaml:{ruta}', 'archivo_original': str(ruta)}
        )
    
    def cargar_desde_txt(self, ruta: str, volumen: int = 100, formato: str = 'csv') -> ConfiguracionGeneracion:
        """Carga columnas desde archivo TXT (una por línea)"""
        ruta_path = Path(ruta)
        
        if not ruta_path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {ruta}")
        
        with open(ruta_path, 'r', encoding='utf-8') as f:
            columnas = [linea.strip().lower() for linea in f if linea.strip()]
        
        if not columnas:
            raise ValueError("El archivo TXT no contiene columnas válidas")
        
        logger.info(f"📄 Columnas cargadas desde TXT: {ruta} ({len(columnas)} columnas)")
        
        return ConfiguracionGeneracion(
            volumen=volumen,
            columnas=columnas,
            formato=formato,
            motor='python',
            metadata={'fuente': f'txt:{ruta}', 'archivo_original': str(ruta)}
        )
    
    def cargar_desde_dict(self, config_dict: Dict[str, Any]) -> ConfiguracionGeneracion:
        """Carga configuración desde diccionario (útil para pruebas)"""
        logger.info("📦 Configuración cargada desde diccionario")
        
        return ConfiguracionGeneracion(
            volumen=config_dict.get('volumen', 1000),
            columnas=config_dict.get('columnas', []),
            formato=config_dict.get('formato', 'excel'),
            motor=config_dict.get('motor', 'python'),
            metadata={'fuente': 'diccionario', **config_dict.get('metadata', {})}
        )
    
    def cargar_desde_archivo(self, ruta: str) -> ConfiguracionGeneracion:
        """Auto-detecta el tipo de archivo y carga la configuración"""
        ruta_path = Path(ruta)
        
        if not ruta_path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {ruta}")
        
        extension = ruta_path.suffix.lower()
        
        if extension == '.json':
            return self.cargar_desde_json(ruta)
        elif extension in ['.yml', '.yaml']:
            return self.cargar_desde_yaml(ruta)
        elif extension == '.txt':
            # Para TXT necesitamos preguntar volumen y formato
            print(f"\n📄 Archivo TXT detectado: {ruta}")
            print(f"   Columnas a cargar desde el archivo")
            volumen = int(input("   ¿Volumen de registros? (default 100): ") or 100)
            formato = input("   ¿Formato? (excel/csv/json, default csv): ").strip().lower() or 'csv'
            return self.cargar_desde_txt(ruta, volumen, formato)
        else:
            raise ValueError(f"Formato de archivo no soportado: {extension}")
    
    def guardar_configuracion(self, config: ConfiguracionGeneracion, ruta: str, formato: str = 'json'):
        """Guarda la configuración en un archivo para reutilización"""
        ruta_path = Path(ruta)
        ruta_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = asdict(config)
        
        if formato == 'json':
            with open(ruta_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        elif formato in ['yml', 'yaml']:
            with open(ruta_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        else:
            raise ValueError(f"Formato no soportado para guardar: {formato}")
        
        logger.info(f"💾 Configuración guardada en: {ruta}")


# ============================================================================
# FUNCIÓN PRINCIPAL PARA EL MAIN (interfaz simplificada)
# ============================================================================
def obtener_configuracion(modo: str = 'interactivo', fuente: Optional[str] = None) -> Dict[str, Any]:
    """
    Interfaz simplificada para el main.
    
    Args:
        modo: 'interactivo', 'archivo', 'dict'
        fuente: Si modo='archivo', ruta del archivo; si modo='dict', diccionario
    
    Returns:
        Diccionario de configuración listo para el pipeline
    """
    manager = InputManager()
    
    if modo == 'interactivo':
        config = manager.cargar_desde_usuario()
    elif modo == 'archivo':
        if not fuente:
            raise ValueError("Se requiere 'fuente' para modo archivo")
        config = manager.cargar_desde_archivo(fuente)
    elif modo == 'dict':
        if not fuente or not isinstance(fuente, dict):
            raise ValueError("Se requiere diccionario para modo dict")
        config = manager.cargar_desde_dict(fuente)
    else:
        raise ValueError(f"Modo no reconocido: {modo}")
    
    return config.to_dict()


# ============================================================================
# PRUEBA DEL INPUT MANAGER
# ============================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    print("\n" + "🧪"*20)
    print("   Probando Input Manager")
    print("🧪"*20)
    
    manager = InputManager()
    
    # Prueba 1: Desde diccionario
    print("\n📦 Prueba 1: Configuración desde diccionario")
    config_dict = {
        'volumen': 50,
        'columnas': ['nombre', 'email', 'edad'],
        'formato': 'csv',
        'motor': 'python'
    }
    config = manager.cargar_desde_dict(config_dict)
    print(f"   → {config.to_dict()}")
    
    # Prueba 2: Guardar configuración
    print("\n💾 Prueba 2: Guardar configuración a JSON")
    manager.guardar_configuracion(config, "configs/mi_config.json")
    print("   → Configuración guardada en configs/mi_config.json")
    
    # Prueba 3: Cargar desde JSON guardado
    print("\n📂 Prueba 3: Cargar desde JSON")
    config_cargada = manager.cargar_desde_json("configs/mi_config.json")
    print(f"   → Volumen: {config_cargada.volumen}, Columnas: {len(config_cargada.columnas)}")
    
    print("\n✅ Input Manager funcionando correctamente!")