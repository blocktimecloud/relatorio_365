import sys
from core.logging.logger import logger, configure_logging
from core.config.settings import settings


def initialize() -> None:
    configure_logging()
    logger.info(f"Iniciando {settings.app_name} [{settings.environment}]")

    # Verifica conexão com o banco antes de começar
    from core.database import check_connection
    if not check_connection():
        logger.error("Não foi possível conectar ao banco de dados. Verifique o .env.")
        sys.exit(1)

    logger.info(f"Banco conectado: {settings.db_host}:{settings.db_port}/{settings.db_name}")