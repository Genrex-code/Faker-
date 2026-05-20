"""
NAHUAL - Módulo de Entrada Interactiva (Inputs/User.py)
Responsabilidad: Recolectar configuración del usuario de forma robusta y amigable.
Soporta: Modo interactivo (por defecto) y modo silencioso para pruebas/scripts.
"""

import sys
import logging
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTES Y CONFIGURACIÓN
# ============================================================================
FORMATOS_VALIDOS = {
    '1': 'excel',
    '2': 'csv', 
    '3': 'json',
    '4': 'parquet',  # Para el futuro
    'excel': 'excel',
    'csv': 'csv',
    'json': 'json',
    'parquet': 'parquet'
}

# Diccionario de columnas comunes (para autocompletado/sugerencias)
COLUMNAS_COMUNES = [
    'nombre', 'email', 'edad', 'telefono', 'direccion', 'ciudad', 'pais',
    'rfc', 'curp', 'fecha_nacimiento', 'salario', 'id', 'uuid',
    'empresa', 'cargo', 'departamento', 'fecha_contratacion',
    'activo', 'cliente_id', 'producto_id', 'categoria'
]

# Umbrales para advertencias
UMBRAL_ADVERTENCIA = 50_000
UMBRAL_CRITICO = 500_000
UMBRAL_RUST_SUGERIDO = 100_000


# ============================================================================
# FUNCIONES AUXILIARES DE ENTRADA
# ============================================================================
def pedir_entero(
    mensaje: str, 
    min_val: int = 1, 
    max_val: Optional[int] = None,
    default: Optional[int] = None
) -> int:
    """
    Pide un número entero al usuario con validación de rangos.
    
    Args:
        mensaje: Texto a mostrar
        min_val: Valor mínimo permitido
        max_val: Valor máximo permitido (None = sin límite)
        default: Valor por defecto si el usuario presiona Enter sin escribir
    """
    while True:
        try:
            entrada = input(mensaje).strip()
            
            # Manejar valor por defecto
            if not entrada and default is not None:
                print(f"   → Usando valor por defecto: {default:,}")
                return default
            
            if not entrada:
                print("❌ No escribiste nada. Intenta de nuevo.")
                continue
            
            valor = int(entrada)
            
            if valor < min_val:
                print(f"❌ El valor mínimo es {min_val:,}.")
                continue
            
            if max_val is not None and valor > max_val:
                print(f"⚠️ El valor máximo sugerido es {max_val:,}.")
                print(f"   Generar {valor:,} registros podría consumir mucha memoria.")
                confirmar = input("   ¿Confirmas continuar? (s/n): ").strip().lower()
                if confirmar != 's':
                    continue
            
            return valor
            
        except ValueError:
            print("❌ Error: Debes ingresar un número entero válido.")
        except KeyboardInterrupt:
            print("\n🛑 Operación cancelada por el usuario.")
            sys.exit(0)


def pedir_columnas(
    mensaje: str, 
    mostrar_ejemplos: bool = True,
    permitir_archivo: bool = True
) -> List[str]:
    """
    Pide las columnas al usuario, con soporte para carga desde archivo.
    
    Args:
        mensaje: Texto a mostrar
        mostrar_ejemplos: Si muestra ejemplos comunes
        permitir_archivo: Si permite cargar desde archivo .txt
    """
    while True:
        try:
            print(f"\n{'-'*50}")
            print("📋 CONFIGURACIÓN DE COLUMNAS")
            print(f"{'-'*50}")
            
            if mostrar_ejemplos:
                print("💡 Columnas comunes sugeridas:")
                print(f"   {', '.join(COLUMNAS_COMUNES[:8])}...")
                print(f"   → Puedes usar cualquier nombre que quieras")
            
            if permitir_archivo:
                print("\n✨ TIP: Puedes escribir 'archivo' para cargar columnas desde un .txt")
            
            print()
            columnas_raw = input(mensaje).strip()
            
            if not columnas_raw:
                print("⚠️ No puedes pedir un dataset sin columnas. Intenta de nuevo.")
                continue
            
            # Cargar desde archivo si se solicita
            if permitir_archivo and columnas_raw.lower() == 'archivo':
                columnas = _cargar_columnas_desde_archivo()
                if columnas:
                    return columnas
                continue
            
            # Procesar entrada normal: separar por comas, limpiar espacios
            columnas = [
                col.strip().lower() 
                for col in columnas_raw.split(",") 
                if col.strip()
            ]
            
            if len(columnas) == 0:
                print("❌ No se detectaron columnas válidas.")
                continue
            
            # Validar columnas duplicadas
            if len(columnas) != len(set(columnas)):
                duplicados = [col for col in set(columnas) if columnas.count(col) > 1]
                print(f"⚠️ Advertencia: Columnas duplicadas detectadas: {duplicados}")
                print("   Se eliminarán los duplicados automáticamente.")
                columnas = list(dict.fromkeys(columnas))  # Preserva orden, elimina duplicados
            
            # Mostrar resumen
            print(f"\n✅ Columnas configuradas ({len(columnas)} campos):")
            print(f"   {', '.join(columnas[:10])}{'...' if len(columnas) > 10 else ''}")
            
            # Confirmación para muchas columnas
            if len(columnas) > 20:
                confirmar = input(f"\n⚠️ Son {len(columnas)} columnas. ¿Confirmas? (s/n): ").strip().lower()
                if confirmar != 's':
                    continue
            
            return columnas
                
        except KeyboardInterrupt:
            print("\n🛑 Operación cancelada por el usuario.")
            sys.exit(0)


