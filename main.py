#!/usr/bin/env python3
"""
NAHUAL - Generador de Datos Sintéticos con Motor Switcheable
Estrategia: Python Faker para volúmenes bajos/medios, Rust para masivos
"""

import sys
import time
import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# Configuración de logging profesional
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================================
# IMPORTS CON FALLBACK Y VALIDACIÓN DE ESTRUCTURA
# ============================================================================
try:
    from inputs.user import menu_interactivo
    logger.info(" Módulo inputs.User cargado")
except ImportError as e:
    logger.error(f" No se pudo importar inputs.User: {e}")
    logger.error("   Verifica que la carpeta se llame 'Inputs' (con I mayúscula)")
    sys.exit(1)

try:
    from pipilinais import State
    logger.info(" Módulo pipeline cargado")
except ImportError as e:
    logger.error(f" No se pudo importar pipeline: {e}")
    sys.exit(1)

# Intento de importar el motor Rust (opcional, falla silenciosamente)
RUST_AVAILABLE = False
try:
    # Esto asume que compilaste tu módulo Rust como biblioteca dinámica
    # Por ahora es placeholder - cuando implementes PyO3 se activa
    # import motorrust  # descomentar cuando tengas el binding

    # RUST_AVAILABLE = True
    # logger.info(" Motor Rust disponible para volúmenes masivos")
    
    logger.info(" Usando motor Python Faker (Rust no disponible)")
except ImportError:
    logger.info(" Motor Python Faker (modo estándar)")


# ============================================================================
# CONFIGURACIÓN DE UMBRALES PARA SWITCH DE MOTOR
# ============================================================================
class MotorSwitcher:
    """Decide qué motor usar según el volumen solicitado"""
    
    # Umbrales configurables (en registros)
    UMBRAL_RUST = 100_000      # A partir de 100k registros, usar Rust
    UMBRAL_ADVERTENCIA = 50_000  # A partir de 50k, advertir que puede ser lento
    
    @staticmethod
    def decidir_motor(volumen: int) -> str:
        """
        Retorna 'rust' o 'python' según el volumen.
        Puedes sobreescribir con config del usuario.
        """
        if RUST_AVAILABLE and volumen >= MotorSwitcher.UMBRAL_RUST:
            return 'rust'
        return 'python'
    
    @staticmethod
    def mostrar_recomendacion(volumen: int):
        """Muestra sugerencia al usuario si el volumen es alto pero Rust no está"""
        if volumen >= MotorSwitcher.UMBRAL_RUST and not RUST_AVAILABLE:
            logger.warning(f" Generando {volumen:,} registros con Python Faker")
            logger.warning(f"   Esto podría ser LENTO. Considera compilar el motor Rust")
            logger.warning(f"   para volúmenes > {MotorSwitcher.UMBRAL_RUST:,} registros")
        elif volumen >= MotorSwitcher.UMBRAL_ADVERTENCIA:
            logger.info(f" Volumen {volumen:,} registros - puede tomar unos segundos")


