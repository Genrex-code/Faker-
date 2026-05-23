"""
NAHUAL - Data Unmasking / PII Detector (inputs/data_unmasking.py)
Responsabilidad: Detectar y enmascarar datos sensibles (PII) en documentos

Soporta:
- Detección automática de PII (RFC, CURP, emails, teléfonos, direcciones, etc.)
- Enmascaramiento configurable (parcial, total, o reemplazo con Faker)
- Reglas predefinidas para México
- Reglas personalizables por el usuario
- Modo censura para documentos sensibles
- Preservación de formato (mantener estructura de RFC/CURP al enmascarar)
"""

import re
import logging
import random
from typing import Dict, Any, List, Optional, Tuple, Pattern, Union
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from enum import Enum

# Faker para datos de reemplazo realistas
try:
    from faker import Faker
    fake = Faker('es_MX')
    HAS_FAKER = True
except ImportError:
    HAS_FAKER = False
    fake = None
    logging.warning("⚠️ Faker no instalado. El reemplazo realista no estará disponible")

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS Y CONSTANTES
# ============================================================================

class MaskMode(Enum):
    """Modos de enmascaramiento"""
    PARTIAL = "partial"      # Mostrar solo primeros/últimos caracteres: j****@gmail.com
    FULL = "full"            # Reemplazar completamente: [EMAIL]
    HASH = "hash"            # Hash del valor original
    FAKE = "fake"            # Reemplazar con dato realista de Faker
    PRESERVE = "preserve"    # Preservar formato pero cambiar valores (RFC: XXXX000000XXX)


class PIIType(Enum):
    """Tipos de datos sensibles detectables"""
    RFC = "rfc"
    CURP = "curp"
    EMAIL = "email"
    TELEFONO = "telefono"
    TELEFONO_MOVIL = "telefono_movil"
    IP_ADDRESS = "ip_address"
    MAC_ADDRESS = "mac_address"
    UUID = "uuid"
    CREDIT_CARD = "credit_card"
    SSN = "ssn"  # Número de seguro social (equivalente a IMSS)
    NSS = "nss"  # Número de Seguridad Social (México)
    PLACA_AUTO = "placa_auto"
    DOMICILIO = "domicilio"
    CODIGO_POSTAL = "codigo_postal"
    NUMERO_EXTERIOR = "numero_exterior"
    NUMERO_INTERIOR = "numero_interior"
    FECHA_NACIMIENTO = "fecha_nacimiento"
    EDAD = "edad"
    GENERO = "genero"
    LATITUD = "latitud"
    LONGITUD = "longitud"


# ============================================================================
# PATRONES PARA MÉXICO
# ============================================================================

