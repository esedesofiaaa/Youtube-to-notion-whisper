"""
ErrorHandler - Manejo centralizado de errores
Responsabilidades:
- Clasificar tipos de errores
- Manejar reintentos
- Logging estructurado
- Notificaciones de errores críticos
"""

import logging
import traceback
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
import asyncio
from pathlib import Path


class ErrorSeverity(Enum):
    """Niveles de severidad de errores"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Categorías de errores del sistema"""
    CONFIGURATION = "configuration"
    NOTION_API = "notion_api"
    GOOGLE_DRIVE = "google_drive"
    YOUTUBE_DOWNLOAD = "youtube_download"
    FILE_SYSTEM = "file_system"
    PROCESSING = "processing"
    NETWORK = "network"
    VALIDATION = "validation"
    SUBPROCESS = "subprocess"


@dataclass
class ErrorInfo:
    """Información estructurada de un error"""
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    details: Optional[str] = None
    timestamp: Optional[datetime] = None
    context: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    max_retries: int = 3
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class ErrorHandler:
    """Maneja errores de forma centralizada con logging y reintentos"""
    
    def __init__(self, logger: logging.Logger, enable_notifications: bool = False):
        """
        Inicializa el manejador de errores
        
        Args:
            logger: Logger configurado para el sistema
            enable_notifications: Habilitar notificaciones externas
        """
        self.logger = logger
        self.enable_notifications = enable_notifications
        self.error_stats = {
            "total_errors": 0,
            "by_category": {},
            "by_severity": {},
            "critical_errors": []
        }
        
        # Configuración de reintentos por categoría
        self.retry_config = {
            ErrorCategory.NOTION_API: {"max_retries": 3, "base_delay": 2.0, "backoff_factor": 2.0},
            ErrorCategory.GOOGLE_DRIVE: {"max_retries": 3, "base_delay": 1.5, "backoff_factor": 2.0},
            ErrorCategory.YOUTUBE_DOWNLOAD: {"max_retries": 2, "base_delay": 5.0, "backoff_factor": 1.5},
            ErrorCategory.NETWORK: {"max_retries": 4, "base_delay": 1.0, "backoff_factor": 2.0},
            ErrorCategory.FILE_SYSTEM: {"max_retries": 2, "base_delay": 0.5, "backoff_factor": 1.0},
            ErrorCategory.SUBPROCESS: {"max_retries": 1, "base_delay": 3.0, "backoff_factor": 1.0},
            ErrorCategory.PROCESSING: {"max_retries": 1, "base_delay": 1.0, "backoff_factor": 1.0},
            ErrorCategory.CONFIGURATION: {"max_retries": 0, "base_delay": 0.0, "backoff_factor": 1.0},
            ErrorCategory.VALIDATION: {"max_retries": 0, "base_delay": 0.0, "backoff_factor": 1.0}
        }
    
    def handle_error(self, error: Exception, category: ErrorCategory, 
                    context: Optional[Dict[str, Any]] = None,
                    severity: Optional[ErrorSeverity] = None) -> ErrorInfo:
        """
        Maneja un error de forma centralizada
        
        Args:
            error: Excepción capturada
            category: Categoría del error
            context: Información contextual adicional
            severity: Severidad del error (auto-detectada si no se especifica)
            
        Returns:
            Información estructurada del error
        """
        # Auto-detectar severidad si no se especifica
        if severity is None:
            severity = self._determine_severity(error, category)
        
        # Crear información del error
        error_info = ErrorInfo(
            category=category,
            severity=severity,
            message=str(error),
            details=self._extract_error_details(error),
            context=context or {}
        )
        
        # Registrar error
        self._log_error(error_info)
        
        # Actualizar estadísticas
        self._update_error_stats(error_info)
        
        # Manejar errores críticos
        if severity == ErrorSeverity.CRITICAL:
            self._handle_critical_error(error_info)
        
        return error_info
    
    def should_retry(self, error_info: ErrorInfo) -> bool:
        """
        Determina si un error debe reintentarse
        
        Args:
            error_info: Información del error
            
        Returns:
            True si debe reintentarse
        """
        config = self.retry_config.get(error_info.category)
        if not config:
            return False
        
        return error_info.retry_count < config["max_retries"]
    
    async def retry_with_backoff(self, func: Callable, error_info: ErrorInfo, 
                               *args, **kwargs) -> Any:
        """
        Ejecuta una función con reintentos y backoff exponencial
        
        Args:
            func: Función a ejecutar
            error_info: Información del error para configurar reintentos
            *args, **kwargs: Argumentos para la función
            
        Returns:
            Resultado de la función
            
        Raises:
            Exception: Si se agotan todos los reintentos
        """
        config = self.retry_config.get(error_info.category, {})
        max_retries = config.get("max_retries", 0)
        base_delay = config.get("base_delay", 1.0)
        backoff_factor = config.get("backoff_factor", 2.0)
        
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                if attempt > 0:
                    self.logger.info(f"✅ Operación exitosa en intento {attempt + 1}")
                
                return result
                
            except Exception as e:
                last_exception = e
                error_info.retry_count = attempt
                
                if attempt < max_retries:
                    delay = base_delay * (backoff_factor ** attempt)
                    
                    self.logger.warning(
                        f"⚠️ Intento {attempt + 1}/{max_retries + 1} falló: {str(e)[:100]}..."
                    )
                    self.logger.info(f"🕐 Esperando {delay:.1f}s antes del siguiente intento")
                    
                    await asyncio.sleep(delay)
                else:
                    # Último intento fallido
                    final_error_info = self.handle_error(
                        e, error_info.category, 
                        context={"final_attempt": True, "total_attempts": attempt + 1}
                    )
                    self.logger.error(f"❌ Todos los reintentos agotados para {error_info.category.value}")
        
        # Si llegamos aquí, todos los reintentos fallaron
        raise last_exception
    
    def create_error_context(self, **kwargs) -> Dict[str, Any]:
        """
        Crea un diccionario de contexto para errores
        
        Args:
            **kwargs: Información contextual
            
        Returns:
            Diccionario de contexto normalizado
        """
        context = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "function": kwargs.get("function"),
            "file": kwargs.get("file"),
            "line": kwargs.get("line"),
            "user_data": kwargs.get("user_data", {})
        }
        
        # Añadir cualquier otra información proporcionada
        for key, value in kwargs.items():
            if key not in context:
                context[key] = value
        
        return context
    
    def log_operation_start(self, operation: str, context: Optional[Dict[str, Any]] = None):
        """Registra el inicio de una operación"""
        self.logger.info(f"🚀 Iniciando: {operation}")
        if context:
            self.logger.debug(f"📋 Contexto: {context}")
    
    def log_operation_success(self, operation: str, context: Optional[Dict[str, Any]] = None):
        """Registra el éxito de una operación"""
        self.logger.info(f"✅ Completado: {operation}")
        if context:
            self.logger.debug(f"📊 Resultado: {context}")
    
    def log_progress(self, current: int, total: int, operation: str = "Procesando"):
        """Registra progreso de operaciones largas"""
        percentage = (current / total) * 100 if total > 0 else 0
        self.logger.info(f"📈 {operation}: {current}/{total} ({percentage:.1f}%)")
    
    def _determine_severity(self, error: Exception, category: ErrorCategory) -> ErrorSeverity:
        """Determina automáticamente la severidad de un error"""
        
        # Errores críticos
        if category == ErrorCategory.CONFIGURATION:
            return ErrorSeverity.CRITICAL
        
        if isinstance(error, (MemoryError, OSError)) and "No space left" in str(error):
            return ErrorSeverity.CRITICAL
        
        # Errores de red y APIs
        if category in [ErrorCategory.NOTION_API, ErrorCategory.GOOGLE_DRIVE]:
            if "401" in str(error) or "403" in str(error):  # Auth errors
                return ErrorSeverity.CRITICAL
            elif "429" in str(error) or "500" in str(error):  # Rate limit/server errors
                return ErrorSeverity.ERROR
            else:
                return ErrorSeverity.WARNING
        
        # Errores de descarga de YouTube
        if category == ErrorCategory.YOUTUBE_DOWNLOAD:
            if "unavailable" in str(error).lower() or "private" in str(error).lower():
                return ErrorSeverity.WARNING
            else:
                return ErrorSeverity.ERROR
        
        # Errores de archivos
        if category == ErrorCategory.FILE_SYSTEM:
            if isinstance(error, PermissionError):
                return ErrorSeverity.ERROR
            elif isinstance(error, FileNotFoundError):
                return ErrorSeverity.WARNING
            else:
                return ErrorSeverity.ERROR
        
        # Por defecto
        return ErrorSeverity.ERROR
    
    def _extract_error_details(self, error: Exception) -> str:
        """Extrae detalles adicionales del error"""
        details = []
        
        # Tipo de error
        details.append(f"Tipo: {type(error).__name__}")
        
        # Traceback resumido (últimas 3 líneas)
        tb_lines = traceback.format_exc().split('\n')
        if len(tb_lines) > 4:
            relevant_lines = tb_lines[-4:-1]  # Excluir la línea vacía final
            details.append("Traceback:")
            for line in relevant_lines:
                if line.strip():
                    details.append(f"  {line.strip()}")
        
        return '\n'.join(details)
    
    def _log_error(self, error_info: ErrorInfo):
        """Registra un error en el sistema de logging"""
        
        # Mensaje principal
        log_message = f"🔴 {error_info.category.value.upper()}: {error_info.message}"
        
        # Contexto adicional
        if error_info.context:
            context_str = ", ".join([f"{k}={v}" for k, v in error_info.context.items()])
            log_message += f" | Contexto: {context_str}"
        
        # Registrar según severidad
        if error_info.severity == ErrorSeverity.CRITICAL:
            self.logger.critical(log_message)
        elif error_info.severity == ErrorSeverity.ERROR:
            self.logger.error(log_message)
        elif error_info.severity == ErrorSeverity.WARNING:
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)
        
        # Detalles adicionales en debug
        if error_info.details:
            self.logger.debug(f"📝 Detalles del error:\n{error_info.details}")
    
    def _update_error_stats(self, error_info: ErrorInfo):
        """Actualiza estadísticas de errores"""
        self.error_stats["total_errors"] += 1
        
        # Por categoría
        category_name = error_info.category.value
        if category_name not in self.error_stats["by_category"]:
            self.error_stats["by_category"][category_name] = 0
        self.error_stats["by_category"][category_name] += 1
        
        # Por severidad
        severity_name = error_info.severity.value
        if severity_name not in self.error_stats["by_severity"]:
            self.error_stats["by_severity"][severity_name] = 0
        self.error_stats["by_severity"][severity_name] += 1
        
        # Errores críticos
        if error_info.severity == ErrorSeverity.CRITICAL:
            self.error_stats["critical_errors"].append({
                "timestamp": error_info.timestamp.isoformat(),
                "category": category_name,
                "message": error_info.message
            })
    
    def _handle_critical_error(self, error_info: ErrorInfo):
        """Maneja errores críticos con notificaciones especiales"""
        
        self.logger.critical("🚨 ERROR CRÍTICO DETECTADO 🚨")
        self.logger.critical(f"Categoría: {error_info.category.value}")
        self.logger.critical(f"Mensaje: {error_info.message}")
        
        if self.enable_notifications:
            # Aquí se podrían implementar notificaciones externas
            # como webhooks, emails, etc.
            self._send_critical_notification(error_info)
    
    def _send_critical_notification(self, error_info: ErrorInfo):
        """Envía notificación de error crítico (placeholder)"""
        # Implementación futura para notificaciones
        self.logger.info("📧 Notificación crítica enviada (simulada)")
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas de errores"""
        return self.error_stats.copy()
    
    def reset_error_stats(self):
        """Reinicia estadísticas de errores"""
        self.error_stats = {
            "total_errors": 0,
            "by_category": {},
            "by_severity": {},
            "critical_errors": []
        }
        self.logger.info("📊 Estadísticas de errores reiniciadas")
    
    def print_error_summary(self):
        """Imprime un resumen de errores"""
        stats = self.error_stats
        
        print("\n" + "="*40)
        print("📊 RESUMEN DE ERRORES")
        print("="*40)
        
        print(f"📈 Total errores: {stats['total_errors']}")
        
        if stats["by_category"]:
            print("\n📂 Por categoría:")
            for category, count in stats["by_category"].items():
                print(f"   {category}: {count}")
        
        if stats["by_severity"]:
            print("\n⚠️ Por severidad:")
            for severity, count in stats["by_severity"].items():
                print(f"   {severity}: {count}")
        
        if stats["critical_errors"]:
            print(f"\n🚨 Errores críticos recientes: {len(stats['critical_errors'])}")
            for error in stats["critical_errors"][-3:]:  # Últimos 3
                timestamp = error["timestamp"][:19]  # YYYY-MM-DDTHH:MM:SS
                print(f"   {timestamp} | {error['category']} | {error['message'][:50]}...")
        
        print("="*40)


# Funciones utilitarias para uso común
def create_error_handler(logger: logging.Logger) -> ErrorHandler:
    """Crea un manejador de errores con configuración estándar"""
    return ErrorHandler(logger, enable_notifications=False)


def handle_common_exceptions(func):
    """Decorador para manejo automático de excepciones comunes"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileNotFoundError as e:
            print(f"❌ Archivo no encontrado: {e}")
            return None
        except PermissionError as e:
            print(f"❌ Error de permisos: {e}")
            return None
        except Exception as e:
            print(f"❌ Error inesperado en {func.__name__}: {e}")
            return None
    return wrapper


