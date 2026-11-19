"""Regras independentes do Matrix; use dentro de Database.transaction()."""

import sqlite3
from dataclasses import dataclass


class QueueError(ValueError):
    """Regra de negócio recusou a operação; mensagem pronta para o usuário."""


@dataclass(frozen=True)
class QueueStatus:
    active_user: str | None
    waiting_count: int


class QueueService:
    """O chamador controla a transação, incluindo o registro do evento recebido."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def waiting(self, room_id: str) -> list[str]:
        rows = self.connection.execute(
            "SELECT user_id FROM fila_espera WHERE room_id = ? ORDER BY id",
            (room_id,),
        )
        return [row["user_id"] for row in rows]

    def active(self, room_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT user_id FROM atendimentos WHERE room_id = ? AND status = 'ativo'",
            (room_id,),
        ).fetchone()
        return row["user_id"] if row else None

    def position(self, room_id: str, user_id: str) -> int | None:
        row = self.connection.execute(
            """SELECT COUNT(*) AS position FROM fila_espera
               WHERE room_id = ? AND id <= (
                   SELECT id FROM fila_espera WHERE room_id = ? AND user_id = ?
               )""",
            (room_id, room_id, user_id),
        ).fetchone()
        return row["position"] or None

    def join(self, room_id: str, user_id: str) -> int:
        if self.active(room_id) == user_id:
            raise QueueError("Você já está em atendimento.")
        if self.position(room_id, user_id) is not None:
            raise QueueError("Você já está na fila de espera.")
        self.connection.execute(
            "INSERT INTO fila_espera (room_id, user_id) VALUES (?, ?)",
            (room_id, user_id),
        )
        position = self.position(room_id, user_id)
        assert position is not None
        return position

    def leave(self, room_id: str, user_id: str) -> None:
        if self.active(room_id) == user_id:
            raise QueueError("Você está em atendimento. Aguarde o professor finalizar.")
        result = self.connection.execute(
            "DELETE FROM fila_espera WHERE room_id = ? AND user_id = ?",
            (room_id, user_id),
        )
        if result.rowcount == 0:
            raise QueueError("Você não está na fila de espera.")

    def call_next(self, room_id: str) -> str:
        if self.active(room_id) is not None:
            raise QueueError("Há um atendimento ativo. Use !finalizar antes de !proximo.")
        row = self.connection.execute(
            "SELECT id, user_id FROM fila_espera WHERE room_id = ? ORDER BY id LIMIT 1",
            (room_id,),
        ).fetchone()
        if row is None:
            raise QueueError("A fila está vazia.")
        self.connection.execute("DELETE FROM fila_espera WHERE id = ?", (row["id"],))
        self.connection.execute(
            "INSERT INTO atendimentos (room_id, user_id, status) VALUES (?, ?, 'ativo')",
            (room_id, row["user_id"]),
        )
        return row["user_id"]

    def finish(self, room_id: str) -> str:
        user_id = self.active(room_id)
        if user_id is None:
            raise QueueError("Não há atendimento ativo.")
        self.connection.execute(
            """UPDATE atendimentos SET status = 'finalizado',
               finished_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
               WHERE room_id = ? AND status = 'ativo'""",
            (room_id,),
        )
        return user_id

    def status(self, room_id: str) -> QueueStatus:
        row = self.connection.execute(
            "SELECT COUNT(*) AS total FROM fila_espera WHERE room_id = ?", (room_id,)
        ).fetchone()
        return QueueStatus(self.active(room_id), row["total"])
