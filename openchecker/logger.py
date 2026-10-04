import logging
import logging.config
import json
import time
import functools
import os
from datetime import datetime
from typing import Optional, Dict, Any
import traceback

class StructuredFormatter(logging.Formatter):
    """Structured log formatter"""
    
    def format(self, record):
        # Add structured fields
        if not hasattr(record, 'structured_data'):
            record.structured_data = {}
        
        # Add timestamp
        record.structured_data['timestamp'] = datetime.fromtimestamp(record.created).isoformat()
        record.structured_data['level'] = record.levelname
        record.structured_data['logger'] = record.name
        record.structured_data['module'] = record.module
        record.structured_data['function'] = record.funcName
        record.structured_data['line'] = record.lineno
        
        # If there's exception info, add it to structured data
        if record.exc_info:
            record.structured_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add the actual message content
        record.structured_data['message'] = record.getMessage()
        
        # If there are extra parameters, add them to structured data
        if hasattr(record, 'extra_fields'):
            record.structured_data.update(record.extra_fields)
        
        return json.dumps(record.structured_data, ensure_ascii=False, default=str)

def get_logger(name: str = None) -> logging.Logger:
    """Get configured logger instance"""
    if name is None:
        name = __name__
    return logging.getLogger(name)

def log_performance(logger_name: str = None):
    """Performance monitoring decorator"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger(logger_name or func.__module__)
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                execution_time = (time.time() - start_time) * 1000
                logger.info(f"Function {func.__name__} completed, execution time: {execution_time:.2f}ms")
                return result
            except Exception as e:
                execution_time = (time.time() - start_time) * 1000
                logger.error(f"Function {func.__name__} failed, execution time: {execution_time:.2f}ms, error: {str(e)}", exc_info=True)
                raise
        return wrapper
    return decorator

def setup_logging(
    log_level: str = "INFO", 
    log_file: Optional[str] = None,
    log_format: str = "structured",  # "structured" or "simple"
    max_file_size: int = 10485760,  # 10MB
    backup_count: int = 5,
    enable_console: bool = True,
    enable_file: bool = True,
    log_dir: str = "logs"
) -> None:
    """
    Setup logging configuration
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Log file path
        log_format: Log format ("structured" or "simple")
        max_file_size: Maximum size of single log file (bytes)
        backup_count: Number of log files to keep
        enable_console: Whether to enable console output
        enable_file: Whether to enable file output
        log_dir: Log directory
    """
    
    # Set default log file path
    if log_file is None and enable_file:
        log_file = os.path.join(log_dir, "openchecker.log")

    # Explicit log_file paths may have a different parent than log_dir.
    if enable_file and log_file:
        parent_dir = os.path.dirname(os.path.abspath(log_file))
        os.makedirs(parent_dir, exist_ok=True)
    
    # Set log level based on environment
    env_level = os.getenv('LOG_LEVEL', log_level)
    log_level = env_level.upper()
    
    # Formatter configuration
    formatters = {}
    if log_format == "structured":
        formatters['structured'] = {
            '()': StructuredFormatter
        }
    else:
        formatters['simple'] = {
            'format': '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s'
        }
        formatters['detailed'] = {
            'format': '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(funcName)s: %(message)s'
        }
    
    # Handler configuration
    handlers = {}
    
    if enable_console:
        handlers['console'] = {
            'class': 'logging.StreamHandler',
            'level': log_level,
            'formatter': 'structured' if log_format == "structured" else 'simple',
            'stream': 'ext://sys.stdout'
        }
    
    if enable_file and log_file:
        handlers['file'] = {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': log_level,
            'formatter': 'structured' if log_format == "structured" else 'detailed',
            'filename': log_file,
            'maxBytes': max_file_size,
            'backupCount': backup_count
        }
        
        # Separate error log file
        log_stem, log_extension = os.path.splitext(log_file)
        error_log_file = log_stem + '_error' + (log_extension or '.log')
        handlers['error_file'] = {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'ERROR',
            'formatter': 'structured' if log_format == "structured" else 'detailed',
            'filename': error_log_file,
            'maxBytes': max_file_size,
            'backupCount': backup_count
        }
    
    # Complete configuration
    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': formatters,
        'handlers': handlers,
        'loggers': {
            '': {  # root logger
                'handlers': list(handlers.keys()),
                'level': log_level,
                'propagate': False
            },
            'openchecker': {  # main application logger
                'handlers': list(handlers.keys()),
                'level': log_level,
                'propagate': False
            },
            'openchecker.agent': {  # agent module
                'handlers': list(handlers.keys()),
                'level': log_level,
                'propagate': False
            },
            'openchecker.platform': {  # platform module
                'handlers': list(handlers.keys()),
                'level': log_level,
                'propagate': False
            },
            'openchecker.queue': {  # message queue module
                'handlers': list(handlers.keys()),
                'level': log_level,
                'propagate': False
            },
            # set log level for some third-party libraries
            'pika': {
                'level': 'WARNING',
                'propagate': False
            },
            'werkzeug': {
                'level': 'WARNING',
                'propagate': False
            },
            'urllib3': {
                'level': 'WARNING',
                'propagate': False
            },
            'requests': {
                'level': 'WARNING',
                'propagate': False
            },
            'flask': {
                'level': 'WARNING',
                'propagate': False
            },
            'flask_restful': {
                'level': 'WARNING',
                'propagate': False
            },
            'flask_jwt': {
                'level': 'WARNING',
                'propagate': False
            }
        }
    }
    
    logging.config.dictConfig(config)
    
    # Log configuration information
    logger = get_logger('openchecker')
    logger.info("Logging system initialized", 
               extra={'extra_fields': {
                   'log_level': log_level,
                   'log_format': log_format,
                   'log_file': log_file,
                   'enable_console': enable_console,
                   'enable_file': enable_file
               }})
