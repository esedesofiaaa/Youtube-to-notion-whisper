"""
ConfigManager - Gestión centralizada de configuración
Responsabilidades:
- Cargar variables de entorno
- Validar configuración
- Gestionar archivos de configuración
- Proveer configuración a otras clases
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
from dotenv import load_dotenv


class ConfigManager:
    """Gestiona toda la configuración del sistema YouTube Processor"""
    
    def __init__(self, env_file: str = ".env"):
        """
        Inicializa el gestor de configuración
        
        Args:
            env_file: Ruta al archivo .env
        """
        self.env_file = env_file
        self.config = {}
        self.validation_errors = []
        
        # Cargar configuración
        self._load_environment()
        self._load_config()
        self._validate_config()
        
        if self.validation_errors:
            raise ValueError(f"Errores de configuración: {', '.join(self.validation_errors)}")
    
    def _load_environment(self) -> None:
        """Carga variables de entorno desde archivo .env"""
        try:
            load_dotenv(self.env_file)
            print(f"✅ Variables de entorno cargadas desde {self.env_file}")
        except Exception as e:
            print(f"⚠️ No se pudo cargar {self.env_file}: {e}")
    
    def _load_config(self) -> None:
        """Carga toda la configuración desde variables de entorno"""
        
        # Configuración de Notion (reutilizando del Discord bot)
        self.config['notion'] = {
            'token': os.getenv('NOTION_TOKEN'),
            'database_id': os.getenv('NOTION_DATABASE_ID')
        }
        
        # Configuración de procesamiento
        self.config['processing'] = {
            'start_date': os.getenv('START_DATE', '2025-07-01'),
            'json_output_dir': os.getenv('JSON_OUTPUT_DIR', './channel_jsons/'),
            'discordtodrive_script': os.getenv('DISCORDTODRIVE_SCRIPT', './Discordtodrive.py'),
            'max_retry_attempts': int(os.getenv('MAX_RETRY_ATTEMPTS', '3')),
            'batch_size': int(os.getenv('BATCH_SIZE_PER_EXECUTION', '10')),
            'cleanup_completed': os.getenv('CLEANUP_COMPLETED_JSONS', 'true').lower() == 'true'
        }
        
        # Configuración de Google Drive
        self.config['google_drive'] = {
            'credentials_file': os.getenv('GOOGLE_DRIVE_CREDENTIALS', 'credentials.json'),
            'token_file': os.getenv('GOOGLE_DRIVE_TOKEN', 'token.json'),
            'channel_mapping_file': os.getenv('CHANNEL_MAPPING_FILE', './channel_drive_mapping.json'),
            'auto_create_folders': os.getenv('AUTO_CREATE_DRIVE_FOLDERS', 'true').lower() == 'true',
            'default_parent_folder': os.getenv('DEFAULT_DRIVE_PARENT')
        }
        
        # Configuración de logging
        self.config['logging'] = {
            'level': os.getenv('LOG_LEVEL', 'INFO'),
            'file': os.getenv('LOG_FILE', './logs/youtube_processor.log'),
            'max_bytes': int(os.getenv('LOG_MAX_BYTES', '10485760')),  # 10MB
            'backup_count': int(os.getenv('LOG_BACKUP_COUNT', '5'))
        }
        
        # Configuración de monitoreo (opcional)
        self.config['monitoring'] = {
            'enabled': os.getenv('MONITORING_ENABLED', 'false').lower() == 'true',
            'heartbeat_url': os.getenv('HEARTBEAT_URL'),
            'heartbeat_interval': int(os.getenv('HEARTBEAT_INTERVAL', '300'))
        }
    
    def _validate_config(self) -> None:
        """Valida la configuración cargada"""
        
        # Validar configuración obligatoria de Notion
        if not self.config['notion']['token']:
            self.validation_errors.append("NOTION_TOKEN es obligatorio")
        elif not (self.config['notion']['token'].startswith('secret_') or self.config['notion']['token'].startswith('ntn_')):
            self.validation_errors.append("NOTION_TOKEN debe empezar con 'secret_' o 'ntn_'")
        
        if not self.config['notion']['database_id']:
            self.validation_errors.append("NOTION_DATABASE_ID es obligatorio")
        elif len(self.config['notion']['database_id']) != 32:
            self.validation_errors.append("NOTION_DATABASE_ID debe tener 32 caracteres")
  
    
    # Resto del código igual...
        
        # Validar fecha de inicio
        try:
            datetime.strptime(self.config['processing']['start_date'], '%Y-%m-%d')
        except ValueError:
            self.validation_errors.append("START_DATE debe tener formato YYYY-MM-DD")
        
        # Validar que Discordtodrive.py existe
        script_path = Path(self.config['processing']['discordtodrive_script'])
        if not script_path.exists():
            self.validation_errors.append(f"Discordtodrive.py no encontrado en {script_path}")
        
        # Validar directorios y crear si no existen
        self._create_required_directories()
        
        # Validar archivos de Google Drive
        self._validate_google_drive_files()
        
        # Validar valores numéricos
        if self.config['processing']['max_retry_attempts'] <= 0:
            self.validation_errors.append("MAX_RETRY_ATTEMPTS debe ser mayor que 0")
        
        if self.config['processing']['batch_size'] <= 0:
            self.validation_errors.append("BATCH_SIZE_PER_EXECUTION debe ser mayor que 0")
    
    def _create_required_directories(self) -> None:
        """Crea directorios necesarios si no existen"""
        directories = [
            self.config['processing']['json_output_dir'],
            os.path.dirname(self.config['logging']['file'])
        ]
        
        for directory in directories:
            try:
                Path(directory).mkdir(parents=True, exist_ok=True)
                print(f"📁 Directorio asegurado: {directory}")
            except Exception as e:
                self.validation_errors.append(f"No se puede crear directorio {directory}: {e}")
    
    def _validate_google_drive_files(self) -> None:
        """Valida archivos de configuración de Google Drive"""
        credentials_file = self.config['google_drive']['credentials_file']
        
        # El archivo credentials.json debe existir
        if not Path(credentials_file).exists():
            self.validation_errors.append(f"Archivo de credenciales no encontrado: {credentials_file}")
        else:
            # Validar que sea un JSON válido
            try:
                with open(credentials_file, 'r') as f:
                    creds_data = json.load(f)
                if 'installed' not in creds_data and 'web' not in creds_data:
                    self.validation_errors.append(f"Formato de credenciales inválido en {credentials_file}")
            except json.JSONDecodeError:
                self.validation_errors.append(f"JSON inválido en {credentials_file}")
        
        # El archivo token.json puede no existir (se crea automáticamente)
        token_file = self.config['google_drive']['token_file']
        if Path(token_file).exists():
            try:
                with open(token_file, 'r') as f:
                    json.load(f)
                print(f"✅ Token de Google Drive encontrado: {token_file}")
            except json.JSONDecodeError:
                self.validation_errors.append(f"Token JSON inválido en {token_file}")
    
    def get(self, section: str, key: str = None) -> Any:
        """
        Obtiene valor de configuración
        
        Args:
            section: Sección de configuración (notion, processing, etc.)
            key: Clave específica (opcional, devuelve toda la sección si no se especifica)
            
        Returns:
            Valor de configuración
        """
        if section not in self.config:
            raise KeyError(f"Sección de configuración '{section}' no encontrada")
        
        if key is None:
            return self.config[section]
        
        if key not in self.config[section]:
            raise KeyError(f"Clave '{key}' no encontrada en sección '{section}'")
        
        return self.config[section][key]
    
    def get_notion_config(self) -> Dict[str, str]:
        """Obtiene configuración completa de Notion"""
        return self.config['notion']
    
    def get_processing_config(self) -> Dict[str, Any]:
        """Obtiene configuración completa de procesamiento"""
        return self.config['processing']
    
    def get_google_drive_config(self) -> Dict[str, Any]:
        """Obtiene configuración completa de Google Drive"""
        return self.config['google_drive']
    
    def get_logging_config(self) -> Dict[str, Any]:
        """Obtiene configuración completa de logging"""
        return self.config['logging']
    
    def load_channel_mapping(self) -> Dict[str, str]:
        """
        Carga el mapeo de canales a carpetas de Drive
        
        Returns:
            Diccionario con mapeo canal -> drive_folder_id
        """
        mapping_file = self.config['google_drive']['channel_mapping_file']
        
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                mapping_data = json.load(f)
            
            # Validar estructura del mapeo
            if 'mappings' not in mapping_data:
                raise ValueError("Archivo de mapeo debe contener clave 'mappings'")
            
            print(f"✅ Mapeo de canales cargado: {len(mapping_data['mappings'])} canales")
            return mapping_data['mappings']
            
        except FileNotFoundError:
            print(f"⚠️ Archivo de mapeo no encontrado: {mapping_file}")
            if self.config['google_drive']['auto_create_folders']:
                print("ℹ️ Se crearán carpetas automáticamente según sea necesario")
                return {}
            else:
                raise FileNotFoundError(f"Mapeo de canales requerido: {mapping_file}")
        
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON inválido en archivo de mapeo: {e}")
    
    def save_channel_mapping(self, mapping: Dict[str, str]) -> None:
        """
        Guarda el mapeo actualizado de canales
        
        Args:
            mapping: Diccionario con mapeo canal -> drive_folder_id
        """
        mapping_file = self.config['google_drive']['channel_mapping_file']
        
        mapping_data = {
            "mappings": mapping,
            "auto_create_folders": self.config['google_drive']['auto_create_folders'],
            "default_parent_folder": self.config['google_drive']['default_parent_folder'],
            "last_updated": datetime.now().isoformat()
        }
        
        try:
            with open(mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mapping_data, f, indent=2, ensure_ascii=False)
            print(f"✅ Mapeo de canales guardado: {mapping_file}")
        except Exception as e:
            raise IOError(f"Error guardando mapeo de canales: {e}")
    
    def setup_logging(self) -> logging.Logger:
        """
        Configura el sistema de logging
        
        Returns:
            Logger configurado
        """
        log_config = self.get_logging_config()
        
        # Configurar formato de log
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Configurar logger principal
        logger = logging.getLogger('youtube_processor')
        logger.setLevel(getattr(logging, log_config['level']))
        
        # Evitar duplicar handlers si ya están configurados
        if not logger.handlers:
            # Handler para archivo
            file_handler = logging.handlers.RotatingFileHandler(
                log_config['file'],
                maxBytes=log_config['max_bytes'],
                backupCount=log_config['backup_count']
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            
            # Handler para consola
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        print(f"✅ Logging configurado: {log_config['file']}")
        return logger
    
    def is_monitoring_enabled(self) -> bool:
        """Verifica si el monitoreo está habilitado"""
        return self.config['monitoring']['enabled']
    
    def get_monitoring_config(self) -> Dict[str, Any]:
        """Obtiene configuración de monitoreo"""
        return self.config['monitoring']
    
    def validate_runtime_config(self) -> List[str]:
        """
        Valida configuración en tiempo de ejecución
        
        Returns:
            Lista de advertencias (no errores críticos)
        """
        warnings = []
        
        # Verificar espacio en disco
        output_dir = Path(self.config['processing']['json_output_dir'])
        try:
            stat = os.statvfs(output_dir)
            free_space_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
            if free_space_gb < 1.0:  # Menos de 1GB libre
                warnings.append(f"Poco espacio libre en disco: {free_space_gb:.2f}GB")
        except:
            warnings.append("No se pudo verificar espacio en disco")
        
        # Verificar conectividad (básica)
        try:
            import urllib.request
            urllib.request.urlopen('https://api.notion.com', timeout=5)
        except:
            warnings.append("No se puede conectar a Notion API")
        
        return warnings
    
    def __str__(self) -> str:
        """Representación string de la configuración"""
        sections = list(self.config.keys())
        return f"ConfigManager(sections={sections}, valid={len(self.validation_errors)==0})"
    
    def print_config_summary(self) -> None:
        """Imprime un resumen de la configuración actual"""
        print("\n" + "="*50)
        print("📋 RESUMEN DE CONFIGURACIÓN")
        print("="*50)
        
        print(f"🔗 Notion:")
        print(f"   - Token: {'✅ Configurado' if self.config['notion']['token'] else '❌ Faltante'}")
        print(f"   - Database ID: {self.config['notion']['database_id'][:8]}...")
        
        print(f"\n⚙️ Procesamiento:")
        print(f"   - Fecha inicio: {self.config['processing']['start_date']}")
        print(f"   - Directorio JSON: {self.config['processing']['json_output_dir']}")
        print(f"   - Script: {self.config['processing']['discordtodrive_script']}")
        print(f"   - Reintentos máx: {self.config['processing']['max_retry_attempts']}")
        print(f"   - Tamaño lote: {self.config['processing']['batch_size']}")
        
        print(f"\n☁️ Google Drive:")
        print(f"   - Credenciales: {'✅ Encontradas' if Path(self.config['google_drive']['credentials_file']).exists() else '❌ Faltantes'}")
        print(f"   - Token: {'✅ Existe' if Path(self.config['google_drive']['token_file']).exists() else '⚠️ Se creará'}")
        print(f"   - Auto-crear carpetas: {'✅ Sí' if self.config['google_drive']['auto_create_folders'] else '❌ No'}")
        
        print(f"\n📝 Logging:")
        print(f"   - Nivel: {self.config['logging']['level']}")
        print(f"   - Archivo: {self.config['logging']['file']}")
        
        if self.validation_errors:
            print(f"\n❌ ERRORES DE VALIDACIÓN:")
            for error in self.validation_errors:
                print(f"   - {error}")
        else:
            print(f"\n✅ Configuración válida")
        
        print("="*50)


# Importaciones adicionales para logging
import logging.handlers


if __name__ == "__main__":
    # Prueba de la clase ConfigManager
    try:
        config = ConfigManager()
        config.print_config_summary()
        
        # Pruebas de funcionalidad
        print("\n🧪 PRUEBAS DE FUNCIONALIDAD:")
        
        # Probar obtención de configuración
        notion_config = config.get_notion_config()
        print(f"✅ Configuración Notion obtenida: {list(notion_config.keys())}")
        
        # Probar mapeo de canales
        try:
            mapping = config.load_channel_mapping()
            print(f"✅ Mapeo de canales cargado: {len(mapping)} canales")
        except:
            print("⚠️ Mapeo de canales no disponible")
        
        # Configurar logging
        logger = config.setup_logging()
        logger.info("ConfigManager inicializado correctamente")
        
        print("✅ Todas las pruebas pasaron")
        
    except Exception as e:
        print(f"❌ Error en ConfigManager: {e}")