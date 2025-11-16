"""
Configuración centralizada de logging para el proyecto YouTube to Google Drive.
"""
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler


def setup_logger(name, log_level=logging.INFO):
    """
    Configura y retorna un logger con handlers para archivo y consola.

    Args:
        name (str): Nombre del logger (usualmente __name__)
        log_level (int): Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        logging.Logger: Logger configurado
    """
    # Crear directorio de logs si no existe
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # Crear logger
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Evitar duplicar handlers si ya existen
    if logger.handlers:
        return logger

    # Formato detallado para archivo
    file_formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)-8s | %(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Formato simple para consola (mantiene UX actual)
    console_formatter = logging.Formatter('%(message)s')

    # Handler para archivo con rotación (max 10MB, 5 backups)
    log_file = os.path.join(log_dir, f"{name.replace('.', '_')}_{datetime.now():%Y%m%d}.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(file_formatter)

    # Handler para consola
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)

    # Agregar handlers al logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_logger(name):
    """
    Obtiene un logger ya configurado o crea uno nuevo.

    Args:
        name (str): Nombre del logger

    Returns:
        logging.Logger: Logger configurado
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger
