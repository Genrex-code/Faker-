"""
NAHUAL - HTML Form Reader (inputs/html_form_reader.py)
Responsabilidad: Leer formularios HTML y extraer campos para generación masiva

Soporta:
- Archivos HTML locales
- URLs remotas (localhost o internet)
- Múltiples pasadas/escaneos para contenido dinámico (animaciones, JS)
- Formularios con campos ocultos que se revelan con tiempo
- Extracción de inputs, selects, textareas, checkboxes, radios
- Generación de datos masivos para stress testing
"""

import re
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urljoin, urlparse
import requests

# HTML parsing
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    logging.warning("⚠️ BeautifulSoup4 no instalado. Instala: pip install beautifulsoup4")

# Para renderizado dinámico (opcional)
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False
    logging.warning("⚠️ Selenium no instalado. Para JS dinámico, instala: pip install selenium")

logger = logging.getLogger(__name__)

# ============================================================================
# ESTRUCTURAS DE DATOS
# ============================================================================

@dataclass
class FormField:
    """Representa un campo de formulario HTML"""
    name: str
    type: str  # text, email, number, select, checkbox, radio, textarea, etc.
    id: Optional[str] = None
    placeholder: Optional[str] = None
    required: bool = False
    options: List[str] = field(default_factory=list)  # Para selects y radios
    default_value: Optional[str] = None
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    pattern: Optional[str] = None  # Regex pattern
    visible: bool = True  # Si está visible en el DOM
    parent_form_id: Optional[str] = None
    label_text: Optional[str] = None
    
    def __post_init__(self):
        if self.name:
            self.name = self.name.lower().strip()


@dataclass
class HTMLFormConfig:
    """Configuración extraída de formulario HTML"""
    volumen: int = 100
    columnas: List[str] = field(default_factory=list)
    formato: str = 'json'
    motor: str = 'python'
    
    # Metadatos del formulario
    form_action: Optional[str] = None
    form_method: str = 'GET'
    form_id: Optional[str] = None
    form_name: Optional[str] = None
    fields: List[FormField] = field(default_factory=list)
    base_url: Optional[str] = None
    
    # Para mapeo de columnas
    field_mapping: Dict[str, str] = field(default_factory=dict)
    
    def to_pipeline_config(self) -> Dict[str, Any]:
        """Convierte a formato que entiende el pipeline"""
        return {
            'volumen': self.volumen,
            'columnas': self.columnas if self.columnas else [f.name for f in self.fields],
            'formato': self.formato,
            '_motor': self.motor,
            '_metadata': {
                'fuente': 'html_form',
                'form_action': self.form_action,
                'form_method': self.form_method,
                'form_id': self.form_id,
                'total_fields': len(self.fields),
                'required_fields': sum(1 for f in self.fields if f.required),
                'field_names': [f.name for f in self.fields]
            }
        }


@dataclass
class HTMLFormOptions:
    """Opciones de configuración para el lector de formularios"""
    # Tiempo de espera entre pasadas (para animaciones/JS)
    wait_between_passes: int = 2
    # Número de pasadas/escaneos para capturar contenido dinámico
    num_passes: int = 3
    # Timeout para carga de página (segundos)
    page_load_timeout: int = 30
    # Esperar a que ciertos selectores estén presentes
    wait_for_selectors: List[str] = field(default_factory=list)
    # Usar Selenium para JS dinámico (si está disponible)
    use_selenium_dynamic: bool = True
    # Capturar campos ocultos que aparecen después
    capture_hidden_after_wait: bool = True
    # Headers personalizados para requests
    custom_headers: Dict[str, str] = field(default_factory=dict)
    # Modo headless para Selenium
    headless_mode: bool = True


# ============================================================================
# LECTOR PRINCIPAL DE FORMULARIOS HTML
# ============================================================================

