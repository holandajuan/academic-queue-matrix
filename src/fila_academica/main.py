"""Execute com python -m fila_academica.main ou fila-academica."""

import asyncio
import logging
import sqlite3

from .command_handler import CommandHandler
from .config import ConfigError, load_config
from .database import Database
from .matrix_client import MatrixBot, MatrixConnectionError


logger = logging.getLogger(__name__)


async def run() -> None:
    config = load_config()
    database = Database(config.database_path)
    await asyncio.to_thread(database.initialize)
    handler = CommandHandler(database, config.professor_ids)
    await MatrixBot(config, handler).run()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Logs do transporte podem incluir URLs com access_token; emitimos apenas logs próprios.
    logging.getLogger("nio").setLevel(logging.CRITICAL)
    logging.getLogger("aiohttp").setLevel(logging.CRITICAL)
    try:
        asyncio.run(run())
    except (ConfigError, MatrixConnectionError) as error:
        logger.error("%s", error)
        return 1
    except (sqlite3.Error, OSError) as error:
        logger.error("Falha local (%s). Confira o banco, o caminho e as permissões.", type(error).__name__)
        return 1
    except KeyboardInterrupt:
        logger.info("Bot encerrado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
