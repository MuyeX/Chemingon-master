from loguru import logger
from .apparatus import Apparatus
from .errors import ExperimentError, ErrorInfo, ErrorHandler
from .experiment import Experiment, JupyterUI
from .operation import Operation, VirtualOperation, VirtualDevice, PublicBlocker
from .protocol import Protocol

logger.remove()
logger.level("SUCCESS", icon="✅")
logger.level("ERROR", icon="❌")
logger.level("TRACE", icon="🔍")
