"""
NAHUAL - Pipilinais v4.0 (Orquestador Core)
REFACTORIZADO: Responsabilidad única - solo orquesta, no implementa exportadores.
Delega TODA exportación al módulo exports/ExportManager.py
"""

import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class State:
    """
    Pipilinais v4.0 - Orquestador Core de Nahual
    
    PRINCIPIOS:
    1. Recibe config del Main
    2. Decide qué motor usar (Python Faker o Rust)
    3. Orquesta generación + exportación (DELEGANDO)
    4. Mide performance
    5. NO implementa lógica de exportación - eso es responsabilidad de exports/
    """
    
    DEFAULT_VOLUMEN = 1000
    DEFAULT_FORMATO = 'excel'
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.dataset = None
        self.metricas = {
            'inicio': None,
            'fin': None,
            'tiempo_generacion': 0.0,
            'tiempo_exportacion': 0.0,
            'motor_usado': None,
            'registros_generados': 0,
            'error': None
        }
        
        # Extraer configuración con defaults
        self.volumen = self.config.get('volumen', self.DEFAULT_VOLUMEN)
        self.columnas = self.config.get('columnas', [])
        self.motor_elegido = self.config.get('_motor', 'python')
        self.formato_salida = self.config.get('formato', self.DEFAULT_FORMATO)
        
        # Validaciones tempranas
        self._validar_configuracion()
    
    def _validar_configuracion(self):
        """Valida que la configuración sea coherente"""
        if not isinstance(self.volumen, int) or self.volumen <= 0:
            logger.warning(f"⚠️ Volumen inválido: {self.volumen}. Usando {self.DEFAULT_VOLUMEN}")
            self.volumen = self.DEFAULT_VOLUMEN
        
        if self.volumen > 10_000_000:
            logger.warning(f"🔥 Volumen MASIVO: {self.volumen:,} registros")
            logger.warning("   Considera usar motor RUST o generación por lotes")
        
        if not self.columnas:
            logger.error("❌ Lista de columnas vacía")
        
        if self.motor_elegido not in ['python', 'rust']:
            logger.warning(f"⚠️ Motor '{self.motor_elegido}' no reconocido. Usando 'python'")
            self.motor_elegido = 'python'
    
    def run(self) -> Optional[Dict[str, Any]]:
        """Ejecuta el pipeline completo"""
        self.metricas['inicio'] = time.perf_counter()
        
        logger.info("=" * 60)
        logger.info(f"🧠 [PIPILINAIS] Iniciando pipeline")
        logger.info(f"   📊 Volumen: {self.volumen:,} registros")
        logger.info(f"   📝 Columnas: {len(self.columnas)} campos")
        logger.info(f"   ⚙️  Motor: {self.motor_elegido.upper()}")
        logger.info(f"   💾 Formato: {self.formato_salida.upper()}")
        logger.info("=" * 60)
        
        # Validación crítica
        if not self.columnas:
            self.metricas['error'] = "Lista de columnas vacía"
            logger.error(f"❌ {self.metricas['error']}")
            return self.metricas
        
        try:
            # FASE 1: GENERACIÓN
            if not self._fase_generacion():
                self.metricas['error'] = "Falló la generación"
                return self.metricas
            
            # FASE 2: EXPORTACIÓN (DELEGADA)
            if not self._fase_exportacion():
                self.metricas['error'] = "Falló la exportación"
                logger.warning("⚠️ Los datos se generaron pero no se guardaron")
            
            # Métricas finales
            self.metricas['fin'] = time.perf_counter()
            self.metricas['tiempo_total'] = self.metricas['fin'] - self.metricas['inicio']
            
            self._mostrar_resumen()
            return self.metricas
            
        except Exception as e:
            self.metricas['error'] = str(e)
            logger.error(f"💥 Error crítico: {e}", exc_info=True)
            return self.metricas
    
    def _fase_generacion(self) -> bool:
        """Delega al motor correspondiente"""
        logger.info(f"🏭 [GENERACIÓN] Motor: {self.motor_elegido.upper()}")
        
        inicio = time.perf_counter()
        
        if self.motor_elegido == 'rust':
            exito = self._usar_motor_rust()
        else:
            exito = self._usar_motor_python()
        
        self.metricas['tiempo_generacion'] = time.perf_counter() - inicio
        self.metricas['motor_usado'] = self.motor_elegido
        
        if exito and self.dataset is not None:
            if hasattr(self.dataset, '__len__'):
                self.metricas['registros_generados'] = len(self.dataset)
            else:
                self.metricas['registros_generados'] = self.volumen
        
        return exito
    
    def _usar_motor_python(self) -> bool:
        """Invoca MotorFaker.py"""
        try:
            # CORREGIDO: Importación con nombres correctos
            from process.motorfaker import generar_con_faker
            
            logger.info("🐍 [PYTHON] Generando con Faker...")
            
            self.dataset = generar_con_faker(self.volumen, self.columnas)
            
            if self.dataset is None:
                logger.error("❌ Motor Python retornó None")
                return False
            
            if hasattr(self.dataset, '__len__') and len(self.dataset) == 0:
                logger.warning("⚠️ Dataset vacío")
                return False
            
            logger.info(f"✅ [PYTHON] Generados {len(self.dataset)} registros")
            return True
            
        except ImportError as e:
            logger.error(f"❌ No se encontró 'process.MotorFaker': {e}")
            logger.info("   📁 Debes crear: process/MotorFaker.py")
            logger.info("   📝 Debe contener: def generar_con_faker(volumen, columnas)")
            return False
        except Exception as e:
            logger.error(f"💥 Error en motor Python: {e}")
            return False
    
    def _usar_motor_rust(self) -> bool:
        """Invoca motor Rust (placeholder)"""
        try:
            import process.motorrust  # Este módulo debe ser creado por el usuario
            
            logger.info("🦀 [RUST] Generando con motor nativo...")
            
            if hasattr(motorrust, 'generar_masivo'):
                self.dataset = motorrust.generar_masivo(self.volumen, self.columnas)
            elif hasattr(motorrust, 'generar_con_faker'):
                self.dataset = motorrust.generar_con_faker(self.volumen, self.columnas)
            else:
                raise AttributeError("Función no encontrada")
            
            return self.dataset is not None
            
        except ImportError:
            logger.warning("🦀 Rust no disponible - Fallback a Python")
            self.motor_elegido = 'python'
            return self._usar_motor_python()
        except Exception as e:
            logger.error(f"💥 Error en motor Rust: {e}")
            return False
    
    def _fase_exportacion(self) -> bool:
        """
        DELEGA la exportación al módulo exports.
        Pipilinais NO implementa exportadores, solo los llama.
        """
        logger.info(f"💾 [EXPORTACIÓN] Formato: {self.formato_salida.upper()}")
        
        if not self.dataset:
            logger.error("❌ No hay datos para exportar")
            return False
        
        inicio = time.perf_counter()
        
        try:
            # IMPORTACIÓN DINÁMICA DEL EXPORTADOR CORRECTO
            from exports.ExportManager import exportar
            
            # Delegar completamente la exportación
            exito = exportar(
                dataset=self.dataset,
                formato=self.formato_salida,
                volumen=self.volumen,
                metadata={
                    'tiempo_generacion': self.metricas['tiempo_generacion'],
                    'motor': self.motor_elegido
                }
            )
            
            self.metricas['tiempo_exportacion'] = time.perf_counter() - inicio
            return exito
            
        except ImportError as e:
            logger.error(f"❌ No se encontró 'exports.ExportManager': {e}")
            logger.info("   📁 Debes crear: exports/ExportManager.py")
            logger.info("   📝 Debe contener: def exportar(dataset, formato, volumen, metadata)")
            return False
        except Exception as e:
            logger.error(f"💥 Error en exportación: {e}")
            self.metricas['tiempo_exportacion'] = time.perf_counter() - inicio
            return False
    
    def _mostrar_resumen(self):
        """Muestra resumen final de la ejecución"""
        logger.info("=" * 60)
        logger.info(f"✅ [PIPILINAIS] Pipeline completado")
        logger.info(f"   📊 Registros: {self.metricas['registros_generados']:,}")
        logger.info(f"   ⚙️  Motor: {self.metricas['motor_usado']}")
        logger.info(f"   ⏱️  Generación: {self.metricas['tiempo_generacion']:.2f}s")
        logger.info(f"   💾 Exportación: {self.metricas['tiempo_exportacion']:.2f}s")
        logger.info(f"   🎯 Total: {self.metricas['tiempo_total']:.2f}s")
        
        if self.metricas['registros_generados'] > 0 and self.metricas['tiempo_generacion'] > 0:
            velocidad = self.metricas['registros_generados'] / self.metricas['tiempo_generacion']
            logger.info(f"   🚀 Velocidad: {velocidad:.0f} registros/segundo")
        logger.info("=" * 60)


# ============================================================================
# PRUEBA RÁPIDA
# ============================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    config = {
        'volumen': 10,
        'columnas': ['nombre', 'email', 'edad'],
        '_motor': 'python',
        'formato': 'excel'
    }
    
    print("\n🧪 Probando Pipilinais v4.0...")
    pipeline = State(config)
    resultado = pipeline.run()
    
    if resultado and not resultado.get('error'):
        print("\n✅ Prueba exitosa!")
    else:
        print(f"\n❌ Falló: {resultado.get('error')}")