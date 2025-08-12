import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set the log level to the highest level to capture

# Add a handler if there isn't one already
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
