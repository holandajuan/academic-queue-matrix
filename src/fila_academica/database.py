"""SQLite local. Cada comando usa uma conexão e uma transação curta."""

import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS fila_espera (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (room_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_fila_sala_ordem ON fila_espera (room_id, id);

CREATE TABLE IF NOT EXISTS atendimentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('ativo', 'finalizado')),
    CHECK ((status = 'ativo' AND finished_at IS NULL)
        OR (status = 'finalizado' AND finished_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_atendimento_ativo_sala
    ON atendimentos (room_id) WHERE status = 'ativo';

CREATE TABLE IF NOT EXISTS eventos_processados (
    event_id TEXT PRIMARY KEY NOT NULL,
    room_id TEXT NOT NULL,
    processed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + "\nCOMMIT;")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