def _cargar_columnas_desde_archivo() -> Optional[List[str]]:
    """
    Carga una lista de columnas desde un archivo de texto.
    Formato esperado: una columna por línea, o separadas por comas.
    """
    print("\n📂 CARGAR COLUMNAS DESDE ARCHIVO")
    print("   El archivo debe tener una columna por línea o separadas por coma")
    
    ruta = input("   Ruta del archivo (ej: columnas.txt): ").strip()
    
    if not ruta:
        print("   ❌ No especificaste archivo.")
        return None
    
    archivo = Path(ruta)
    
    if not archivo.exists():
        print(f"   ❌ El archivo '{ruta}' no existe.")
        return None
    
    try:
        contenido = archivo.read_text(encoding='utf-8')
        
        # Intentar detectar formato: si hay comas, asumir CSV en una línea
        if ',' in contenido and '\n' not in contenido:
            columnas = [col.strip().lower() for col in contenido.split(',') if col.strip()]
        else:
            # Asumir una columna por línea
            columnas = [linea.strip().lower() for linea in contenido.splitlines() if linea.strip()]
        
        if columnas:
            print(f"   ✅ Cargadas {len(columnas)} columnas desde '{ruta}'")
            return columnas
        else:
            print("   ❌ El archivo no contiene columnas válidas.")
            return None
            
    except Exception as e:
        print(f"   ❌ Error leyendo archivo: {e}")
        return None


def pedir_formato() -> str:
    """Menú interactivo para seleccionar formato de salida."""
    print(f"\n{'='*50}")
    print("📁 SELECCIÓN DE FORMATO DE SALIDA")
    print(f"{'='*50}")
    print("   1) Excel (.xlsx)  - Ideal para análisis en oficina")
    print("   2) CSV (.csv)     - Compatible con bases de datos")
    print("   3) JSON (.json)   - Para APIs y sistemas modernos")
    print("   4) Parquet (.parquet) - Formato columnar eficiente (experimental)")
    print()
    
    while True:
        try:
            opcion = input("👉 Elige el número (1-4): ").strip()
            
            if opcion in FORMATOS_VALIDOS:
                formato = FORMATOS_VALIDOS[opcion]
                print(f"   ✅ Formato seleccionado: {formato.upper()}")
                return formato
            else:
                print("❌ Opción no válida. Teclea 1, 2, 3 o 4.")
                
        except KeyboardInterrupt:
            print("\n🛑 Operación cancelada.")
            sys.exit(0)


def pedir_volumen_con_ayuda() -> int:
    """
    Pide el volumen con información contextual y sugerencia de motor.
    """
    print(f"\n{'='*50}")
    print("📊 CONFIGURACIÓN DE VOLUMEN")
    print(f"{'='*50}")
    print("   📌 RANGOS SUGERIDOS:")
    print(f"      • Pequeño: 1 - 1,000 registros  (rápido, pruebas)")
    print(f"      • Mediano: 1,001 - 50,000 registros")
    print(f"      • Grande: 50,001 - {UMBRAL_RUST_SUGERIDO:,} registros (puede tomar segundos)")
    print(f"      • Masivo: > {UMBRAL_RUST_SUGERIDO:,} registros (usará motor RUST si está disponible)")
    print()
    
    volumen = pedir_entero(
        "🔢 ¿Cuántos registros necesitas? ",
        min_val=1,
        max_val=None,  # Sin límite máximo fijo
        default=1000
    )
    
    # Mostrar advertencias según el volumen
    if volumen >= UMBRAL_RUST_SUGERIDO:
        print(f"\n⚠️ AVISO: {volumen:,} registros es un volumen MASIVO.")
        print(f"   → Se recomienda usar el motor RUST para mejor rendimiento.")
        print(f"   → Si Rust no está disponible, Python podría tardar MINUTOS.")
    elif volumen >= UMBRAL_ADVERTENCIA:
        print(f"\n📢 NOTA: {volumen:,} registros puede tomar varios segundos en Python.")
        print(f"   → Considera usar volúmenes más pequeños para pruebas rápidas.")
    
    return volumen