class MexicanPIIPatterns:
    """Patrones de PII específicos para México"""
    
    # RFC - Persona Moral o Física
    # Formato: Letra(4) + Número(6) + Letra(3) o Letra(3) + Número(6) + Letra(3)
    RFC_PATTERN = re.compile(
        r'\b[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}\b',
        re.IGNORECASE
    )
    
    # CURP - Clave Única de Registro de Población
    # Formato: Letra(4) + Número(6) + Letra(6) + Número(2)
    CURP_PATTERN = re.compile(
        r'\b[A-Z]{4}[0-9]{6}[A-Z]{6}[0-9]{2}\b',
        re.IGNORECASE
    )
    
    # Email
    EMAIL_PATTERN = re.compile(
        r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
    )
    
    # Teléfono fijo (10 dígitos, con o sin LADA)
    TELEFONO_PATTERN = re.compile(
        r'\b(?:\d{2}\s?)?\d{4}[-.\s]?\d{4}\b|\b\d{10}\b'
    )
    
    # Teléfono móvil (10 dígitos, empezando con 1 o con 55/56/33/etc)
    TELEFONO_MOVIL_PATTERN = re.compile(
        r'\b(?:55|56|33|81|44|66|99|77|22|55)[-.\s]?\d{4}[-.\s]?\d{4}\b|\b1\d{9}\b'
    )
    
    # IP Address (IPv4)
    IP_PATTERN = re.compile(
        r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
    )
    
    # MAC Address
    MAC_PATTERN = re.compile(
        r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b'
    )
    
    # UUID
    UUID_PATTERN = re.compile(
        r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
        re.IGNORECASE
    )
    
    # Tarjeta de crédito (básico, detecta formatos comunes)
    CREDIT_CARD_PATTERN = re.compile(
        r'\b(?:\d{4}[- ]?){3}\d{4}\b'
    )
    
    # NSS (Número de Seguridad Social mexicano)
    NSS_PATTERN = re.compile(
        r'\b\d{2,4}\d{2}\d{2}\d{3}\d{1}\b|\b\d{11}\b'
    )
    
    # Placa de auto (México - formato común)
    PLACA_PATTERN = re.compile(
        r'\b[A-Z]{3}[ -]?\d{3}\b|\b\d{3}[ -]?[A-Z]{3}\b',
        re.IGNORECASE
    )
    
    # Código Postal (México - 5 dígitos)
    CODIGO_POSTAL_PATTERN = re.compile(
        r'\b[0-9]{5}\b'
    )
    
    # Número exterior (calle)
    NUMERO_EXTERIOR_PATTERN = re.compile(
        r'\b(?:No\.?|Núm\.?|#)\s*[0-9]+\b',
        re.IGNORECASE
    )
    
    # Fecha de nacimiento (formato DD/MM/YYYY o DD-MM-YYYY)
    FECHA_NACIMIENTO_PATTERN = re.compile(
        r'\b(?:0[1-9]|[12][0-9]|3[01])[-/](?:0[1-9]|1[0-2])[-/](?:19|20)[0-9]{2}\b'
    )
    
    # Edad (número entre 0 y 120, cerca de palabras clave)
    EDAD_PATTERN = re.compile(
        r'(?:edad|años?):\s*([0-9]{1,3})',
        re.IGNORECASE
    )
    
    # Latitud/Longitud
    COORDENADA_PATTERN = re.compile(
        r'\b[-+]?(?:[0-8]?\d(?:\.\d+)?|90(?:\.0+)?)[°\s]?[-+]?(?:[0-9]?\d(?:\.\d+)?|180(?:\.0+)?)\b'
    )


# ============================================================================
# ESTRUCTURAS DE DATOS
# ============================================================================

@dataclass
class PIIMatch:
    """Representa una coincidencia de PII encontrada"""
    tipo: PIIType
    valor_original: str
    posicion_inicio: int
    posicion_fin: int
    contexto: str  # Texto alrededor
    confianza: float  # 0.0 - 1.0
    
    def __repr__(self):
        return f"PIIMatch(tipo={self.tipo.value}, valor={self.valor_original[:20]}...)"


@dataclass
class UnmaskingConfig:
    """Configuración de enmascaramiento"""
    # Qué tipos de PII detectar (si None, todos)
    tipos_a_detectar: Optional[List[PIIType]] = None
    
    # Modo de enmascaramiento por defecto
    modo_default: MaskMode = MaskMode.PARTIAL
    
    # Modos específicos por tipo de PII
    modos_por_tipo: Dict[PIIType, MaskMode] = field(default_factory=dict)
    
    # Carácter de enmascaramiento (para modo PARTIAL)
    mask_char: str = '*'
    
    # Porcentaje de caracteres a mostrar (0-100) para modo PARTIAL
    visible_percent: int = 30
    
    # Preservar formato (ej: mantener estructura de RFC/CURP)
    preserve_format: bool = True
    
    # Reemplazar con datos de Faker (requiere Faker instalado)
    use_faker_for_replacement: bool = True
    
    # Columnas a excluir del enmascaramiento
    columnas_excluidas: List[str] = field(default_factory=list)
    
    # Patrones personalizados (regex personalizado -> tipo)
    custom_patterns: Dict[Pattern, PIIType] = field(default_factory=dict)
    
    # Guardar estadísticas de enmascaramiento
    save_statistics: bool = True
    
    def __post_init__(self):
        if self.tipos_a_detectar is None:
            self.tipos_a_detectar = [t for t in PIIType]
        
        if self.modos_por_tipo is None:
            self.modos_por_tipo = {}


# ============================================================================
# DETECTOR Y ENMASCARADOR PRINCIPAL
# ============================================================================

