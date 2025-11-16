# Changelog

## [Mejoras - 2025-11-16]

### ✨ Nuevas Características

#### Logging Estructurado
- Implementado sistema de logging profesional con módulo `logger_config.py`
- Logs se guardan automáticamente en directorio `logs/` con rotación automática (max 10MB, 5 backups)
- Formato detallado en archivos: timestamp, nombre del módulo, nivel, función, línea y mensaje
- Formato simple en consola para mantener UX amigable
- Niveles de logging: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Logs persistentes para debugging y auditorías

#### Configuración Centralizada
- Nuevo módulo `config.py` con todas las constantes y parámetros configurables
- Eliminación de valores hardcodeados en el código
- Fácil personalización de:
  - Modelos de Whisper (small para DiscordToDrive, medium para LocalTranscriber)
  - Parámetros de transcripción (temperatura, beam_size, thresholds)
  - Configuración de yt-dlp (reintentos, timeouts, user agents)
  - Formatos de nombres de archivos
  - Rutas de directorios

#### Sistema de Reintentos
- Decorador `@retry_on_failure` en `utils.py` para operaciones propensas a fallos
- Implementado en `upload_file_to_drive()` con exponential backoff
- Configurable: 3 reintentos por defecto con delay de 2 segundos
- Logs detallados de cada intento de reintento

#### Módulo de Utilidades
- Nuevo archivo `utils.py` con funciones comunes reutilizables:
  - `validate_ffmpeg()`: Verifica FFmpeg al inicio
  - `validate_credentials()`: Valida credenciales de Google Drive
  - `sanitize_filename()`: Sanitiza nombres de archivos
  - `ensure_directory_exists()`: Crea directorios si no existen
  - `safe_remove_file()`: Eliminación segura de archivos
  - `clean_temp_directory()`: Limpieza de directorios temporales
  - `is_audio_file()` / `is_video_file()`: Detección de tipos de archivo
  - `format_file_size()`: Formateo legible de tamaños

### 🔧 Mejoras de Código

#### DiscordToDrive.py
- Reemplazados todos los `print()` por `logger.info/error/warning()`
- Añadida validación de dependencias al inicio (FFmpeg, credentials, config)
- Uso de configuración centralizada desde `config.py`
- Docstrings mejorados en todas las funciones con tipos de parámetros y retornos
- Manejo de errores mejorado con `exc_info=True` para tracebacks completos
- Try-catch en uploads con logs detallados de errores
- Uso de funciones de utilidad para operaciones comunes
- Contador de progreso en procesamiento de videos (1/5, 2/5, etc.)
- Mensajes de inicio y fin más informativos

#### LocalTranscriber.py
- Mismas mejoras de logging que DiscordToDrive.py
- Eliminadas funciones duplicadas (ahora usan `utils.py`)
- Validación de FFmpeg al inicio
- Uso de configuración centralizada
- Docstrings mejorados
- Contador de progreso en procesamiento de archivos

### 🛠️ Arquitectura

```
Antes:
- DiscordToDrive.py (monolítico)
- LocalTranscriber.py (monolítico)

Después:
- DiscordToDrive.py (lógica principal)
- LocalTranscriber.py (lógica principal)
- config.py (configuración centralizada)
- logger_config.py (logging estructurado)
- utils.py (funciones comunes)
```

### 📊 Beneficios

1. **Debugging Mejorado**: Logs persistentes con timestamps y contexto completo
2. **Mantenibilidad**: Configuración centralizada y código más modular
3. **Confiabilidad**: Sistema de reintentos para operaciones de red
4. **Documentación**: Docstrings completos con tipos y descripciones
5. **Validación Temprana**: Verifica dependencias antes de iniciar procesamiento
6. **Reutilización**: Funciones comunes en módulo de utilidades
7. **Escalabilidad**: Arquitectura preparada para nuevas features

### ⚙️ Variables de Entorno Soportadas

- `WHISPER_DEVICE`: 'cpu' o 'cuda' (default: 'cpu')
- `LOG_LEVEL`: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL' (default: 'INFO')

### 📝 Notas de Compatibilidad

- ✅ Totalmente compatible con versión anterior
- ✅ Sin cambios en la interfaz de usuario
- ✅ Sin cambios en formato de archivos de entrada (LinksYT.json)
- ✅ Mantiene toda la funcionalidad existente
- ✅ Logs se crean automáticamente en directorio `logs/` (ya en .gitignore)

### 🚀 Próximas Mejoras Sugeridas

- [ ] Tests unitarios con pytest
- [ ] Progress bars con tqdm
- [ ] Rate limiting para Google Drive API
- [ ] Configuración vía archivo .env
- [ ] Módulos separados para yt-dlp, whisper y drive operations
- [ ] CLI mejorado con click o typer
- [ ] Integración con `channel_drive_mapping.json`
