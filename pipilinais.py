"""
NAHUAL - Pipilinais v5.0 (Orquestador Core)
CORREGIDO: Importaciones correctas, manejo de errores mejorado
"""

import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class State:
    """Orquestador Core de Nahual - Versión corregida"""
    
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
        
        if not self.columnas:
            self.metricas['error'] = "Lista de columnas vacía"
            logger.error(f"❌ {self.metricas['error']}")
            return self.metricas
        
        try:
            # FASE 1: GENERACIÓN
            if not self._fase_generacion():
                self.metricas['error'] = "Falló la generación"
                return self.metricas
            
            # FASE 2: EXPORTACIÓN
            if not self._fase_exportacion():
                self.metricas['error'] = "Falló la exportación"
                logger.warning("⚠️ Los datos se generaron pero no se guardaron")
            
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
        """Invoca MotorFaker.py - CORREGIDO"""
        try:
            # CORRECCIÓN: importación correcta
            from process.motorfaker import generar_con_faker
            
            logger.info("🐍 [PYTHON] Generando con Faker...")
            
            self.dataset = generar_con_faker(self.volumen, self.columnas)
            
            if self.dataset is None:
                logger.error("❌ Motor Python retornó None")
                return False
            
            if isinstance(self.dataset, dict) and len(self.dataset) == 0:
                logger.warning("⚠️ Dataset vacío")
                return False
            
            logger.info(f"✅ [PYTHON] Generados {len(next(iter(self.dataset.values())))} registros")
            return True
            
        except ImportError as e:
            logger.error(f"❌ No se encontró 'process.motorfaker': {e}")
            logger.info("   📁 Debes crear: process/motorfaker.py")
            logger.info("   📝 Debe contener: def generar_con_faker(volumen, columnas)")
            return False
        except Exception as e:
            logger.error(f"💥 Error en motor Python: {e}")
            return False
    
    def _usar_motor_rust(self) -> bool:
        """Invoca motor Rust (placeholder para futura implementación)"""
        logger.warning("🦀 [RUST] Motor no implementado aún - Usando Python")
        self.motor_elegido = 'python'
        return self._usar_motor_python()
    
    def _fase_exportacion(self) -> bool:
        """Delega la exportación al ExportManager"""
        logger.info(f"💾 [EXPORTACIÓN] Formato: {self.formato_salida.upper()}")
        
        if not self.dataset:
            logger.error("❌ No hay datos para exportar")
            return False
        
        inicio = time.perf_counter()
        
        try:
            from exports.ExportManager import exportar
            
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
            return False
        except Exception as e:
            logger.error(f"💥 Error en exportación: {e}")
            self.metricas['tiempo_exportacion'] = time.perf_counter() - inicio
            return False
    
    def _mostrar_resumen(self):
        """Muestra resumen final"""
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    config = {
        'volumen': 10,
        'columnas': ['nombre', 'email', 'edad'],
        '_motor': 'python',
        'formato': 'excel'
    }
    
    print("\n🧪 Probando Pipilinais v5.0...")
    pipeline = State(config)
    resultado = pipeline.run()
    
    if resultado and not resultado.get('error'):
        print("\n✅ Prueba exitosa!")
    else:
        print(f"\n❌ Falló: {resultado.get('error')}")