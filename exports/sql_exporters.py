"""
NAHUAL - SQL Exporter (exports/sql_exporters.py)
Responsabilidad: Tomar los datos sintéticos generados en la RAM y exportarlos 
ya sea a un archivo físico .sql o inyectarlos directo en una base de datos viva.

Soporta:
- Generación de scripts SQL (INSERTs)
- Inyección directa a bases de datos (PostgreSQL, MySQL, SQL Server, SQLite)
- Múltiples modos: solo script, solo inyección, o ambos
- Manejo seguro de credenciales
- Bulk insert optimizado
"""

import logging
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
import pandas as pd

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTES
# ============================================================================

# Tamaño por defecto para bulk inserts
DEFAULT_CHUNK_SIZE = 10000

# Motores SQL soportados
SUPPORTED_ENGINES = ['postgresql', 'mysql', 'sqlserver', 'sqlite']

# Dialectos de SQLAlchemy
SQLALCHEMY_DIALECTS = {
    'postgresql': 'postgresql+psycopg2',
    'mysql': 'mysql+pymysql',
    'sqlserver': 'mssql+pyodbc',
    'sqlite': 'sqlite'
}


# ============================================================================
# EXPORTADOR PRINCIPAL
# ============================================================================

def exportar_sql(
    dataset: Dict[str, List[Any]], 
    volumen: int, 
    ruta: Optional[str] = None, 
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Punto de entrada para la exportación SQL.
    Decide si genera un archivo script, si inyecta en vivo, o ambos.
    
    Args:
        dataset: Diccionario con los datos generados
        volumen: Número de registros
        ruta: Ruta de destino para el archivo .sql (opcional)
        metadata: Configuración con credenciales y opciones
    
    Returns:
        True si la operación fue exitosa, False en caso contrario
    """
    logger.info(f"🗄️ [SQL EXPORTER] Iniciando exportación SQL...")
    
    if not dataset or len(dataset) == 0:
        logger.error("❌ Dataset vacío")
        return False
    
    try:
        df = pd.DataFrame(dataset)
        
        # Extraer parámetros de configuración
        meta_segura = metadata if metadata is not None else {}
        nombre_tabla = meta_segura.get('table', 'nahual_datos')
        modo = meta_segura.get('mode', 'both')  # 'script', 'live', 'both'
        db_config = meta_segura.get('db_connection', None)
        chunk_size = meta_segura.get('chunk_size', DEFAULT_CHUNK_SIZE)
        if_exists = meta_segura.get('if_exists', 'append')  # 'fail', 'replace', 'append'
        
        resultados = {'script': False, 'live': False}
        
        # 1. Generar archivo script SQL
        if modo in ['script', 'both']:
            resultados['script'] = _generar_archivo_script_sql(df, nombre_tabla, ruta)
        
        # 2. Inyección directa a base de datos
        if modo in ['live', 'both'] and db_config:
            resultados['live'] = _inyectar_base_de_datos_viva(
                df, nombre_tabla, db_config, if_exists, chunk_size
            )
        elif modo in ['live', 'both'] and not db_config:
            logger.warning("⚠️ Modo 'live' seleccionado pero no hay configuración de base de datos")
        
        # Resumen final
        if modo == 'script':
            success = resultados['script']
        elif modo == 'live':
            success = resultados['live']
        else:
            success = resultados['script'] and resultados['live']
        
        if success:
            logger.info("✅ [SQL EXPORTER] Exportación SQL completada")
        else:
            logger.warning("⚠️ [SQL EXPORTER] Exportación parcial o fallida")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Error crítico en exportador SQL: {e}", exc_info=True)
        return False


# ============================================================================
# GENERADOR DE SCRIPT SQL
# ============================================================================

def _generar_archivo_script_sql(
    df: pd.DataFrame, 
    nombre_tabla: str, 
    ruta_archivo: Optional[str] = None,
    dialecto: str = 'mysql'  # 'mysql', 'postgresql', 'sqlserver'
) -> bool:
    """
    Genera un archivo .sql con comandos INSERT
    
    Args:
        df: DataFrame con los datos
        nombre_tabla: Nombre de la tabla destino
        ruta_archivo: Ruta donde guardar (opcional)
        dialecto: Dialecto SQL para usar (diferentes delimitadores)
    """
    try:
        # Crear ruta por defecto si no se proporcionó
        if not ruta_archivo:
            output_dir = Path("outputs")
            output_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ruta_archivo = str(output_dir / f"nahual_inserciones_{timestamp}.sql")
        
        logger.info(f"💾 Generando script SQL en: {ruta_archivo}")
        
        # Obtener delimitadores según dialecto
        if dialecto == 'mysql':
            quote_char = '`'
        elif dialecto == 'postgresql':
            quote_char = '"'
        else:
            quote_char = ''
        
        columnas = ", ".join([f"{quote_char}{col}{quote_char}" for col in df.columns])
        
        with open(ruta_archivo, 'w', encoding='utf-8') as f:
            # Cabecera
            f.write(f"-- ============================================\n")
            f.write(f"-- NAHUAL SHADOW DATA GENERATOR\n")
            f.write(f"-- ============================================\n")
            f.write(f"-- Tabla: {nombre_tabla}\n")
            f.write(f"-- Registros: {len(df):,}\n")
            f.write(f"-- Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"-- Dialecto: {dialecto.upper()}\n")
            f.write(f"-- ============================================\n\n")
            
            # Opcional: CREATE TABLE si no existe
            f.write(f"-- CREATE TABLE IF NOT EXISTS {quote_char}{nombre_tabla}{quote_char} (\n")
            for i, col in enumerate(df.columns):
                tipo = _inferir_tipo_sql(df[col])
                f.write(f"    {quote_char}{col}{quote_char} {tipo}")
                if i < len(df.columns) - 1:
                    f.write(",")
                f.write("\n")
            f.write(f");\n\n")
            
            # INSERTs
            f.write(f"-- INSERTANDO {len(df):,} REGISTROS\n")
            f.write(f"INSERT INTO {quote_char}{nombre_tabla}{quote_char} ({columnas}) VALUES\n")
            
            total_filas = len(df)
            batch_size = 500  # Para evitar líneas extremadamente largas
            
            for batch_start in range(0, total_filas, batch_size):
                batch_end = min(batch_start + batch_size, total_filas)
                batch_df = df.iloc[batch_start:batch_end]
                
                for idx, row in batch_df.iterrows():
                    valores_formateados = []
                    for val in row:
                        if pd.isna(val) or val is None:
                            valores_formateados.append("NULL")
                        elif isinstance(val, bool):
                            valores_formateados.append("TRUE" if val else "FALSE")
                        elif isinstance(val, (int, float)):
                            valores_formateados.append(str(val))
                        elif isinstance(val, datetime):
                            valores_formateados.append(f"'{val.strftime('%Y-%m-%d %H:%M:%S')}'")
                        else:
                            # Escapar comillas simples
                            val_escapado = str(val).replace("'", "''")
                            valores_formateados.append(f"'{val_escapado}'")
                    
                    valores_linea = ", ".join(valores_formateados)
                    
                    # Último registro del batch
                    if idx == total_filas - 1:
                        f.write(f"({valores_linea});\n")
                    else:
                        f.write(f"({valores_linea}),\n")
                
                # Separador entre batches
                if batch_end < total_filas:
                    f.write(f"-- Batch {batch_start//batch_size + 1} completado\n")
            
            # Footer
            f.write(f"\n-- ============================================\n")
            f.write(f"-- Script completado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        logger.info(f"   ✅ Script SQL guardado: {ruta_archivo} ({total_filas:,} registros)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error escribiendo script SQL: {e}")
        return False


def _inferir_tipo_sql(serie: pd.Series) -> str:
    """Infiera el tipo SQL apropiado para una columna"""
    if pd.api.types.is_integer_dtype(serie):
        return "INT"
    elif pd.api.types.is_float_dtype(serie):
        return "DECIMAL(15,2)"
    elif pd.api.types.is_bool_dtype(serie):
        return "BOOLEAN"
    elif pd.api.types.is_datetime64_any_dtype(serie):
        return "TIMESTAMP"
    else:
        # Texto: calcular longitud máxima
        max_len = serie.astype(str).str.len().max() if len(serie) > 0 else 255
        if max_len > 1000:
            return "TEXT"
        elif max_len > 255:
            return f"VARCHAR({min(max_len, 4000)})"
        else:
            return f"VARCHAR({max(255, max_len + 10)})"


# ============================================================================
# INYECCIÓN A BASE DE DATOS VIVA
# ============================================================================

def _inyectar_base_de_datos_viva(
    df: pd.DataFrame,
    nombre_tabla: str,
    db_config: Dict[str, Any],
    if_exists: str = 'append',
    chunk_size: int = DEFAULT_CHUNK_SIZE
) -> bool:
    """
    Inyecta datos directamente a una base de datos usando SQLAlchemy
    
    Args:
        df: DataFrame con los datos
        nombre_tabla: Nombre de la tabla destino
        db_config: Configuración de conexión
        if_exists: 'fail', 'replace', 'append'
        chunk_size: Tamaño de lote para inserción masiva
    """
    try:
        import sqlalchemy as sa
        from sqlalchemy import text, inspect
        
        # Validar configuración
        db_type = db_config.get('db_type', 'postgresql')
        if db_type not in SUPPORTED_ENGINES:
            logger.error(f"❌ Motor no soportado: {db_type}")
            logger.info(f"   Motores soportados: {SUPPORTED_ENGINES}")
            return False
        
        # Construir connection string
        conn_string = _construir_connection_string(db_config)
        
        if not conn_string:
            logger.error("❌ No se pudo construir connection string")
            return False
        
        logger.info(f"🌐 Conectando a {db_type.upper()}...")
        
        # Crear engine
        engine = sa.create_engine(
            conn_string,
            pool_pre_ping=True,
            pool_recycle=3600
        )
        
        # Probar conexión
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        
        logger.info(f"   ✅ Conexión establecida")
        
        # Verificar si la tabla existe
        inspector = inspect(engine)
        tabla_existe = inspector.has_table(nombre_tabla)
        
        if tabla_existe and if_exists == 'fail':
            logger.error(f"❌ La tabla '{nombre_tabla}' ya existe y if_exists='fail'")
            engine.dispose()
            return False
        
        elif tabla_existe and if_exists == 'replace':
            logger.warning(f"⚠️ Reemplazando tabla existente: {nombre_tabla}")
            # Drop y recreate
            df.to_sql(
                nombre_tabla, 
                con=engine, 
                if_exists='replace', 
                index=False,
                chunksize=chunk_size
            )
        
        else:
            # Append o crear nueva
            logger.info(f"   ⏳ Insertando {len(df):,} registros en lote de {chunk_size}...")
            
            # Usar to_sql con chunks para mejor performance
            df.to_sql(
                nombre_tabla,
                con=engine,
                # correcion de redundancia: if_exists ya se maneja arriba, aquí siempre es append
                if_exists='append',
                index=False,
                chunksize=chunk_size,
                method='multi'  # Multi-row insert para mejor performance
            )
        
        # Verificar resultado
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {nombre_tabla}"))
            count = result.scalar()
        
        logger.info(f"   ✅ Inyección completada: {count:,} registros en tabla '{nombre_tabla}'")
        
        engine.dispose()
        return True
        
    except ImportError:
        logger.error("❌ SQLAlchemy no está instalado")
        logger.info("   Instala: pip install sqlalchemy pymysql psycopg2-binary pyodbc")
        return False
    except Exception as e:
        logger.error(f"❌ Falló la inyección en vivo: {e}")
        return False


def _construir_connection_string(db_config: Dict[str, Any]) -> Optional[str]:
    """Construye el connection string según el tipo de base de datos"""
    db_type = db_config.get('db_type', 'postgresql')
    
    # Intentar obtener de variable de entorno si no viene en config
    host = db_config.get('host') or os.getenv(f"{db_type.upper()}_HOST", 'localhost')
    port = db_config.get('port') or os.getenv(f"{db_type.upper()}_PORT")
    database = db_config.get('database') or os.getenv(f"{db_type.upper()}_DATABASE")
    username = db_config.get('username') or os.getenv(f"{db_type.upper()}_USER")
    password = db_config.get('password') or os.getenv(f"{db_type.upper()}_PASSWORD")
    
    # Validar campos obligatorios
    if not database:
        logger.error("❌ Nombre de base de datos no especificado")
        return None
    
    # SQLite es especial
    if db_type == 'sqlite':
        sqlite_path = db_config.get('sqlite_path', 'nahual_data.db')
        return f"sqlite:///{sqlite_path}"
    
    # Validar credenciales
    if not username:
        logger.warning("⚠️ Usuario no especificado, intentando conexión sin autenticación")
    
    # Construir según motor
    if db_type == 'postgresql':
        port = port or 5432
        dialect = SQLALCHEMY_DIALECTS['postgresql']
        return f"{dialect}://{username}:{password}@{host}:{port}/{database}"
    
    elif db_type == 'mysql':
        port = port or 3306
        dialect = SQLALCHEMY_DIALECTS['mysql']
        return f"{dialect}://{username}:{password}@{host}:{port}/{database}"
    
    elif db_type == 'sqlserver':
        port = port or 1433
        dialect = SQLALCHEMY_DIALECTS['sqlserver']
        # Para SQL Server, puede necesitar driver específico
        driver = db_config.get('driver', 'ODBC+Driver+17+for+SQL+Server')
        return f"{dialect}://{username}:{password}@{host}:{port}/{database}?driver={driver}"
    
    else:
        logger.error(f"❌ Motor no soportado: {db_type}")
        return None


# ============================================================================
# FUNCIONES DE UTILIDAD
# ============================================================================

def generar_create_table_sql(df: pd.DataFrame, nombre_tabla: str, dialecto: str = 'mysql') -> str:
    """Genera solo el CREATE TABLE sin inserts"""
    if dialecto == 'mysql':
        quote_char = '`'
    elif dialecto in ['postgresql', 'sqlserver']:
        quote_char = '"'
    else:
        quote_char = ''
        
    columnas = []
    for col in df.columns:
        tipo = _inferir_tipo_sql(df[col])
        columnas.append(f"    {quote_char}{col}{quote_char} {tipo}")
        
    # 🌟 LA CURA: Unimos las columnas fuera de la f-string para evitar la '\n' maldita
    cuerpo_tabla = ",\n".join(columnas)
    
    # Ahora la f-string es completamente plana y segura para Python 3.11
    return f"CREATE TABLE {quote_char}{nombre_tabla}{quote_char} (\n{cuerpo_tabla}\n);"


def generar_inserts_sql(df: pd.DataFrame, nombre_tabla: str, dialecto: str = 'mysql') -> List[str]:
    """Genera lista de sentencias INSERT independientes (útil para debugging y fuzzing)"""
    # Manejo profesional de dialectos SQL para los identificadores
    if dialecto == 'mysql':
        quote_char = '`'
    elif dialecto in ['postgresql', 'sqlserver']:
        quote_char = '"'
    else:
        quote_char = ''
    
    columnas = ", ".join([f"{quote_char}{col}{quote_char}" for col in df.columns])
    inserts = []
    
    for _, row in df.iterrows():
        valores = []
        for val in row:
            # 1. Manejo de Nulos
            if pd.isna(val) or val is None:
                valores.append("NULL")
                
            # 2. Manejo de Strings (Corrección de comillas)
            elif isinstance(val, str):
                val_escapado = val.replace("'", "''")
                valores.append(f"'{val_escapado}'")
                
            # 3. Manejo de Booleanos (Crucial para que no truene la DB)
            elif isinstance(val, (bool, bool)):  # En pandas a veces mapea como bool de numpy
                valores.append("1" if val else "0")
                
            # 4. Manejo de Fechas y Tiempo
            elif isinstance(val, (datetime, pd.Timestamp)):
                valores.append(f"'{val.strftime('%Y-%m-%d %H:%M:%S')}'")
                
            # 5. Números (Integers, Floats)
            else:
                valores.append(str(val))
        
        # Inyección limpia por cada fila
        sentencia = f"INSERT INTO {quote_char}{nombre_tabla}{quote_char} ({columnas}) VALUES ({', '.join(valores)});"
        inserts.append(sentencia)
    
    return inserts