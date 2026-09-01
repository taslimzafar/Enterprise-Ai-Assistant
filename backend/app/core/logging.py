import logging
import sys
from app.core.config import settings

def setup_logging():
    """Set up basic structured logging."""
    logger = logging.getLogger("enterprise_ai")
    
    # Avoid adding multiple handlers if setup is called multiple times
    if not logger.handlers:
        logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
        
        handler = logging.StreamHandler(sys.stdout)
        
        # Simple structured formatter (can be replaced with python-json-logger for true JSON)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        # Also configure root logger to catch all other logs minimally
        logging.basicConfig(
            level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[handler]
        )
    return logger

logger = setup_logging()
