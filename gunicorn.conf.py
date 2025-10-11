import logging
import signal

# Bind to 0.0.0.0:5000
bind = "0.0.0.0:5000"

# Worker class for async support with SocketIO
worker_class = "gevent"

# Number of workers
workers = 1

# Set log level to WARNING to suppress SIGWINCH INFO messages
loglevel = "warning"

# Custom logger class to filter out SIGWINCH messages
class FilteredGunicornLogger(logging.Logger):
    def log(self, level, msg, *args, **kwargs):
        if "Handling signal: winch" not in str(msg):
            super().log(level, msg, *args, **kwargs)

logconfig_dict = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'generic': {
            'format': '%(asctime)s [%(process)d] [%(levelname)s] %(message)s',
            'datefmt': '[%Y-%m-%d %H:%M:%S %z]',
        },
    },
    'filters': {
        'winch_filter': {
            '()': lambda: type('WinchFilter', (), {
                'filter': lambda self, record: 'Handling signal: winch' not in record.getMessage()
            })()
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'generic',
            'filters': ['winch_filter'],
            'stream': 'ext://sys.stdout'
        },
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console']
    },
    'loggers': {
        'gunicorn.error': {
            'level': 'INFO',
            'handlers': ['console'],
            'propagate': False,
        },
        'gunicorn.access': {
            'level': 'INFO',
            'handlers': ['console'],
            'propagate': False,
        }
    }
}