# ============================================================================
# BANNER Y PRESENTACIÓN
# ============================================================================
def mostrar_banner():
    """El cartel que asusta/impresiona"""
    banner = r"""
     _   _       _                 _ 
    | \ | |     | |               | |
    |  \| | __ _| |__  _   _  __ _| |
    | . ` |/ _` | '_ \| | | |/ _` | |
    | |\  | (_| | | | | |_| | (_| | |
    \_| \_/\__,_|_| |_|\__,_|\__,_|_|
    :: Shadow Data Generator v2.0 ::
    :: Perro - June - SABIN - :3  ::
    """
    print(banner)
    print("=" * 60)
    print(f" Iniciando NAHUAL - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" Motor principal: Python + Faker")
    print(f" Motor masivo: {'DISPONIBLE' if RUST_AVAILABLE else 'NO DETECTADO'}")
    print(f"  Umbral Rust: {MotorSwitcher.UMBRAL_RUST:,} registros")
    print("=" * 60)
    print()


# ============================================================================
# GUARDADO DE MÉTRICAS (para análisis posterior)
# ============================================================================
def guardar_metricas(orden_config: Dict[str, Any], 
                      volumen: int, 
                      motor_usado: str,
                      tiempo_ejecucion: float):
    #NOta no moverle nada aca por si acaso
    """Guarda un registro de la generación para análisis"""
    metricas_dir = Path("metricas")
    metricas_dir.mkdir(exist_ok=True)
    
    registro = {
        "timestamp": datetime.now().isoformat(),
        "volumen": volumen,
        "motor": motor_usado,
        "tiempo_segundos": round(tiempo_ejecucion, 2),
        "config": orden_config
    }
    
    archivo_log = metricas_dir / f"generacion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(archivo_log, 'w') as f:
        json.dump(registro, f, indent=2, default=str)
    
    logger.info(f" Métricas guardadas en {archivo_log}")


# ============================================================================
# MAIN - EL ORQUESTADOR DEFINITIVO
# ============================================================================
def main():
    """El cerebro que todo lo coordina"""
    mostrar_banner()
    
    # Estadísticas de la sesión
    stats = {
        'generaciones': 0,
        'total_registros': 0,
        'total_tiempo': 0.0,
        'usos_rust': 0,
        'usos_python': 0
    }
    
    while True:
        try:
            # ------------------------------------------------------------
            # 1. RECOLECTAR CONFIGURACIÓN DEL USUARIO
            # ------------------------------------------------------------
            print("\n>>> CONFIGURANDO GENERACIÓN <<<")
            orden_config = menu_interactivo()
            
            if not orden_config:
                logger.info("Generación cancelada por el usuario")
                respuesta = input("\n¿Salir del programa? (s/n): ").strip().lower()
                if respuesta == 's':
                    break
                continue
            
            # Extraer volumen (asumiendo que viene en la config)
            # Ajusta esto según cómo devuelva menu_interactivo()
            volumen = orden_config.get('volumen', orden_config.get('cantidad', 1000))
            if not isinstance(volumen, int):
                try:
                    volumen = int(volumen)
                except (ValueError, TypeError):
                    volumen = 1000
            
            # ------------------------------------------------------------
            # 2. DECIDIR MOTOR SEGÚN VOLUMEN
            # ------------------------------------------------------------
            motor = MotorSwitcher.decidir_motor(volumen)
            MotorSwitcher.mostrar_recomendacion(volumen)
            
            logger.info(f" Generando {volumen:,} registros usando motor: {motor.upper()}")
            
            # Si usamos Rust, inyectamos la instrucción en la config
            if motor == 'rust' and RUST_AVAILABLE:
                orden_config['_motor'] = 'rust'
                orden_config['_modulo_rust'] = 'motorrust'  # placeholder
            else:
                orden_config['_motor'] = 'python'
            
            # ------------------------------------------------------------
            # 3. EJECUTAR PIPELINE
            # ------------------------------------------------------------
            inicio = time.perf_counter()
            
            pipeline = State(orden_config)
            pipeline.run()  # Aquí dentro debe respetar el '_motor' de la config
            
            tiempo = time.perf_counter() - inicio
            
            # ------------------------------------------------------------
            # 4. ACTUALIZAR ESTADÍSTICAS
            # ------------------------------------------------------------
            stats['generaciones'] += 1
            stats['total_registros'] += volumen
            stats['total_tiempo'] += tiempo
            
            if motor == 'rust':
                stats['usos_rust'] += 1
            else:
                stats['usos_python'] += 1
            
            # Guardar métricas para análisis
            guardar_metricas(orden_config, volumen, motor, tiempo)
            
            # Mostrar resumen de esta generación
            print("\n" + "="*50)
            print(f" GENERACIÓN COMPLETADA")
            print(f"    Registros: {volumen:,}")
            print(f"     Motor: {motor.upper()}")
            print(f"     Tiempo: {tiempo:.2f} segundos")
            print(f"    Velocidad: {volumen/tiempo:.0f} registros/segundo")
            print("="*50)
            
            # ------------------------------------------------------------
            # 5. PREGUNTAR SI CONTINUAR
            # ------------------------------------------------------------
            print(f"\n Estadísticas de sesión:")
            print(f"   Generaciones: {stats['generaciones']}")
            print(f"   Registros totales: {stats['total_registros']:,}")
            print(f"   Tiempo total: {stats['total_tiempo']:.1f}s")
            print(f"   Usos Rust: {stats['usos_rust']} | Python: {stats['usos_python']}")
            
            respuesta = input("\n ¿Generar otro set de datos? (s/n): ").strip().lower()
            if respuesta != 's':
                print("\n Fue un Gusto Ayudar. ¡Hasta la próxima!")
                break
                
        except KeyboardInterrupt:
            print("\n\n Ejecución abortada por el usuario")
            print(f" Resumen final: {stats['generaciones']} generaciones, "
                  f"{stats['total_registros']:,} registros en {stats['total_tiempo']:.1f}s")
            print("👋 Nos vemos!")
            sys.exit(0)
            
        except Exception as e:
            logger.error(f" Error crítico: {e}", exc_info=True)
            print("\n El pipeline falló. Revisa los logs.")
            respuesta = input("¿Intentar otra generación? (s/n): ").strip().lower()
            if respuesta != 's':
                break


if __name__ == "__main__":
    main()