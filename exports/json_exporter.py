"""
NAHUAL - JSON Exporter (exports/json_exporter.py)
Responsabilidad: Exportar a JSON con formato legible
"""

import json
import logging
from pathlib import Path
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)


def exportar_json(dataset: dict, volumen: int, ruta: str = None, indent: int = 2) -> bool:
    """
    Exporta dataset a JSON
    
    Args:
        dataset: Diccionario con los datos
        volumen: Número de registros
        ruta: Ruta de destino (opcional)
        indent: Nivel de indentación (default: 2)
    """
    try:
        output_dir = Path("outputs")
        output_dir.mkdir(exist_ok=True)
        
        if not ruta:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ruta = output_dir / f"nahual_datos_{timestamp}.json"
        else:
            ruta = Path(ruta)
        
        # Convertir a lista de registros (formato más común para JSON)
        df = pd.DataFrame(dataset)
        registros = df.to_dict(orient='records')
        
        with open(ruta, 'w', encoding='utf-8') as f:
            json.dump(registros, f, indent=indent, ensure_ascii=False, default=str)
        
        logger.info(f"✅ JSON guardado: {ruta}")
        logger.info(f"   📊 {volumen:,} registros")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error exportando a JSON: {e}")
        return False


def exportar_json_lineas(dataset: dict, volumen: int, ruta: str = None) -> bool:
    """
    Exporta a JSON Lines (cada línea es un registro) - útil para big data
    """
    try:
        import json
        
        output_dir = Path("outputs")
        output_dir.mkdir(exist_ok=True)
        
        if not ruta:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ruta = output_dir / f"nahual_datos_{timestamp}.jsonl"
        else:
            ruta = Path(ruta)
        
        df = pd.DataFrame(dataset)
        
        with open(ruta, 'w', encoding='utf-8') as f:
            for _, row in df.iterrows():
                f.write(json.dumps(row.to_dict(), ensure_ascii=False, default=str) + '\n')
        
        logger.info(f"✅ JSON Lines guardado: {ruta}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error exportando a JSON Lines: {e}")
        return False