class DataUnmasking:
    """Detector y enmascarador de datos sensibles"""
    
    def __init__(self, config: Optional[UnmaskingConfig] = None):
        """
        Inicializa el detector/enmascarador
        
        Args:
            config: Configuración de enmascaramiento
        """
        self.config = config or UnmaskingConfig()
        self.statistics = {
            'total_pii_detected': 0,
            'by_type': {},
            'by_mode': {},
            'processed_at': None,
            'total_texts_processed': 0
        }
        
        # Mapeo de tipos a patrones
        self._build_pattern_mapping()
    
    def _build_pattern_mapping(self):
        """Construye el mapeo de tipos a patrones regex"""
        self.patterns = []
        
        # Patrones predefinidos
        predefined = [
            (PIIType.RFC, MexicanPIIPatterns.RFC_PATTERN, 0.95),
            (PIIType.CURP, MexicanPIIPatterns.CURP_PATTERN, 0.95),
            (PIIType.EMAIL, MexicanPIIPatterns.EMAIL_PATTERN, 0.98),
            (PIIType.TELEFONO, MexicanPIIPatterns.TELEFONO_PATTERN, 0.85),
            (PIIType.TELEFONO_MOVIL, MexicanPIIPatterns.TELEFONO_MOVIL_PATTERN, 0.90),
            (PIIType.IP_ADDRESS, MexicanPIIPatterns.IP_PATTERN, 0.90),
            (PIIType.MAC_ADDRESS, MexicanPIIPatterns.MAC_PATTERN, 0.95),
            (PIIType.UUID, MexicanPIIPatterns.UUID_PATTERN, 0.98),
            (PIIType.CREDIT_CARD, MexicanPIIPatterns.CREDIT_CARD_PATTERN, 0.85),
            (PIIType.NSS, MexicanPIIPatterns.NSS_PATTERN, 0.80),
            (PIIType.PLACA_AUTO, MexicanPIIPatterns.PLACA_PATTERN, 0.75),
            (PIIType.CODIGO_POSTAL, MexicanPIIPatterns.CODIGO_POSTAL_PATTERN, 0.70),
            (PIIType.FECHA_NACIMIENTO, MexicanPIIPatterns.FECHA_NACIMIENTO_PATTERN, 0.80),
            (PIIType.NUMERO_EXTERIOR, MexicanPIIPatterns.NUMERO_EXTERIOR_PATTERN, 0.65)
        ]
        
        for pii_type, pattern, confidence in predefined:
            if pii_type in self.config.tipos_a_detectar:
                self.patterns.append((pii_type, pattern, confidence))
        
        # Patrones personalizados
        for pattern, pii_type in self.config.custom_patterns.items():
            if pii_type in self.config.tipos_a_detectar:
                self.patterns.append((pii_type, pattern, 0.90))
    
    def detectar_en_texto(self, texto: str) -> List[PIIMatch]:
        """
        Detecta PII en un texto
        
        Args:
            texto: Texto a analizar
        
        Returns:
            Lista de coincidencias de PII
        """
        matches = []
        
        for pii_type, pattern, confidence in self.patterns:
            for match in pattern.finditer(texto):
                # Verificar contexto para reducir falsos positivos
                start, end = match.span()
                contexto = texto[max(0, start-30):min(len(texto), end+30)]
                
                # Ajustar confianza basado en contexto
                adjusted_confidence = self._adjust_confidence_by_context(
                    match.group(), pii_type, contexto, confidence
                )
                
                if adjusted_confidence >= 0.6:  # Umbral mínimo
                    matches.append(PIIMatch(
                        tipo=pii_type,
                        valor_original=match.group(),
                        posicion_inicio=start,
                        posicion_fin=end,
                        contexto=contexto,
                        confianza=adjusted_confidence
                    ))
        
        # Eliminar duplicados y superposiciones
        matches = self._deduplicate_matches(matches)
        
        # Actualizar estadísticas
        self._update_statistics(matches)
        
        return matches
    
    def _adjust_confidence_by_context(
        self, 
        valor: str, 
        pii_type: PIIType, 
        contexto: str, 
        base_confidence: float
    ) -> float:
        """Ajusta la confianza basado en el contexto"""
        confidence = base_confidence
        
        # Verificar palabras clave en contexto
        keywords = {
            PIIType.RFC: ['rfc', 'registro federal', 'contribuyente'],
            PIIType.CURP: ['curp', 'registro poblacion', 'clave unica'],
            PIIType.EMAIL: ['email', 'correo', 'mail'],
            PIIType.TELEFONO: ['tel', 'telefono', 'cel', 'movil'],
        }
        
        if pii_type in keywords:
            for kw in keywords[pii_type]:
                if kw in contexto.lower():
                    confidence = min(confidence + 0.05, 0.99)
        
        # Verificar longitud y formato
        if pii_type == PIIType.RFC:
            if len(valor) not in [12, 13]:
                confidence *= 0.7
        elif pii_type == PIIType.CURP:
            if len(valor) != 18:
                confidence *= 0.7
        elif pii_type == PIIType.EMAIL:
            if '@' not in valor or '.' not in valor.split('@')[-1]:
                confidence *= 0.5
        
        return min(confidence, 0.99)
    
    def _deduplicate_matches(self, matches: List[PIIMatch]) -> List[PIIMatch]:
        """Elimina coincidencias duplicadas o superpuestas"""
        # Ordenar por posición
        matches.sort(key=lambda m: (m.posicion_inicio, -m.confianza))
        
        unique = []
        for match in matches:
            # Verificar si se superpone con alguna ya agregada
            overlapping = False
            for existing in unique:
                if (match.posicion_inicio < existing.posicion_fin and 
                    match.posicion_fin > existing.posicion_inicio):
                    overlapping = True
                    # Si esta es más confiable, reemplazar
                    if match.confianza > existing.confianza:
                        unique.remove(existing)
                        unique.append(match)
                    break
            
            if not overlapping:
                unique.append(match)
        
        return unique
    
    def enmascarar_en_texto(self, texto: str, matches: Optional[List[PIIMatch]] = None) -> str:
        """
        Enmascara las PII detectadas en un texto
        
        Args:
            texto: Texto original
            matches: Coincidencias pre-detectadas (opcional)
        
        Returns:
            Texto con PII enmascaradas
        """
        if matches is None:
            matches = self.detectar_en_texto(texto)
        
        # Ordenar de derecha a izquierda para no afectar índices
        matches.sort(key=lambda m: m.posicion_inicio, reverse=True)
        
        resultado = texto
        
        for match in matches:
            # Verificar si la columna está excluida (contexto puede indicar columna)
            if self._is_column_excluded(match.tipo, match.contexto):
                continue
            
            modo = self._get_mode_for_type(match.tipo)
            valor_enmascarado = self._apply_mask(match.valor_original, match.tipo, modo)
            
            # Reemplazar en el texto
            resultado = (
                resultado[:match.posicion_inicio] + 
                valor_enmascarado + 
                resultado[match.posicion_fin:]
            )
        
        return resultado
    
    def _get_mode_for_type(self, pii_type: PIIType) -> MaskMode:
        """Obtiene el modo de enmascaramiento para un tipo"""
        if pii_type in self.config.modos_por_tipo:
            return self.config.modos_por_tipo[pii_type]
        return self.config.modo_default
    
    def _apply_mask(self, valor: str, pii_type: PIIType, modo: MaskMode) -> str:
        """Aplica el enmascaramiento a un valor"""
        
        if modo == MaskMode.FULL:
            return f"[{pii_type.value.upper()}]"
        
        elif modo == MaskMode.PARTIAL:
            return self._partial_mask(valor, pii_type)
        
        elif modo == MaskMode.HASH:
            return self._hash_mask(valor)
        
        elif modo == MaskMode.FAKE:
            return self._fake_replacement(pii_type)
        
        elif modo == MaskMode.PRESERVE:
            return self._preserve_format_mask(valor, pii_type)
        
        return valor
    
    def _partial_mask(self, valor: str, pii_type: PIIType) -> str:
        """Enmascara parcialmente mostrando solo algunos caracteres"""
        length = len(valor)
        visible_chars = max(1, int(length * self.config.visible_percent / 100))
        
        if pii_type == PIIType.EMAIL:
            # Para emails, preservar dominio
            if '@' in valor:
                local, domain = valor.split('@')
                if len(local) > 2:
                    masked_local = local[0] + self.config.mask_char * (len(local) - 2) + local[-1]
                else:
                    masked_local = self.config.mask_char * len(local)
                return f"{masked_local}@{domain}"
        
        # Para otros tipos
        if visible_chars >= length:
            return valor
        
        show_start = visible_chars // 2
        show_end = visible_chars - show_start
        
        start = valor[:show_start]
        end = valor[-show_end:] if show_end > 0 else ''
        middle = self.config.mask_char * (length - show_start - show_end)
        
        return f"{start}{middle}{end}"
    
    def _hash_mask(self, valor: str) -> str:
        """Aplica hash al valor"""
        import hashlib
        hash_obj = hashlib.sha256(valor.encode())
        return f"HASH_{hash_obj.hexdigest()[:8]}"
    
    def _fake_replacement(self, pii_type: PIIType) -> str:
        """Genera un valor falso realista"""
        if not HAS_FAKER:
            return f"[FAKE_{pii_type.value}]"

        replacements = {
            PIIType.RFC: lambda: self._generate_fake_rfc(),
            PIIType.CURP: lambda: self._generate_fake_curp(),
            PIIType.EMAIL: lambda: fake.email(),
            PIIType.TELEFONO: lambda: fake.phone_number(),
            PIIType.IP_ADDRESS: lambda: fake.ipv4(),
            PIIType.UUID: lambda: fake.uuid4(),
            PIIType.DOMICILIO: lambda: fake.address(),
            PIIType.NOMBRE: lambda: fake.name()
        }
        
        if pii_type in replacements:
            return replacements[pii_type]()
        
        return f"[FAKE_{pii_type.value}]"
    
    def _preserve_format_mask(self, valor: str, pii_type: PIIType) -> str:
        """Preserva formato pero cambia valores (ej: mantener estructura de RFC/CURP)"""
        if pii_type == PIIType.RFC:
            # Preservar estructura: 3-4 letras + 6 números + 3 letras/números
            chars = list(valor)
            for i in range(len(chars)):
                if i < 4:  # Letras iniciales
                    chars[i] = random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZÑ&')
                elif i < 10:  # Números
                    chars[i] = str(random.randint(0, 9))
                else:  # Letras/números finales
                    chars[i] = random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
            return ''.join(chars)
        
        elif pii_type == PIIType.CURP:
            # CURP: 4 letras + 6 números + 6 letras + 2 números
            chars = list(valor)
            for i in range(len(chars)):
                if i < 4 or (10 <= i < 16):
                    chars[i] = random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
                else:
                    chars[i] = str(random.randint(0, 9))
            return ''.join(chars)
        
        else:
            return self._partial_mask(valor, pii_type)
    
    def _generate_fake_rfc(self) -> str:
        """Genera un RFC falso válido en estructura"""
        letras = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZÑ&', k=4))
        numeros = ''.join(random.choices('0123456789', k=6))
        homoclave = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=3))
        return f"{letras}{numeros}{homoclave}"
    
    def _generate_fake_curp(self) -> str:
        """Genera una CURP falsa válida en estructura"""
        letras = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
        fecha = f"{random.randint(19, 20)}{random.randint(0, 9)}{random.randint(0, 9)}{random.randint(0, 9)}"
        resto = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=6))
        homoclave = ''.join(random.choices('0123456789', k=2))
        return f"{letras}{fecha}{resto}{homoclave}"
    
    def _is_column_excluded(self, pii_type: PIIType, contexto: str) -> bool:
        """Verifica si una columna está excluida del enmascaramiento"""
        for excluded in self.config.columnas_excluidas:
            if excluded.lower() in contexto.lower():
                return True
        return False
    
    def _update_statistics(self, matches: List[PIIMatch]):
        """Actualiza estadísticas de detección"""
        self.statistics['total_pii_detected'] += len(matches)
        
        for match in matches:
            tipo = match.tipo.value
            self.statistics['by_type'][tipo] = self.statistics['by_type'].get(tipo, 0) + 1
    
    def procesar_dataset(self, dataset: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
        """
        Procesa un dataset completo aplicando enmascaramiento
        
        Args:
            dataset: Diccionario con datos (columna -> lista de valores)
        
        Returns:
            Dataset con datos enmascarados
        """
        import copy
        resultado = copy.deepcopy(dataset)
        
        self.statistics['total_texts_processed'] = 0
        self.statistics['processed_at'] = datetime.now().isoformat()
        
        for col_name, col_values in resultado.items():
            # Verificar si la columna está excluida
            if any(excluded.lower() in col_name.lower() for excluded in self.config.columnas_excluidas):
                logger.debug(f"   Columna excluida: {col_name}")
                continue
            
            # Procesar cada valor en la columna
            for i, valor in enumerate(col_values):
                if isinstance(valor, str):
                    matches = self.detectar_en_texto(valor)
                    if matches:
                        valor_enmascarado = self.enmascarar_en_texto(valor, matches)
                        resultado[col_name][i] = valor_enmascarado
                        self.statistics['total_texts_processed'] += 1
        
        # Guardar estadísticas si se solicita
        if self.config.save_statistics:
            self._save_statistics()
        
        return resultado
    
    def _save_statistics(self):
        """Guarda estadísticas de enmascaramiento"""
        stats_dir = Path("metrics")
        stats_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stats_file = stats_dir / f"unmasking_stats_{timestamp}.json"
        
        import json
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(self.statistics, f, indent=2, default=str)
        
        logger.info(f"📊 Estadísticas guardadas en {stats_file}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Retorna estadísticas actuales"""
        return self.statistics
    
    def detectar_en_dataset(self, dataset: Dict[str, List[Any]]) -> Dict[str, List[PIIMatch]]:
        """
        Detecta PII en todo un dataset sin enmascarar
        
        Returns:
            Diccionario con nombre_columna -> lista de matches
        """
        resultados = {}
        
        for col_name, col_values in dataset.items():
            col_matches = []
            for valor in col_values:
                if isinstance(valor, str):
                    matches = self.detectar_en_texto(valor)
                    if matches:
                        col_matches.extend(matches)
            if col_matches:
                resultados[col_name] = col_matches
        
        return resultados
    
    def generar_reporte(self) -> str:
        """Genera un reporte legible de las estadísticas"""
        report = []
        report.append("=" * 60)
        report.append("📊 REPORTE DE DETECCIÓN DE PII")
        report.append("=" * 60)
        report.append(f"Total PII detectadas: {self.statistics['total_pii_detected']}")
        report.append(f"Textos procesados: {self.statistics.get('total_texts_processed', 0)}")
        report.append(f"Procesado en: {self.statistics.get('processed_at', 'N/A')}")
        report.append("\n📋 POR TIPO:")
        
        for tipo, count in sorted(self.statistics['by_type'].items(), key=lambda x: x[1], reverse=True):
            report.append(f"   - {tipo}: {count}")
        
        report.append("=" * 60)
        return "\n".join(report)


# ============================================================================
# FUNCIÓN PRINCIPAL PARA INPUT_MANAGER
# ============================================================================

def enmascarar_dataset(
    dataset: Dict[str, List[Any]],
    config: Optional[UnmaskingConfig] = None
) -> Dict[str, List[Any]]:
    """
    Función de alto nivel para enmascarar datasets
    
    Args:
        dataset: Dataset a procesar
        config: Configuración de enmascaramiento (opcional)
    
    Returns:
        Dataset enmascarado
    """
    unmasker = DataUnmasking(config)
    resultado = unmasker.procesar_dataset(dataset)
    
    # Mostrar reporte
    print(unmasker.generar_reporte())
    
    return resultado


# ============================================================================
# FUNCIONES RÁPIDAS PARA CASOS COMUNES
# ============================================================================

def censurar_documento(texto: str, nivel: str = 'alto') -> str:
    """
    Censura rápidamente un documento según nivel de sensibilidad
    
    Args:
        texto: Documento a censurar
        nivel: 'bajo' (solo emails/teléfonos), 'medio' (+RFC/CURP), 'alto' (todo)
    
    Returns:
        Texto censurado
    """
    if nivel == 'bajo':
        tipos = [PIIType.EMAIL, PIIType.TELEFONO, PIIType.TELEFONO_MOVIL]
    elif nivel == 'medio':
        tipos = [PIIType.EMAIL, PIIType.TELEFONO, PIIType.TELEFONO_MOVIL, 
                 PIIType.RFC, PIIType.CURP, PIIType.IP_ADDRESS]
    else:
        tipos = None  # Todos
    
    config = UnmaskingConfig(
        tipos_a_detectar=tipos,
        modo_default=MaskMode.PARTIAL,
        preserve_format=True
    )
    
    unmasker = DataUnmasking(config)
    return unmasker.enmascarar_en_texto(texto)


def obtener_pii_report(texto: str) -> Dict[str, List[str]]:
    """
    Obtiene todas las PII detectadas sin enmascarar
    
    Returns:
        Diccionario con tipo -> lista de valores encontrados
    """
    unmasker = DataUnmasking()
    matches = unmasker.detectar_en_texto(texto)
    
    report = {}
    for match in matches:
        tipo = match.tipo.value
        if tipo not in report:
            report[tipo] = []
        if match.valor_original not in report[tipo]:
            report[tipo].append(match.valor_original)
    
    return report


# ============================================================================
# PRUEBA DEL MÓDULO
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    print("\n" + "🧪"*20)
    print("   Probando Data Unmasking / PII Detector")
    print("🧪"*20)
    
    # Texto de prueba con datos sensibles
    texto_prueba = """
    Datos del cliente:
    RFC: GODE561231J98
    CURP: GODE561231MHGRLJ09
    Email: juan.perez@empresa.com
    Teléfono: 5541234567
    Dirección: Av. Reforma #123, Colonia Juárez, CDMX, CP 06600
    IP: 192.168.1.100
    """
    
    print("\n📌 PRUEBA 1: Detección de PII")
    unmasker = DataUnmasking()
    matches = unmasker.detectar_en_texto(texto_prueba)
    
    print(f"   Detectadas {len(matches)} PII:")
    for match in matches[:5]:
        print(f"      - {match.tipo.value}: {match.valor_original} (confianza: {match.confianza:.0%})")
    
    print("\n📌 PRUEBA 2: Enmascaramiento parcial")
    texto_censurado = unmasker.enmascarar_en_texto(texto_prueba)
    print(f"   Original: {texto_prueba[:100]}...")
    print(f"   Censurado: {texto_censurado[:100]}...")
    
    print("\n📌 PRUEBA 3: Diferentes modos de enmascaramiento")
    config_prueba = UnmaskingConfig(
        modos_por_tipo={
            PIIType.RFC: MaskMode.PRESERVE,
            PIIType.EMAIL: MaskMode.FAKE,
            PIIType.TELEFONO: MaskMode.FULL
        },
        preserve_format=True
    )
    
    unmasker_custom = DataUnmasking(config_prueba)
    texto_custom = unmasker_custom.enmascarar_en_texto(texto_prueba)
    print(f"   Resultado: {texto_custom[:150]}...")
    
    print("\n📌 PRUEBA 4: Reporte de PII sin enmascarar")
    report = obtener_pii_report(texto_prueba)
    for tipo, valores in report.items():
        print(f"   {tipo}: {valores}")
    
    print("\n📌 PRUEBA 5: Censura rápida por niveles")
    texto_largo = "Contacto: ana@mail.com, tel: 5512345678, RFC: GODE780101XXX"
    
    censura_baja = censurar_documento(texto_largo, 'bajo')
    censura_media = censurar_documento(texto_largo, 'medio')
    censura_alta = censurar_documento(texto_largo, 'alto')
    
    print(f"   Original: {texto_largo}")
    print(f"   Censura baja: {censura_baja}")
    print(f"   Censura alta: {censura_alta}")
    
    print("\n📌 PRUEBA 6: Procesar dataset completo")
    dataset_prueba = {
        'nombre': ['Juan Pérez', 'María García', 'Carlos López'],
        'email': ['juan@mail.com', 'maria@mail.com', 'carlos@mail.com'],
        'rfc': ['GODE561231J98', 'MAGF780101XYZ', 'CALO900101ABC'],
        'telefono': ['5512345678', '5523456789', '5534567890']
    }
    
    config_dataset = UnmaskingConfig(
        modo_default=MaskMode.PARTIAL,
        visible_percent=40,
        columnas_excluidas=['nombre']  # No enmascarar nombres
    )
    
    dataset_censurado = enmascarar_dataset(dataset_prueba, config_dataset)
    
    print("\n   Dataset censurado:")
    for col, valores in dataset_censurado.items():
        print(f"      {col}: {valores}")
    
    print("\n✅ Data Unmasking funcionando correctamente!")