class HTMLFormReader:
    """Lector de formularios HTML con soporte para contenido dinámico"""
    
    # Tipos de input soportados
    INPUT_TYPES = ['text', 'email', 'password', 'number', 'tel', 'url', 
                   'date', 'datetime-local', 'time', 'month', 'week',
                   'color', 'range', 'search', 'hidden']
    
    def __init__(self, options: Optional[HTMLFormOptions] = None):
        """
        Inicializa el lector de formularios HTML
        
        Args:
            options: Opciones de configuración (pasadas, timeouts, etc.)
        """
        self.options = options or HTMLFormOptions()
        self.soup = None
        self.driver = None
        self.html_content = None
        self.base_url = None
        self.forms_found = []
    
    def cargar_configuracion(
        self, 
        fuente: str, 
        es_url: bool = False,
        form_index: int = 0
    ) -> HTMLFormConfig:
        """
        Carga configuración desde archivo HTML o URL
        
        Args:
            fuente: Ruta del archivo o URL
            es_url: True si es URL, False si es archivo local
            form_index: Índice del formulario a usar (si hay múltiples)
        """
        logger.info(f"📖 Cargando formulario HTML desde: {fuente}")
        
        if not HAS_BS4:
            logger.error("❌ BeautifulSoup4 es requerido. Instala: pip install beautifulsoup4")
            return HTMLFormConfig()
        
        # Mostrar configuración de pasadas
        logger.info(f"   🔄 Pasadas/escaneos: {self.options.num_passes}")
        logger.info(f"   ⏱️  Espera entre pasadas: {self.options.wait_between_passes}s")
        
        # Cargar el contenido HTML
        if es_url:
            success = self._cargar_desde_url_con_pasadas(fuente)
        else:
            success = self._cargar_desde_archivo(fuente)
        
        if not success:
            logger.error("❌ No se pudo cargar el HTML")
            return HTMLFormConfig()
        
        # Extraer todos los formularios
        self.forms_found = self._extraer_todos_formularios()
        
        if not self.forms_found:
            logger.warning("⚠️ No se encontraron formularios en el HTML")
            return HTMLFormConfig()
        
        # Seleccionar formulario
        form_data = self._seleccionar_formulario(form_index)
        
        if not form_data:
            return HTMLFormConfig()
        
        # Extraer campos del formulario
        fields = self._extraer_campos_formulario(form_data['soup'])
        
        # Segunda pasada: esperar y capturar campos que aparecen después
        if self.options.capture_hidden_after_wait and es_url:
            logger.info(f"   ⏳ Esperando {self.options.wait_between_passes}s para contenido dinámico...")
            time.sleep(self.options.wait_between_passes)
            
            # Recargar o re-escrapear
            if self.driver and HAS_SELENIUM:
                # Selenium ya tiene el DOM actualizado
                more_fields = self._extraer_campos_dinamicos_selenium()
                fields.extend(more_fields)
        
        # Eliminar duplicados por nombre
        fields = self._deduplicar_campos(fields)
        
        # Construir configuración
        config = self._construir_configuracion(form_data, fields)
        
        # Mostrar resumen
        self._mostrar_resumen(config)
        
        # Interacción con usuario para ajustes
        return self._configurar_interactivo(config)
    
    def _cargar_desde_archivo(self, ruta: str) -> bool:
        """Carga HTML desde archivo local"""
        try:
            ruta_path = Path(ruta)
            
            if not ruta_path.exists():
                logger.error(f"❌ Archivo no encontrado: {ruta}")
                return False
            
            with open(ruta_path, 'r', encoding='utf-8') as f:
                self.html_content = f.read()
            
            self.soup = BeautifulSoup(self.html_content, 'html.parser')
            self.base_url = f"file://{ruta_path.absolute()}"
            
            logger.info(f"   ✅ HTML local cargado: {len(self.html_content)} caracteres")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error cargando archivo {ruta}: {e}")
            return False
    
    def _cargar_desde_url_con_pasadas(self, url: str) -> bool:
        """
        Carga HTML desde URL con múltiples pasadas para capturar contenido dinámico
        """
        # Primera pasada: requests básico
        logger.info(f"   📡 Pasada 1/{self.options.num_passes}: Carga inicial...")
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'es-MX,es;q=0.8,en;q=0.5',
                **self.options.custom_headers
            }
            
            response = requests.get(
                url,
                timeout=self.options.page_load_timeout,
                headers=headers
            )
            
            response.raise_for_status()
            self.html_content = response.text
            self.soup = BeautifulSoup(self.html_content, 'html.parser')
            self.base_url = url
            
            logger.info(f"   ✅ Pasada 1 completada: {len(self.html_content)} caracteres")
            
        except requests.RequestException as e:
            logger.warning(f"   ⚠️ Error en pasada 1: {e}")
            
            # Si falla requests y tenemos Selenium, intentamos con eso
            if self.options.use_selenium_dynamic and HAS_SELENIUM:
                return self._cargar_con_selenium(url)
            return False
        
        # Pasadas adicionales para contenido dinámico (si hay Selenium)
        if self.options.use_selenium_dynamic and HAS_SELENIUM and self.options.num_passes > 1:
            return self._cargar_con_selenium(url)
        
        return True
    
    def _cargar_con_selenium(self, url: str) -> bool:
        """Carga página con Selenium para contenido dinámico (JS, animaciones)"""
        if not HAS_SELENIUM:
            logger.warning("⚠️ Selenium no disponible para contenido dinámico")
            return True  # Al menos tenemos el contenido básico
        
        try:
            logger.info(f"   🌐 Usando Selenium para contenido dinámico...")
            
            # Configurar opciones de Chrome
            chrome_options = Options()
            if self.options.headless_mode:
                chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.get(url)
            
            # Esperar a que selectores específicos estén presentes
            for selector in self.options.wait_for_selectors:
                try:
                    WebDriverWait(self.driver, self.options.wait_between_passes).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"   ✅ Selector encontrado: {selector}")
                except:
                    logger.debug(f"   ⏳ Timeout esperando: {selector}")
            
            # Múltiples pasadas con esperas
            for pass_num in range(2, self.options.num_passes + 1):
                logger.info(f"   📡 Pasada {pass_num}/{self.options.num_passes}: Esperando contenido...")
                
                # Scroll para activar lazy loading
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                
                # Esperar para animaciones
                time.sleep(self.options.wait_between_passes)
                
                # Posible scroll adicional
                self.driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(1)
            
            # Obtener el HTML final
            self.html_content = self.driver.page_source
            self.soup = BeautifulSoup(self.html_content, 'html.parser')
            
            logger.info(f"   ✅ Selenium completado: {len(self.html_content)} caracteres")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error con Selenium: {e}")
            return False
    
    def _extraer_todos_formularios(self) -> List[Dict]:
        """Extrae todos los formularios del HTML"""
        forms = []
        
        # Buscar etiquetas <form>
        for form in self.soup.find_all('form'):
            form_data = {
                'soup': form,
                'action': form.get('action', ''),
                'method': form.get('method', 'GET').upper(),
                'id': form.get('id'),
                'name': form.get('name'),
                'fields': []
            }
            forms.append(form_data)
        
        # Si no hay formularios <form>, buscar inputs sueltos
        if not forms:
            logger.info("   No se encontraron <form>, buscando inputs sueltos...")
            inputs = self.soup.find_all(['input', 'select', 'textarea'])
            if inputs:
                form_data = {
                    'soup': None,
                    'action': '',
                    'method': 'GET',
                    'id': 'loose_inputs',
                    'name': 'loose_inputs',
                    'fields': inputs
                }
                forms.append(form_data)
        
        logger.info(f"   📋 Encontrados {len(forms)} formulario(s)")
        return forms
    
    def _seleccionar_formulario(self, index: int) -> Optional[Dict]:
        """Selecciona un formulario específico"""
        if not self.forms_found:
            return None
        
        if len(self.forms_found) == 1:
            return self.forms_found[0]
        
        print(f"\n📋 FORMULARIOS DISPONIBLES ({len(self.forms_found)}):")
        for i, form in enumerate(self.forms_found):
            action = form['action'] or '(acción no definida)'
            method = form['method']
            id_info = f" id='{form['id']}'" if form['id'] else ""
            print(f"   {i+1}. {method} {action}{id_info}")
        
        while True:
            try:
                seleccion = input(f"\n👉 Selecciona formulario (1-{len(self.forms_found)}): ").strip()
                if not seleccion:
                    return self.forms_found[0]
                idx = int(seleccion) - 1
                if 0 <= idx < len(self.forms_found):
                    return self.forms_found[idx]
                print(f"❌ Número inválido")
            except ValueError:
                print("❌ Ingresa un número válido")
    
    def _extraer_campos_formulario(self, form_soup) -> List[FormField]:
        """Extrae todos los campos de un formulario"""
        fields = []
        
        # Buscar en el formulario o en todo el documento
        search_root = form_soup if form_soup else self.soup
        
        # Inputs
        for input_tag in search_root.find_all('input'):
            field = self._parse_input_field(input_tag)
            if field and field.name:
                fields.append(field)
        
        # Selects
        for select_tag in search_root.find_all('select'):
            field = self._parse_select_field(select_tag)
            if field and field.name:
                fields.append(field)
        
        # Textareas
        for textarea_tag in search_root.find_all('textarea'):
            field = self._parse_textarea_field(textarea_tag)
            if field and field.name:
                fields.append(field)
        
        # Buttons (excepto submit)
        for button_tag in search_root.find_all('button'):
            if button_tag.get('type') != 'submit':
                field = self._parse_button_field(button_tag)
                if field and field.name:
                    fields.append(field)
        
        logger.info(f"   📝 Extraídos {len(fields)} campos del formulario")
        return fields
    
    def _extraer_campos_dinamicos_selenium(self) -> List[FormField]:
        """Extrae campos adicionales que aparecieron después de JS/animaciones"""
        if not self.driver:
            return []
        
        fields = []
        
        try:
            # Buscar inputs que no estaban visibles inicialmente
            dynamic_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input:not([type="hidden"]), select, textarea')
            
            for elem in dynamic_inputs:
                name = elem.get_attribute('name')
                if name and not self._field_exists(name):
                    field = FormField(
                        name=name,
                        type=elem.tag_name,
                        visible=elem.is_displayed(),
                        placeholder=elem.get_attribute('placeholder'),
                        required=elem.get_attribute('required') is not None
                    )
                    
                    # Para selects, capturar opciones
                    if elem.tag_name == 'select':
                        options = [opt.text for opt in elem.find_elements(By.TAG_NAME, 'option') if opt.text]
                        field.options = options
                    
                    fields.append(field)
            
            if fields:
                logger.info(f"   🎯 Capturados {len(fields)} campos dinámicos adicionales")
            
        except Exception as e:
            logger.debug(f"   Error capturando campos dinámicos: {e}")
        
        return fields
    
    def _parse_input_field(self, input_tag) -> Optional[FormField]:
        """Parsea una etiqueta <input> a FormField"""
        input_type = input_tag.get('type', 'text').lower()
        name = input_tag.get('name')
        
        if not name and input_type != 'submit':
            # Intentar obtener por id
            name = input_tag.get('id')
        
        if not name:
            return None
        
        # Saltar submit/reset/button
        if input_type in ['submit', 'reset', 'button', 'image']:
            return None
        
        field = FormField(
            name=name,
            type=input_type,
            id=input_tag.get('id'),
            placeholder=input_tag.get('placeholder'),
            required=input_tag.get('required') is not None,
            default_value=input_tag.get('value'),
            visible=input_tag.get('type') != 'hidden'
        )
        
        # Validaciones HTML5
        if input_type == 'number':
            if input_tag.get('min'):
                field.min_value = int(input_tag.get('min'))
            if input_tag.get('max'):
                field.max_value = int(input_tag.get('max'))
        elif input_type == 'range':
            field.min_value = int(input_tag.get('min', 0))
            field.max_value = int(input_tag.get('max', 100))
        
        if input_tag.get('pattern'):
            field.pattern = input_tag.get('pattern')
        
        return field
    
    def _parse_select_field(self, select_tag) -> Optional[FormField]:
        """Parsea una etiqueta <select> a FormField"""
        name = select_tag.get('name')
        if not name:
            name = select_tag.get('id')
        
        if not name:
            return None
        
        options = []
        for option in select_tag.find_all('option'):
            option_text = option.get_text(strip=True)
            if option_text:
                options.append(option_text)
        
        return FormField(
            name=name,
            type='select',
            id=select_tag.get('id'),
            required=select_tag.get('required') is not None,
            options=options,
            default_value=select_tag.get('value'),
            visible=True
        )
    
    def _parse_textarea_field(self, textarea_tag) -> Optional[FormField]:
        """Parsea una etiqueta <textarea> a FormField"""
        name = textarea_tag.get('name')
        if not name:
            name = textarea_tag.get('id')
        
        if not name:
            return None
        
        return FormField(
            name=name,
            type='textarea',
            id=textarea_tag.get('id'),
            placeholder=textarea_tag.get('placeholder'),
            required=textarea_tag.get('required') is not None,
            default_value=textarea_tag.get_text(strip=True),
            visible=True
        )
    
    def _parse_button_field(self, button_tag) -> Optional[FormField]:
        """Parsea una etiqueta <button> a FormField"""
        name = button_tag.get('name')
        if not name:
            return None
        
        return FormField(
            name=name,
            type='button',
            id=button_tag.get('id'),
            default_value=button_tag.get_text(strip=True),
            visible=True
        )
    
    def _deduplicar_campos(self, fields: List[FormField]) -> List[FormField]:
        """Elimina campos duplicados por nombre"""
        seen = set()
        unique = []
        for field in fields:
            if field.name not in seen:
                seen.add(field.name)
                unique.append(field)
        return unique
    
    def _field_exists(self, name: str) -> bool:
        """Verifica si un campo ya existe"""
        # Implementación simple, se puede mejorar
        return False
    
    def _construir_configuracion(self, form_data: Dict, fields: List[FormField]) -> HTMLFormConfig:
        """Construye el objeto de configuración"""
        return HTMLFormConfig(
            form_action=form_data.get('action', ''),
            form_method=form_data.get('method', 'GET'),
            form_id=form_data.get('id'),
            form_name=form_data.get('name'),
            fields=fields,
            base_url=self.base_url,
            columnas=[f.name for f in fields if f.type != 'button']
        )
    
    def _mostrar_resumen(self, config: HTMLFormConfig):
        """Muestra resumen del formulario encontrado"""
        print("\n" + "="*60)
        print("📊 RESUMEN DEL FORMULARIO HTML")
        print("="*60)
        
        if config.form_action:
            print(f"   🎯 Acción: {config.form_action}")
        print(f"   📌 Método: {config.form_method}")
        print(f"   📝 Campos totales: {len(config.fields)}")
        
        required = sum(1 for f in config.fields if f.required)
        print(f"   ⭐ Campos requeridos: {required}")
        
        # Clasificar por tipo
        tipos = {}
        for field in config.fields:
            tipos[field.type] = tipos.get(field.type, 0) + 1
        
        print(f"\n   📋 TIPOS DE CAMPOS:")
        for tipo, count in sorted(tipos.items()):
            print(f"      - {tipo}: {count}")
        
        # Mostrar primeros campos
        print(f"\n   🔤 PRIMEROS CAMPOS:")
        for field in config.fields[:10]:
            req = "🔴" if field.required else "⚪"
            print(f"      {req} {field.name} ({field.type})")
        if len(config.fields) > 10:
            print(f"      ... y {len(config.fields) - 10} más")
        
        print("="*60)
    
    def _configurar_interactivo(self, config: HTMLFormConfig) -> HTMLFormConfig:
        """Permite al usuario ajustar la configuración"""
        print("\n🎯 CONFIGURACIÓN PARA GENERACIÓN")
        print("-" * 40)
        
        # Preguntar si quiere usar todos los campos o seleccionar
        usar_todos = input("\n📌 ¿Usar todos los campos? (s/n, default: s): ").strip().lower()
        
        if usar_todos == 'n':
            print("\n   Campos disponibles:")
            for i, field in enumerate(config.fields, 1):
                req = " (requerido)" if field.required else ""
                print(f"      {i}. {field.name} ({field.type}){req}")
            
            seleccion = input("\n   ¿Qué campos usar? (ej: 1,3,5 o 'todos'): ").strip()
            
            if seleccion and seleccion != 'todos':
                indices = [int(x.strip()) - 1 for x in seleccion.split(',') if x.strip().isdigit()]
                config.fields = [config.fields[i] for i in indices if 0 <= i < len(config.fields)]
                config.columnas = [f.name for f in config.fields]
                print(f"   ✅ Seleccionados {len(config.fields)} campos")
        
        # Volumen
        while True:
            try:
                vol_input = input("\n📊 ¿Cuántos registros generar? (default: 100): ").strip()
                config.volumen = int(vol_input) if vol_input else 100
                if config.volumen > 0:
                    break
                print("   ❌ Debe ser mayor a 0")
            except ValueError:
                print("   ❌ Ingresa un número válido")
        
        # Formato
        print("\n💾 FORMATO DE SALIDA")
        print("   1) JSON (recomendado para APIs)")
        print("   2) CSV")
        print("   3) Excel")
        
        formato_op = input("\n👉 Elige (1-3, default: 1): ").strip() or '1'
        formatos = {'1': 'json', '2': 'csv', '3': 'excel'}
        config.formato = formatos.get(formato_op, 'json')
        
        return config
    
    def cerrar(self):
        """Cierra el driver de Selenium si está abierto"""
        if self.driver:
            self.driver.quit()
            self.driver = None


# ============================================================================
# FUNCIÓN PRINCIPAL PARA INPUT_MANAGER
# ============================================================================

def obtener_configuracion_html_form(
    fuente: Optional[str] = None,
    es_url: bool = False,
    num_passes: int = 3,
    wait_time: int = 2
) -> Dict[str, Any]:
    """
    Interfaz para integrar con input_manager.py
    
    Args:
        fuente: Ruta del archivo HTML o URL (si es None, pide interactivamente)
        es_url: True si es URL, False si es archivo local
        num_passes: Número de pasadas/escaneos (para contenido dinámico)
        wait_time: Tiempo de espera entre pasadas (segundos)
    
    Returns:
        Diccionario de configuración listo para el pipeline
    """
    options = HTMLFormOptions(
        num_passes=num_passes,
        wait_between_passes=wait_time
    )
    
    reader = HTMLFormReader(options)
    
    try:
        # Si no hay fuente, preguntar interactivamente
        if not fuente:
            print("\n" + "="*60)
            print("📋 LECTOR DE FORMULARIOS HTML")
            print("="*60)
            print("\n¿Cómo quieres cargar el formulario?")
            print("   1) Desde archivo HTML local")
            print("   2) Desde URL (localhost o internet)")
            
            opcion = input("\n👉 Elige (1-2): ").strip()
            
            if opcion == '1':
                fuente = input("📁 Ruta del archivo HTML: ").strip()
                es_url = False
            else:
                fuente = input("🌐 URL del formulario: ").strip()
                es_url = True
                if not fuente.startswith(('http://', 'https://')):
                    fuente = 'http://' + fuente
        
        config_obj = reader.cargar_configuracion(fuente, es_url)
        return config_obj.to_pipeline_config()
        
    finally:
        reader.cerrar()


