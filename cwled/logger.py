import logging
import colorlog
import sys
from widgets.qButtons import ErrorDialog
from PyQt6.QtWidgets import QApplication
from pathlib import Path
from datetime import datetime
from platformdirs import user_log_path

parentLogger=logging.getLogger('')
log_colors = {
    'DEBUG': 'cyan',
    'INFO': 'light_white',
    'WARNING': 'yellow',
    'ERROR': 'red',
    'CRITICAL': 'bold_red',
}


#CHECK_MARK = "\u2705"  # ✅
#CROSS_MARK = "\u274C"  # ❌
#WARNING_SIGN = "\u26A0"  # ⚠️
#INFO_SIGN = "\u2139"   # ℹ️
#WORKING SIGN = "\u23F3"  # ⏳
detailed_formatter = colorlog.ColoredFormatter(
    '%(log_color)s[%(name)s |%(levelname)-8s | %(asctime)s]: %(lineno)-5d:%(filename)-22s: %(message)s',
    datefmt="%Y-%m-%d %H:%M:%S", 
    log_colors=log_colors)
basic_formatter=colorlog.ColoredFormatter(
    '%(log_color)s[%(name)s |%(levelname)-8s | %(asctime)s]: %(message)s',
    datefmt="%Y-%m-%d %H:%M:%S", 
    log_colors=log_colors)

# Custom handler to apply different formatters based on log level
class LevelBasedFormatter(logging.StreamHandler):
    def __init__(self, stream =None):
        super().__init__(stream)
        self.formatters = {
            logging.DEBUG: detailed_formatter,
            logging.INFO: basic_formatter,
            logging.WARNING: basic_formatter,
            logging.ERROR: detailed_formatter,
            logging.CRITICAL: detailed_formatter,
        }

    def emit(self, record):
        formatter = self.formatters.get(record.levelno)
        self.setFormatter(formatter)
        super().emit(record)

class ErrorDialogHandler(logging.Handler):
    """Custom logging handler that shows ErrorDialog for critical and error messages."""
    
    def __init__(self, parent_window=None):
        super().__init__()
        self.parent_window = parent_window
        
    def emit(self, record):
        """Show ErrorDialog for ERROR and CRITICAL level messages."""
        if record.levelno >= logging.ERROR:
            # Format the message
            message = self.format(record)
            
            # Create and show the error dialog
            # Use QApplication.activeWindow() if no parent specified
            parent = self.parent_window or QApplication.activeWindow()
            
            # Determine dialog title based on log level
            title = "Critical Error" if record.levelno >= logging.CRITICAL else "Error"
            
            dialog = ErrorDialog(f"{title} from {record.name}", 
                               f"Logger: {record.name}\nLevel: {record.levelname}\nMessage: {message}")
            dialog.exec()


# stderr_handler = logging.StreamHandler(sys.stderr)
# stderr_handler = logging.StreamHandler()
# stderr_handler.setFormatter(formatter)
# Create the custom handler
level_based_handler = LevelBasedFormatter(stream=sys.stderr)
# level_based_handler.setLevel(logging.DEBUG)

# Create file handler to store logs
def setup_file_handler():
    """
    Set up a file handler to store logs in a log file.
    Creates log directory if it doesn't exist.
    """
    # Get platform-specific log directory
    log_dir = user_log_path(appname='cwled', ensure_exists=True)
    
    # Create log file with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'cwled_{timestamp}.log'
    
    # Create file handler
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    
    # Use detailed formatter for file (without colors)
    file_formatter = logging.Formatter(
        '[%(name)s |%(levelname)-8s | %(asctime)s]: %(lineno)-5d:%(filename)-22s: %(message)s',
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    
    parentLogger.info(f"Logging to file: {log_file}")
    
    return file_handler

# Set up file logging
file_handler = setup_file_handler()
parentLogger.addHandler(file_handler)

parentLogger.setLevel('DEBUG')
parentLogger.addHandler(level_based_handler)


# The parent logger above runs at DEBUG, and third-party libraries propagate to
# it, so their internals drown out CWLed's own messages: urllib3 logs every
# connection it opens, cwltool logs every URI it resolves, rdflib every term it
# cannot parse. Hold them at WARNING instead. A library can be raised back up
# for debugging through the usual `logLevel` configuration, e.g.
#   logLevel:
#     urllib3: DEBUG
THIRD_PARTY_LOGGERS = [
    'asyncio', 'boto3', 'botocore', 'cachecontrol', 'chardet',
    'charset_normalizer', 'coloredlogs', 'concurrent', 'cwl-upgrader',
    'cwl_utils', 'cwlformat', 'cwltool', 'filelock', 'fsspec', 'galaxy',
    'git', 'httpcore', 'httpx', 'humanfriendly', 'langchain',
    'langchain_core', 'langsmith', 'markdown', 'markdown2', 'markdownify',
    'matplotlib', 'openai', 'packaging', 'PIL', 'prov', 'pydot', 'rdflib',
    'requests', 'ruamel', 's3transfer', 'salad', 'sbpack', 'schema_salad',
    'setuptools', 'sevenbridges', 'shellescape', 'urllib3', 'watchdog',
]

THIRD_PARTY_LEVEL = 'WARNING'


def pinThirdPartyLoggers():
    """
    Hold every third-party logger at WARNING.

    Setting the level on a logger that does not exist yet still works: the
    library picks up the same logger object when it is imported later.
    Libraries that set their own level at import time undo that, though -
    `cwltool` pins itself to INFO - so this is called again from
    `CWLRunner.checkTools()`, once the in-process tools have been imported.
    """
    try:
        import data
        overrides = data.configuration.get('logLevel', {}) or {}
    except Exception:
        overrides = {}

    for name in THIRD_PARTY_LOGGERS:
        logging.getLogger(name).setLevel(overrides.get(name, THIRD_PARTY_LEVEL))


pinThirdPartyLoggers()


### add the following lines in the classes of interest
    # self.logger=logging.getLogger(self.__class__.__name__)
    # try:
    #     self.logger.setLevel(data.configuration.get('logLevel',{}).get(self.__class__.__name__, 'DEBUG'))
    # except Exception as e:
    #     self.logger.setLevel("DEBUG")


