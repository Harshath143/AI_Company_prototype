import logging
import sys

def setup_logger(name="NeoForge"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(fmt)
        logger.addHandler(console_handler)

        # N-3: File handler — persists logs across terminal sessions
        file_handler = logging.FileHandler("neoforge.log", encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger

logger = setup_logger()
