import logging
import logging.config
import json
import sys
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
            exc_info = record.exc_info
            if isinstance(exc_info, BaseException):
                exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
            elif not isinstance(exc_info, tuple) or len(exc_info) != 3:
                # A record can carry `exc_info=True` (it is what logging itself
                # accepts, and what hand-built / replayed records contain). It
                # used to reach `record.exc_info[0]` below and turn the logging
                # call into a TypeError, i.e. logging an error could crash the
                # error path. Resolve it against the live exception instead.
                exc_info = sys.exc_info()
            if exc_info and exc_info[0] is not None:
                record.structured_data['exception'] = {
                    'type': exc_info[0].__name__,
                    'message': str(exc_info[1]),
                    'traceback': traceback.format_exception(*exc_info)
                }
            else:
                # `exc_info=True` is resolved by Logger._log() against the
                # exception being handled at *logging* time. A record built by
                # hand, or replayed from a queue, keeps the bare flag, so once
                # it is formatted later there is no traceback left to attach.
                # Report that instead of dropping the field without a trace.
                record.structured_data['exception'] = {
                    'type': 'unavailable',
                    'message': 'exc_info was set but no traceback is attached to the record'
                }
        
        # Add the actual message content
        record.structured_data['message'] = record.getMessage()
        
        # If there are extra parameters, add them to structured data
        if hasattr(record, 'extra_fields'):
            record.structured_data.update(record.extra_fields)
        
        return json.dumps(record.structured_data, ensure_ascii=False, default=str)

class SimpleFormatter(logging.Formatter):
    """Human-readable log formatter used when `log_format="simple"`.

    setup_logging() documents two formats, "structured" and "simple", but only
    the structured branch had a formatter class of its own; the simple branch
    built plain ``logging.Formatter`` instances from a format string, so the
    two modes were not symmetric and callers had no formatter object to reuse
    or to configure a handler with directly.
    """

    DEFAULT_FORMAT = '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s'
    DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None):
        super().__init__(fmt or self.DEFAULT_FORMAT, datefmt or self.DEFAULT_DATE_FORMAT)

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
    
    # Ensure log directory exists
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Set default log file path
    if log_file is None and enable_file:
        log_file = os.path.join(log_dir, "openchecker.log")
    
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
            '()': SimpleFormatter
        }
        formatters['detailed'] = {
            '()': SimpleFormatter,
            'fmt': '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(funcName)s: %(message)s'
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
        error_log_file = log_file.replace('.log', '_error.log')
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
    
    try:
        logging.config.dictConfig(config)
    except Exception as exc:
        # dictConfig() raises when a handler cannot be built - an unwritable
        # log directory, a read-only or full filesystem, a locked file on
        # Windows. Losing the log file must not take the service down at
        # startup, so fall back to console output and say why.
        fallback = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {'simple': {'()': SimpleFormatter}},
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'level': log_level,
                    'formatter': 'simple',
                    'stream': 'ext://sys.stdout'
                }
            },
            'loggers': {
                '': {'handlers': ['console'], 'level': log_level, 'propagate': False},
                'openchecker': {'handlers': ['console'], 'level': log_level, 'propagate': False}
            }
        }
        logging.config.dictConfig(fallback)
        logging.getLogger('openchecker').warning(
            "Logging setup failed (%s: %s); continuing with console logging only",
            type(exc).__name__, exc)
        return

    
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