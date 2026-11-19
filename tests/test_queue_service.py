import sqlite3

import pytest

from fila_academica.database import Database
from fila_academica.queue_service import QueueError, QueueService


ROOM = "!sala:example.org"
OTHER_ROOM = "!outra:example.org"
ANA = "@ana:example.org"
BRUNO = "@bruno:example.org"


def test_join_and_position(service):
    assert service.join(ROOM, ANA) == 1
    assert service.join(ROOM, BRUNO) == 2
    assert service.position(ROOM, ANA) == 1
    assert service.position(ROOM, BRUNO) == 2
    assert service.position(ROOM, "@ausente:example.org") is None


def test_fifo_uses_insertion_sequence_instead_of_timestamp(service):
    service.join(ROOM, BRUNO)
    service.join(ROOM, ANA)
    service.connection.execute(
        "UPDATE fila_espera SET created_at = '1900-01-01' WHERE user_id = ?", (ANA,)
    )
    assert service.waiting(ROOM) == [BRUNO, ANA]
    assert service.call_next(ROOM) == BRUNO
    service.finish(ROOM)
    assert service.call_next(ROOM) == ANA


def test_duplicate_in_waiting_and_active(service):
    service.join(ROOM, ANA)
    with pytest.raises(QueueError, match="já está na fila"):
        service.join(ROOM, ANA)
    service.call_next(ROOM)
    with pytest.raises(QueueError, match="já está em atendimento"):
        service.join(ROOM, ANA)
    assert service.waiting(ROOM) == []


def test_leave_updates_positions_and_reentry_goes_to_end(service):
    service.join(ROOM, ANA)
    service.join(ROOM, BRUNO)
    service.leave(ROOM, ANA)
    assert service.position(ROOM, BRUNO) == 1
    assert service.position(ROOM, ANA) is None
    assert service.join(ROOM, ANA) == 2


def test_leave_absent_and_active(service):
    with pytest.raises(QueueError, match="não está na fila"):
        service.leave(ROOM, ANA)
    service.join(ROOM, ANA)
    service.call_next(ROOM)
    with pytest.raises(QueueError, match="professor finalizar"):
        service.leave(ROOM, ANA)
    assert service.active(ROOM) == ANA


def test_call_next_and_finish_preserve_history(service):
    service.join(ROOM, ANA)
    assert service.call_next(ROOM) == ANA
    assert service.status(ROOM).active_user == ANA
    assert service.status(ROOM).waiting_count == 0
    assert service.finish(ROOM) == ANA
    assert service.active(ROOM) is None
    row = service.connection.execute("SELECT * FROM atendimentos").fetchone()
    assert row["status"] == "finalizado"
    assert row["started_at"] and row["finished_at"]
    assert service.join(ROOM, ANA) == 1


def test_empty_queue_and_finish_without_active(service):
    assert service.waiting(ROOM) == []
    assert service.status(ROOM).active_user is None
    with pytest.raises(QueueError, match="fila está vazia"):
        service.call_next(ROOM)
    with pytest.raises(QueueError, match="Não há atendimento"):
        service.finish(ROOM)


def test_cannot_call_another_student_while_active(service):
    service.join(ROOM, ANA)
    service.join(ROOM, BRUNO)
    service.call_next(ROOM)
    with pytest.raises(QueueError, match="atendimento ativo"):
        service.call_next(ROOM)
    assert service.active(ROOM) == ANA
    assert service.waiting(ROOM) == [BRUNO]


def test_rooms_are_independent(service):
    service.join(ROOM, ANA)
    service.join(OTHER_ROOM, ANA)
    service.join(OTHER_ROOM, BRUNO)
    service.call_next(ROOM)
    assert service.active(OTHER_ROOM) is None
    assert service.call_next(OTHER_ROOM) == ANA
    service.finish(ROOM)
    assert service.active(OTHER_ROOM) == ANA
    assert service.waiting(OTHER_ROOM) == [BRUNO]


def test_state_survives_new_database_and_service(database):
    with database.transaction() as connection:
        service = QueueService(connection)
        service.join(ROOM, ANA)
        service.join(ROOM, BRUNO)
        service.call_next(ROOM)
    reopened = Database(database.path)
    reopened.initialize()
    with reopened.transaction() as connection:
        service = QueueService(connection)
        assert service.active(ROOM) == ANA
        assert service.waiting(ROOM) == [BRUNO]
        service.finish(ROOM)
        assert service.call_next(ROOM) == BRUNO


def test_database_constraints(service):
    service.join(ROOM, ANA)
    with pytest.raises(sqlite3.IntegrityError):
        service.connection.execute(
            "INSERT INTO fila_espera (room_id, user_id) VALUES (?, ?)", (ROOM, ANA)
        )
    service.call_next(ROOM)
    with pytest.raises(sqlite3.IntegrityError):
        service.connection.execute(
            "INSERT INTO atendimentos (room_id, user_id, status) VALUES (?, ?, 'ativo')",
            (ROOM, BRUNO),
        )


def test_failed_call_rolls_back_removal(database):
    with database.transaction() as connection:
        QueueService(connection).join(ROOM, ANA)
        connection.execute("""CREATE TRIGGER fail_start BEFORE INSERT ON atendimentos
                           BEGIN SELECT RAISE(ABORT, 'falha simulada'); END""")
    with pytest.raises(sqlite3.IntegrityError), database.transaction() as connection:
        QueueService(connection).call_next(ROOM)
    with database.transaction() as connection:
        assert QueueService(connection).waiting(ROOM) == [ANA]
        assert QueueService(connection).active(ROOM) is None
