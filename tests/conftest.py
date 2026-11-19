import pytest

from fila_academica.command_handler import CommandHandler
from fila_academica.database import Database
from fila_academica.queue_service import QueueService


@pytest.fixture
def database(tmp_path):
    database = Database(tmp_path / "fila.sqlite3")
    database.initialize()
    return database


@pytest.fixture
def service(database):
    with database.transaction() as connection:
        yield QueueService(connection)


@pytest.fixture
def handler(database):
    return CommandHandler(database, {"@professor:example.org"})