# ============================================================================
# FUNCIÓN PARA RELLENAR FORMULARIOS EN MASA (STRESS TESTING)
# ============================================================================

def generar_datos_para_formulario(
    config: HTMLFormConfig,
    cantidad: int = 100
) -> List[Dict[str, Any]]:
    """
    Genera datos masivos para rellenar un formulario
    
    Args:
        config: Configuración del formulario
        cantidad: Número de conjuntos de datos a generar
    
    Returns:
        Lista de diccionarios con datos para el formulario
    """
    from faker import Faker
    import random
    
    fake = Faker('es_MX')
    resultados = []
    
    for _ in range(cantidad):
        registro = {}
        
        for field in config.fields:
            if field.type in ['text', 'search', 'url']:
                if 'email' in field.name.lower():
                    registro[field.name] = fake.email()
                elif 'nombre' in field.name.lower() or 'name' in field.name.lower():
                    registro[field.name] = fake.name()
                elif 'telefono' in field.name.lower() or 'phone' in field.name.lower():
                    registro[field.name] = fake.phone_number()
                else:
                    registro[field.name] = fake.word()
            
            elif field.type == 'email':
                registro[field.name] = fake.email()
            
            elif field.type == 'number':
                min_val = field.min_value or 0
                max_val = field.max_value or 100
                registro[field.name] = random.randint(min_val, max_val)
            
            elif field.type == 'select':
                if field.options:
                    registro[field.name] = random.choice(field.options)
                else:
                    registro[field.name] = fake.word()
            
            elif field.type == 'checkbox':
                registro[field.name] = random.choice([True, False])
            
            elif field.type == 'radio':
                if field.options:
                    registro[field.name] = random.choice(field.options)
                else:
                    registro[field.name] = fake.word()
            
            elif field.type == 'textarea':
                registro[field.name] = fake.paragraph()
            
            elif field.type == 'date':
                registro[field.name] = fake.date()
            
            else:
                registro[field.name] = fake.word()
        
        resultados.append(registro)
    
    return resultados


