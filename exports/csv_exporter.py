"""
NAHUAL - CSV Exporter (exports/csv_exporter.py)
Responsabilidad: Exportar a CSV con múltiples opciones
"""

import logging
from pathlib import Path
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)


def exportar_csv(
    dataset: dict, 
    volumen: int, 
    ruta: str = None,
    delimiter: str = ',',
    encoding: str = 'utf-8-sig'
) -> bool:
    """
    Exporta dataset a CSV
    
    Args:
        dataset: Diccionario con los datos
        volumen: Número de registros
        ruta: Ruta de destino (opcional)
        delimiter: Separador de columnas (default: ',')
        encoding: Codificación (default: 'utf-8-sig')
    """
    try:
        output_dir = Path("outputs")
        output_dir.mkdir(exist_ok=True)
        
        if not ruta:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ruta = output_dir / f"nahual_datos_{timestamp}.csv"
        else:
            ruta = Path(ruta)
        
        df = pd.DataFrame(dataset)
        df.to_csv(ruta, index=False, encoding=encoding, sep=delimiter)
        
        logger.info(f"✅ CSV guardado: {ruta}")
        logger.info(f"   📊 {volumen:,} filas × {len(dataset)} columnas")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error exportando a CSV: {e}")
        return False


def exportar_csv_excel_compatible(dataset: dict, volumen: int, ruta: str = None) -> bool:
    """Exporta CSV compatible con Excel (separador punto y coma)"""
    return exportar_csv(dataset, volumen, ruta, delimiter=';')