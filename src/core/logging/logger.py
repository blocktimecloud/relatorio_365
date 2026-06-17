import logging

from core.config.settings import settings
from core.logging.formatters import LOG_FORMAT

logger = logging.getLogger("office365")


def configure_logging() -> None:
    """
    Configura o logger da aplicação com handler, formato e nível.
    Idempotente: chamar mais de uma vez não duplica handlers.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)

    # evita que as mensagens subam para o root e sejam logadas em dobro
    logger.propagate = False