# ============================================================================
# PRUEBA DEL MÓDULO
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    print("\n" + "🧪"*20)
    print("   Probando HTML Form Reader")
    print("🧪"*20)
    
    # Crear HTML de ejemplo
    ejemplo_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Formulario de Prueba</title></head>
    <body>
        <form action="/submit" method="POST">
            <label>Nombre:</label>
            <input type="text" name="nombre" required>
            
            <label>Email:</label>
            <input type="email" name="email" required>
            
            <label>Edad:</label>
            <input type="number" name="edad" min="18" max="99">
            
            <label>País:</label>
            <select name="pais">
                <option>México</option>
                <option>España</option>
                <option>Argentina</option>
            </select>
            
            <label>Comentarios:</label>
            <textarea name="comentarios"></textarea>
            
            <button type="submit">Enviar</button>
        </form>
    </body>
    </html>
    """
    
    # Guardar ejemplo
    Path("configs").mkdir(exist_ok=True)
    with open("configs/formulario_ejemplo.html", "w", encoding='utf-8') as f:
        f.write(ejemplo_html)
    
    print("\n📌 Prueba con archivo HTML local")
    config = obtener_configuracion_html_form("configs/formulario_ejemplo.html", es_url=False)
    
    print(f"\n✅ Configuración obtenida:")
    print(f"   Formulario: {config.get('_metadata', {}).get('form_action', 'N/A')}")
    print(f"   Campos: {len(config.get('_metadata', {}).get('field_names', []))}")
    
    # Probar generación de datos
    print("\n📌 Generando datos de prueba para el formulario...")
    # Reconstruir config para prueba
    test_config = HTMLFormConfig(
        fields=[
            FormField(name="nombre", type="text", required=True),
            FormField(name="email", type="email", required=True),
            FormField(name="edad", type="number", min_value=18, max_value=99),
            FormField(name="pais", type="select", options=["México", "España", "Argentina"]),
            FormField(name="comentarios", type="textarea")
        ]
    )
    
    datos = generar_datos_para_formulario(test_config, 5)
    for i, registro in enumerate(datos[:3], 1):
        print(f"   Registro {i}: {registro}")
    
    print("\n✅ HTML Form Reader funcionando correctamente!")