def mostrar_resumen_config(config: Dict[str, Any]) -> None:
    """Muestra un resumen bonito de la configuración antes de generar."""
    print(f"\n{'='*60}")
    print("📋 RESUMEN DE CONFIGURACIÓN")
    print(f"{'='*60}")
    print(f"   📊 Volumen:    {config.get('volumen', 'N/A'):,} registros")
    print(f"   📝 Columnas:   {len(config.get('columnas', []))} campos")
    print(f"   💾 Formato:    {config.get('formato', 'N/A').upper()}")
    print(f"   ⚙️  Motor:      {config.get('_motor', 'auto (Python)')}")
    print(f"{'='*60}")
    
    # Mostrar primeras columnas si son pocas
    columnas = config.get('columnas', [])
    if len(columnas) <= 10:
        print(f"   Campos: {', '.join(columnas)}")
    else:
        print(f"   Campos: {', '.join(columnas[:8])}... +{len(columnas)-8} más")
    print(f"{'='*60}")


# ============================================================================
# FUNCIÓN PRINCIPAL DEL MÓDULO
# ============================================================================
def menu_interactivo() -> Dict[str, Any]:
    """
    Interfaz principal de terminal para Nahual.
    
    Returns:
        Diccionario con la configuración para el pipeline:
        {
            'volumen': int,
            'columnas': List[str],
            'formato': str,
            '_motor': str (opcional, lo define el main después)
        }
    """
    print("\n" + "🐺"*30)
    print("   NAHUAL - GENERADOR DE DATOS SINTÉTICOS")
    print("   Modo Interactivo v2.0")
    print("🐺"*30)
    
    config = {}
    
    # FASE 1: Volumen (con ayuda contextual)
    config['volumen'] = pedir_volumen_con_ayuda()
    
    # FASE 2: Estructura (columnas)
    config['columnas'] = pedir_columnas(
        "✏️  Ingresa las columnas separadas por coma: ",
        mostrar_ejemplos=True,
        permitir_archivo=True
    )
    
    # FASE 3: Formato de salida
    config['formato'] = pedir_formato()
    
    # Mostrar resumen final
    mostrar_resumen_config(config)
    
    # Confirmación final
    print("\n✅ ¡Configuración completada!")
    respuesta = input("   ¿Generar datos con esta configuración? (s/n): ").strip().lower()
    
    if respuesta != 's':
        print("   ⚠️ Generación cancelada.")
        return {}
    
    return config


# ============================================================================
# MODO NO INTERACTIVO (para pruebas/scripts)
# ============================================================================
def config_desde_dict(config_parcial: Dict[str, Any]) -> Dict[str, Any]:
    """
    Permite pasar configuración directamente (útil para pruebas).
    
    Args:
        config_parcial: Diccionario con algunos o todos los campos
        
    Returns:
        Configuración completa con valores por defecto
    """
    config_completa = {
        'volumen': config_parcial.get('volumen', 100),
        'columnas': config_parcial.get('columnas', ['nombre', 'email']),
        'formato': config_parcial.get('formato', 'csv')
    }
    
    # Validaciones básicas
    if not isinstance(config_completa['volumen'], int) or config_completa['volumen'] <= 0:
        config_completa['volumen'] = 100
    
    if not config_completa['columnas']:
        config_completa['columnas'] = ['nombre', 'email']
    
    if config_completa['formato'] not in FORMATOS_VALIDOS.values():
        config_completa['formato'] = 'csv'
    
    return config_completa


# ============================================================================
# PRUEBA RÁPIDA DEL MÓDULO
# ============================================================================
if __name__ == "__main__":
    # Configurar logging para pruebas
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    print("\n🧪 Probando módulo Inputs/User.py")
    print("="*50)
    
    # Probar modo interactivo
    config = menu_interactivo()
    
    if config:
        print("\n✅ Configuración capturada:")
        for key, value in config.items():
            if key == 'columnas':
                print(f"   {key}: {len(value)} campos")
            else:
                print(f"   {key}: {value}")
    else:
        print("\n⚠️ No se generó configuración")