"""
NAHUAL - SQL Reader (inputs/sql_reader.py)
Responsabilidad: Leer configuración desde una base de datos SQL y convertirla al formato del pipeline.

Soporta:
- Conexión a múltiples motores (PostgreSQL, MySQL, SQL Server, SQLite)
- Lectura de esquema y columnas desde metadatos
- Modo interactivo para credenciales
- Conexiones seguras con variables de entorno
- Validación de esquemas y tipos
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================================
# ESTRUCTURA DE CONFIGURACIÓN SQL
# ============================================================================

@dataclass
class SQLConnectionConfig:
    """Configuración de conexión a base de datos SQL"""
    db_type: str  # 'postgresql', 'mysql', 'sqlserver', 'sqlite'
    host: Optional[str] = None
    port: Optional[int] = None
    database: str = ""
    username: Optional[str] = None
    password: Optional[str] = None
    sqlite_path: Optional[str] = None
    
    # Opciones adicionales
    schema: str = "public"
    table: str = ""
    query: Optional[str] = None
    
    # Seguridad
    use_env_vars: bool = True
    ssl_mode: str = "prefer"  # 'disable', 'require', 'prefer'
    
    def get_connection_string(self) -> str:
        """Genera el string de conexión según el motor"""
        if self.db_type == 'postgresql':
            return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        
        elif self.db_type == 'mysql':
            return f"mysql+pymysql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        
        elif self.db_type == 'sqlserver':
            return f"mssql+pyodbc://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}?driver=ODBC+Driver+17+for+SQL+Server"
        
        elif self.db_type == 'sqlite':
            if not self.sqlite_path:
                self.sqlite_path = "nahual_data.db"
            return f"sqlite:///{self.sqlite_path}"
        
        else:
            raise ValueError(f"Motor de base de datos no soportado: {self.db_type}")


@dataclass
class SQLReaderConfig:
    """Configuración completa que retorna el SQL Reader"""
    volumen: int = 1000
    columnas: List[str] = field(default_factory=list)
    formato: str = 'excel'
    motor: str = 'python'
    
    # Metadatos específicos de SQL
    sql_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_pipeline_config(self) -> Dict[str, Any]:
        """Convierte a formato que entiende el pipeline"""
        return {
            'volumen': self.volumen,
            'columnas': self.columnas,
            'formato': self.formato,
            '_motor': self.motor,
            '_metadata': {
                'fuente': 'sql',
                **self.sql_metadata
            }
        }


# ============================================================================
# LECTOR SQL PRINCIPAL
# ============================================================================

class SQLReader:
    """Lector de configuración desde bases de datos SQL"""
    
    # Motores soportados
    SUPPORTED_ENGINES = ['postgresql', 'mysql', 'sqlserver', 'sqlite']
    
    # Puertos por defecto
    DEFAULT_PORTS = {
        'postgresql': 5432,
        'mysql': 3306,
        'sqlserver': 1433,
        'sqlite': None
    }
    
    def __init__(self, use_env_vars: bool = True):
        """
        Inicializa el lector SQL
        
        Args:
            use_env_vars: Si debe buscar credenciales en variables de entorno
        """
        self.use_env_vars = use_env_vars
        self.connection = None
        self.engine = None
    
    def leer_configuracion(self, archivo_config: Optional[str] = None) -> SQLReaderConfig:
        """
        Lee configuración SQL desde archivo o interactivamente
        
        Args:
            archivo_config: Ruta a archivo de configuración JSON/YAML (opcional)
        """
        if archivo_config and Path(archivo_config).exists():
            return self._leer_desde_archivo(archivo_config)
        else:
            return self._leer_interactivo()
    
    def _leer_desde_archivo(self, archivo_config: str) -> SQLReaderConfig:
        """Lee configuración desde archivo JSON/YAML"""
        import json
        import yaml
        
        ruta = Path(archivo_config)
        
        if ruta.suffix == '.json':
            with open(ruta, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            with open(ruta, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        
        logger.info(f"📄 Configuración SQL cargada desde: {archivo_config}")
        
        # Extraer config de conexión
        db_config = data.get('database', {})
        query_config = data.get('query', {})
        
        # Crear objeto de conexión
        conn_config = SQLConnectionConfig(
            db_type=db_config.get('type', 'postgresql'),
            host=db_config.get('host'),
            port=db_config.get('port'),
            database=db_config.get('database', ''),
            username=db_config.get('username'),
            password=db_config.get('password'),
            sqlite_path=db_config.get('sqlite_path'),
            schema=db_config.get('schema', 'public'),
            table=query_config.get('table', ''),
            query=query_config.get('sql'),
            use_env_vars=db_config.get('use_env_vars', True),
            ssl_mode=db_config.get('ssl_mode', 'prefer')
        )
        
        # Conectar y obtener columnas si no están definidas
        columnas = data.get('columnas', [])
        
        if not columnas and conn_config.table:
            columnas = self._obtener_columnas_desde_tabla(conn_config)
        
        return SQLReaderConfig(
            volumen=data.get('volumen', 1000),
            columnas=columnas,
            formato=data.get('formato', 'excel'),
            motor=data.get('motor', 'python'),
            sql_metadata={
                'connection_type': conn_config.db_type,
                'database': conn_config.database,
                'table': conn_config.table,
                'query_provided': bool(conn_config.query),
                'columns_from_schema': len(columnas) > 0
            }
        )
    
    def _leer_interactivo(self) -> SQLReaderConfig:
        """Lee configuración mediante entrada interactiva del usuario"""
        print("\n" + "="*60)
        print("🗄️  CONFIGURACIÓN DESDE BASE DE DATOS SQL")
        print("="*60)
        
        # 1. Seleccionar motor
        print("\n📌 MOTORES SOPORTADOS:")
        for i, engine in enumerate(self.SUPPORTED_ENGINES, 1):
            print(f"   {i}) {engine.upper()}")
        
        while True:
            opcion = input("\n👉 Elige motor (1-4): ").strip()
            if opcion in ['1', '2', '3', '4']:
                db_type = self.SUPPORTED_ENGINES[int(opcion) - 1]
                break
            print("❌ Opción inválida")
        
        # 2. Configurar conexión
        conn_config = self._configurar_conexion_interactiva(db_type)
        
        # 3. Seleccionar tabla o query
        use_table = self._seleccionar_tabla_o_query(conn_config)
        
        # 4. Obtener columnas
        columnas = self._seleccionar_columnas(conn_config)
        
        # 5. Configurar volumen
        volumen = self._configurar_volumen()
        
        # 6. Configurar formato
        formato = self._configurar_formato()
        
        print("\n✅ Configuración SQL completada")
        
        return SQLReaderConfig(
            volumen=volumen,
            columnas=columnas,
            formato=formato,
            motor='python',
            sql_metadata={
                'connection_type': db_type,
                'database': conn_config.database,
                'table': conn_config.table if use_table == 'table' else None,
                'query_provided': use_table == 'query'
            }
        )
    
    def _configurar_conexion_interactiva(self, db_type: str) -> SQLConnectionConfig:
        """Configuración interactiva de conexión"""
        print(f"\n🔌 CONFIGURACIÓN {db_type.upper()}")
        
        # Intentar obtener credenciales de variables de entorno
        username = None
        password = None
        host = None
        port = self.DEFAULT_PORTS.get(db_type)
        database = None
        
        if self.use_env_vars:
            env_prefix = db_type.upper()
            username = os.getenv(f"{env_prefix}_USER") or os.getenv(f"{env_prefix}_USERNAME")
            password = os.getenv(f"{env_prefix}_PASSWORD")
            host = os.getenv(f"{env_prefix}_HOST")
            #correcion al bug de puerto que no se convertía a int
            env_port = os.getenv(f"{env_prefix}_PORT")
            port = int(env_port) if env_port else port
            #fin de la correcion
            database = os.getenv(f"{env_prefix}_DATABASE")
        
        # SQLite es especial
        if db_type == 'sqlite':
            default_path = "nahual_data.db"
            sqlite_path = input(f"   Ruta del archivo SQLite (default: {default_path}): ").strip()
            if not sqlite_path:
                sqlite_path = default_path
            
            return SQLConnectionConfig(
                db_type=db_type,
                sqlite_path=sqlite_path,
                database=Path(sqlite_path).stem,
                use_env_vars=self.use_env_vars
            )
        
        # Para otros motores
        print("\n   📡 DATOS DE CONEXIÓN:")
        
        host = input(f"   Host (default: {host or 'localhost'}): ").strip() or host or 'localhost'
        
        port_str = input(f"   Puerto (default: {port}): ").strip()
        if port_str:
            port = int(port_str)
        
        database = input(f"   Base de datos: ").strip()
        while not database:
            print("   ❌ La base de datos es obligatoria")
            database = input(f"   Base de datos: ").strip()
        
        usar_env = input(f"   ¿Usar credenciales de entorno? (s/n, default: s): ").strip().lower()
        if usar_env == 'n':
            username = input("   Usuario: ").strip()
            password = input("   Contraseña: ").strip()
            use_env = False
        else:
            if not username:
                username = input("   Usuario (o variable de entorno): ").strip()
            if not password:
                password = input("   Contraseña (o variable de entorno): ").strip()
            use_env = True
        
        return SQLConnectionConfig(
            db_type=db_type,
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            use_env_vars=use_env,
            ssl_mode=input("   SSL Mode (disable/require/prefer, default: prefer): ").strip() or 'prefer'
        )
    
    def _seleccionar_tabla_o_query(self, conn_config: SQLConnectionConfig) -> str:
        """Selecciona si usar tabla o query personalizada"""
        print("\n📋 FUENTE DE DATOS:")
        print("   1) Usar una tabla existente")
        print("   2) Usar query SQL personalizada")
        
        while True:
            opcion = input("\n👉 Elige (1-2): ").strip()
            if opcion == '1':
                self._listar_tablas(conn_config)
                tabla = input("\n   Nombre de la tabla: ").strip()
                if tabla:
                    conn_config.table = tabla
                return 'table'
            elif opcion == '2':
                print("\n   ✏️  Escribe tu query SQL (termina con punto y coma ';' en línea nueva):")
                lines = []
                while True:
                    line = input()
                    if line.strip().endswith(';'):
                        lines.append(line.rstrip(';'))
                        break
                    lines.append(line)
                conn_config.query = ' '.join(lines).strip()
                return 'query'
            print("❌ Opción inválida")
    
    def _listar_tablas(self, conn_config: SQLConnectionConfig):
        """Lista las tablas disponibles en la base de datos"""
        try:
            import sqlalchemy as sa
            
            engine = sa.create_engine(conn_config.get_connection_string())
            inspector = sa.inspect(engine)
            tablas = inspector.get_table_names(schema=conn_config.schema)
            
            print(f"\n   📋 TABLAS DISPONIBLES ({len(tablas)}):")
            for i, tabla in enumerate(tablas[:20], 1):
                print(f"      {i}. {tabla}")
            if len(tablas) > 20:
                print(f"      ... y {len(tablas) - 20} más")
            
            engine.dispose()
            
        except Exception as e:
            logger.warning(f"⚠️ No se pudieron listar tablas: {e}")
            print("   💡 Ingresa el nombre de la tabla manualmente")
    
    def _obtener_columnas_desde_tabla(self, conn_config: SQLConnectionConfig) -> List[str]:
        """Obtiene las columnas de una tabla existente"""
        try:
            import sqlalchemy as sa
            
            engine = sa.create_engine(conn_config.get_connection_string())
            
            if conn_config.table:
                # Usar reflection para obtener columnas
                metadata = sa.MetaData()
                table = sa.Table(conn_config.table, metadata, autoload_with=engine, schema=conn_config.schema)
                columnas = [col.name for col in table.columns]
                logger.info(f"📋 Columnas detectadas desde tabla '{conn_config.table}': {len(columnas)} campos")
                engine.dispose()
                return columnas
            
        except Exception as e:
            logger.warning(f"⚠️ No se pudieron obtener columnas automáticamente: {e}")
        
        return []
    
    def _seleccionar_columnas(self, conn_config: SQLConnectionConfig) -> List[str]:
        """Selecciona qué columnas usar"""
        # Intentar obtener columnas automáticamente
        columnas_automaticas = self._obtener_columnas_desde_tabla(conn_config)
        
        if columnas_automaticas:
            print(f"\n📊 COLUMNAS DETECTADAS ({len(columnas_automaticas)}):")
            print(f"   {', '.join(columnas_automaticas[:15])}")
            if len(columnas_automaticas) > 15:
                print(f"   ... y {len(columnas_automaticas) - 15} más")
            
            usar_todas = input("\n   ¿Usar todas las columnas? (s/n, default: s): ").strip().lower()
            if usar_todas != 'n':
                return columnas_automaticas
        
        # Entrada manual de columnas
        print("\n   ✏️  Ingresa las columnas separadas por coma")
        print("   💡 Ejemplo: nombre, email, edad, ciudad")
        
        while True:
            col_input = input("   Columnas: ").strip()
            if col_input:
                columnas = [c.strip().lower() for c in col_input.split(',') if c.strip()]
                if columnas:
                    return columnas
            print("   ❌ Debes especificar al menos una columna")
    
    def _configurar_volumen(self) -> int:
        """Configura el número de registros a generar"""
        print("\n📊 CONFIGURACIÓN DE VOLUMEN")
        
        while True:
            try:
                volumen = input("   ¿Cuántos registros generar? (default: 1000): ").strip()
                if not volumen:
                    return 1000
                volumen_int = int(volumen)
                if volumen_int > 0:
                    return volumen_int
                print("   ❌ El volumen debe ser mayor a 0")
            except ValueError:
                print("   ❌ Ingresa un número válido")
    
    def _configurar_formato(self) -> str:
        """Configura el formato de salida"""
        print("\n💾 FORMATO DE SALIDA")
        print("   1) Excel (.xlsx)")
        print("   2) CSV (.csv)")
        print("   3) JSON (.json)")
        
        while True:
            opcion = input("\n👉 Elige (1-3, default: 1): ").strip()
            if not opcion or opcion == '1':
                return 'excel'
            elif opcion == '2':
                return 'csv'
            elif opcion == '3':
                return 'json'
            print("❌ Opción inválida")
    
    def test_conexion(self, config: SQLConnectionConfig) -> bool:
        """Prueba la conexión a la base de datos"""
        try:
            import sqlalchemy as sa
            
            engine = sa.create_engine(config.get_connection_string())
            with engine.connect() as conn:
                result = conn.execute(sa.text("SELECT 1"))
                result.fetchone()
            
            logger.info(f"✅ Conexión exitosa a {config.db_type}/{config.database}")
            engine.dispose()
            return True
            
        except ImportError:
            logger.error("❌ SQLAlchemy no está instalado. Ejecuta: pip install sqlalchemy pymysql psycopg2-binary pyodbc")
            return False
        except Exception as e:
            logger.error(f"❌ Error de conexión: {e}")
            return False


# ============================================================================
# FUNCIÓN PRINCIPAL PARA INTEGRAR CON INPUT_MANAGER
# ============================================================================

def obtener_configuracion_sql(archivo_config: Optional[str] = None) -> Dict[str, Any]:
    """
    Interfaz para integrar con input_manager.py
    
    Args:
        archivo_config: Ruta opcional a archivo de configuración
    
    Returns:
        Diccionario de configuración listo para el pipeline
    """
    reader = SQLReader(use_env_vars=True)
    
    # Probar dependencias primero
    try:
        import sqlalchemy
    except ImportError:
        logger.error("❌ SQLAlchemy no instalado")
        logger.info("   Instala: pip install sqlalchemy pymysql psycopg2-binary")
        return {}
    
    config_obj = reader.leer_configuracion(archivo_config)
    
    # Probar conexión si es necesario
    if archivo_config:
        # Si viene de archivo, podríamos probar la conexión
        pass
    
    return config_obj.to_pipeline_config()


# ============================================================================
# GUARDAR CONFIGURACIÓN PARA REUTILIZAR
# ============================================================================

def guardar_configuracion_sql(config: Dict[str, Any], ruta: str):
    """Guarda la configuración SQL en un archivo para reutilizar"""
    import json
    
    output = {
        'volumen': config.get('volumen', 1000),
        'columnas': config.get('columnas', []),
        'formato': config.get('formato', 'excel'),
        'motor': config.get('_motor', 'python'),
        'database': config.get('_metadata', {}).get('sql_metadata', {})
    }
    
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    logger.info(f"💾 Configuración SQL guardada en: {ruta}")


# ============================================================================
# PRUEBA DEL MÓDULO
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    print("\n" + "🧪"*20)
    print("   Probando SQL Reader")
    print("🧪"*20)
    
    # Probar modo interactivo
    reader = SQLReader(use_env_vars=True)
    
    print("\n📌 PRUEBA 1: Configuración interactiva")
    print("   (responde las preguntas o escribe 'test' para saltar)")
    
    try:
        config = reader.leer_configuracion()
        print("\n✅ Configuración obtenida:")
        print(f"   Volumen: {config.volumen}")
        print(f"   Columnas: {config.columnas[:5]}...")
        print(f"   Formato: {config.formato}")
    except KeyboardInterrupt:
        print("\n   Prueba cancelada")
    
    # Mostrar ejemplo de archivo de configuración
    print("\n📌 EJEMPLO de archivo de configuración SQL (configs/sql_config.json):")
    ejemplo = {
        "volumen": 1000,
        "formato": "excel",
        "motor": "python",
        "database": {
            "type": "postgresql",
            "host": "localhost",
            "port": 5432,
            "database": "mi_db",
            "schema": "public",
            "use_env_vars": True
        },
        "query": {
            "table": "usuarios"
        },
        "columnas": ["nombre", "email", "edad"]
    }
    
    import json
    print(json.dumps(ejemplo, indent=2))