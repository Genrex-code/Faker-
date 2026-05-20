"""
NAHUAL - Export Manager (exports/ExportManager.py)
Responsabilidad: Gestionar TODAS las exportaciones delegando a especialistas
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def exportar(
    dataset: Dict[str, List[Any]],
    formato: str,
    volumen: int,
    metadata: Optional[Dict[str, Any]] = None,
    ruta: Optional[str] = None
) -> bool:
    """
    Punto único de entrada para exportar datasets.
    
    Args:
        dataset: Diccionario columna -> lista de valores
        formato: 'excel', 'csv', 'json'
        volumen: Número de registros
        metadata: Info adicional
        ruta: Ruta de destino (opcional)
    """
    logger.info(f"🚚 [EXPORT MANAGER] Exportando a {formato.upper()}...")
    
    if not dataset or len(dataset) == 0:
        logger.error("❌ Dataset vacío")
        return False
    
    # Importar exportadores según formato
    if formato == 'excel':
        from exports.excel_formatter import exportar_excel
        return exportar_excel(dataset, volumen, ruta, metadata)
    
    elif formato == 'csv':
        from exports.csv_exporter import exportar_csv
        return exportar_csv(dataset, volumen, ruta)
    
    elif formato == 'json':
        from exports.json_exporter import exportar_json
        return exportar_json(dataset, volumen, ruta)
    
    else:
        logger.error(f"❌ Formato '{formato}' no soportado")
        logger.info(f"   Formatos disponibles: excel, csv, json")
        return False