if __name__ == "__main__":
    # Pruebas de la clase ErrorHandler
    print("🧪 PRUEBAS DE ErrorHandler")
    print("="*40)
    
    # Configurar logger para pruebas
    import logging
    
    logger = logging.getLogger('test_error_handler')
    logger.setLevel(logging.DEBUG)
    
    # Handler para consola
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Crear error handler
    error_handler = ErrorHandler(logger)
    
    try:
        # Prueba 1: Error de configuración
        print("\n1️⃣ Simulando error de configuración...")
        try:
            raise ValueError("Token de Notion inválido")
        except Exception as e:
            error_info = error_handler.handle_error(e, ErrorCategory.CONFIGURATION)
            print(f"✅ Error manejado: {error_info.severity.value}")
        
        # Prueba 2: Error de API con reintento
        print("\n2️⃣ Simulando error de API con reintentos...")
        
        async def failing_api_call():
            raise ConnectionError("Timeout connecting to Notion API")
        
        async def test_retry():
            try:
                error_info = ErrorInfo(ErrorCategory.NOTION_API, ErrorSeverity.ERROR, "Test")
                await error_handler.retry_with_backoff(failing_api_call, error_info)
            except Exception as e:
                print(f"✅ Reintentos agotados como esperado: {type(e).__name__}")
        
        # Ejecutar prueba async
        import asyncio
        asyncio.run(test_retry())
        
        # Prueba 3: Logging de operaciones
        print("\n3️⃣ Probando logging de operaciones...")
        error_handler.log_operation_start("Extracción de videos de YouTube")
        error_handler.log_progress(5, 10, "Procesando videos")
        error_handler.log_operation_success("Extracción completada")
        
        # Prueba 4: Estadísticas
        print("\n4️⃣ Generando más errores para estadísticas...")
        for i in range(3):
            try:
                raise FileNotFoundError(f"Archivo {i} no encontrado")
            except Exception as e:
                error_handler.handle_error(e, ErrorCategory.FILE_SYSTEM)
        
        # Mostrar estadísticas
        print("\n5️⃣ Estadísticas de errores:")
        error_handler.print_error_summary()
        
        print("\n✅ ¡Todas las pruebas de ErrorHandler pasaron!")
        
    except Exception as e:
        print(f"\n❌ Error en pruebas: {e}")
        import traceback
        traceback.print_exc()