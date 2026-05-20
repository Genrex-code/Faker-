#!/usr/bin/env python3
"""
NAHUAL - Generador de Datos Sintéticos con Motor Switcheable
Versión estandarizada con InputManager y ExportManager
"""

import sys
import time
import logging
import json
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def mostrar_banner():
    banner = r"""
     _   _       _                 _ 
    | \ | |     | |               | |
    |  \| | __ _| |__  _   _  __ _| |
    | . ` |/ _` | '_ \| | | |/ _` | |
    | |\  | (_| | | | | |_| | (_| | |
    \_| \_/\__,_|_| |_|\__,_|\__,_|_|
    :: Shadow Data Generator v2.0 ::
    """
    print(banner)
    print("=" * 60)
    print(f"🚀 NAHUAL - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


def guardar_metricas(config: Dict[str, Any], volumen: int, motor: str, tiempo: float):
    """Guarda métricas de generación"""
    metricas_dir = Path("metricas")
    metricas_dir.mkdir(exist_ok=True)
    
    registro = {
        "timestamp": datetime.now().isoformat(),
        "volumen": volumen,
        "motor": motor,
        "tiempo_segundos": round(tiempo, 2),
        "config": config
    }
    
    archivo = metricas_dir / f"generacion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(archivo, 'w', encoding='utf-8') as f:
        json.dump(registro, f, indent=2, default=str)
    
    logger.info(f"📝 Métricas guardadas en {archivo}")


def main():
    mostrar_banner()
    
    from inputs.input_manager import obtener_configuracion
    from pipilinais import State
    
    stats = {'generaciones': 0, 'total_registros': 0, 'total_tiempo': 0.0}
    
    while True:
        try:
            print("\n" + "="*50)
            print(">>> SELECCIONA MODO DE ENTRADA <<<")
            print("   1) Interactivo (pregunta todo)")
            print("   2) Desde archivo JSON/YAML/TXT")
            print("   3) Salir")
            
            opcion = input("\n👉 Elige (1-3): ").strip()
            
            if opcion == '1':
                config = obtener_configuracion(modo='interactivo')
            elif opcion == '2':
                ruta = input("📁 Ruta del archivo de configuración: ").strip()
                if not ruta:
                    logger.warning("Ruta no proporcionada")
                    continue
                config = obtener_configuracion(modo='archivo', fuente=ruta)
            elif opcion == '3':
                print("\n🐾 ¡Hasta la próxima!")
                break
            else:
                print("❌ Opción inválida")
                continue
            
            if not config:
                logger.warning("Configuración vacía")
                continue
            
            volumen = config.get('volumen', 1000)
            motor = config.get('_motor', 'python')
            
            logger.info(f"🎯 Generando {volumen:,} registros con motor: {motor.upper()}")
            
            inicio = time.perf_counter()
            pipeline = State(config)
            metricas = pipeline.run()
            tiempo = time.perf_counter() - inicio
            
            if metricas and not metricas.get('error'):
                stats['generaciones'] += 1
                stats['total_registros'] += volumen
                stats['total_tiempo'] += tiempo
                
                guardar_metricas(config, volumen, motor, tiempo)
                
                print("\n" + "="*50)
                print(f"✅ GENERACIÓN COMPLETADA")
                print(f"   📊 Registros: {volumen:,}")
                print(f"   ⚙️  Motor: {motor.upper()}")
                print(f"   ⏱️  Tiempo: {tiempo:.2f}s")
                print("="*50)
                
                print(f"\n📊 Sesión: {stats['generaciones']} gen | {stats['total_registros']:,} reg | {stats['total_tiempo']:.1f}s")
            else:
                logger.error(f"❌ Error: {metricas.get('error') if metricas else 'Desconocido'}")
            
            respuesta = input("\n🔄 ¿Otra generación? (s/n): ").strip().lower()
            if respuesta != 's':
                break
                
        except KeyboardInterrupt:
            print("\n\n🛑 Ejecución cancelada")
            break
        except Exception as e:
            logger.error(f"💥 Error: {e}", exc_info=True)
            respuesta = input("¿Intentar de nuevo? (s/n): ").strip().lower()
            if respuesta != 's':
                break


if __name__ == "__main__":
    main()