import sqlite3
from itertools import count

import pytest

from fila_academica.command_handler import CommandHandler
from fila_academica.queue_service import QueueService


ROOM = "!sala:example.org"
ANA = "@ana:example.org"
BRUNO = "@bruno:example.org"
PROFESSOR = "@professor:example.org"


@pytest.fixture
def command(handler):
    sequence = count()

    def send(body, sender=ANA, room_id=ROOM):
        return handler.handle(room_id, sender, f"$evento{next(sequence)}", body)

    return send


def test_complete_demonstration(command):
    assert "Posição: 1" in command("!entrar")
    assert "Posição: 2" in command("!entrar", BRUNO)
    assert command("!fila") == f"Fila de espera:\n1. {ANA}\n2. {BRUNO}"
    assert command("!posicao", BRUNO) == "Sua posição: 2."
    assert ANA in command("!proximo", PROFESSOR)
    assert command("!posicao") == "Você está em atendimento."
    assert command("!status") == f"Em atendimento: {ANA}. Em espera: 1."
    assert "atendimento ativo" in command("!proximo", PROFESSOR)
    assert "finalizado" in command("!finalizar", PROFESSOR)
    assert BRUNO in command("!proximo", PROFESSOR)
    command("!finalizar", PROFESSOR)
    assert command("!fila") == "A fila está vazia."
    assert command("!status") == "Em atendimento: ninguém. Em espera: 0."


@pytest.mark.parametrize("body", ["!proximo", "!finalizar"])
@pytest.mark.parametrize("sender", [ANA, "@professor:outro.org", "Professor"])
def test_teacher_permission_uses_exact_matrix_id(command, body, sender):
    command("!entrar")
    assert "Apenas professores autorizados" in command(body, sender)
    assert ANA in command("!fila")


def test_leave_and_invalid_actions(command):
    assert "não está na fila" in command("!posicao")
    assert "não está na fila" in command("!sair")
    command("!entrar")
    assert "já está na fila" in command("!entrar")
    assert command("!sair") == "Você saiu da fila de espera."
    assert "fila está vazia" in command("!proximo", PROFESSOR)
    assert "Não há atendimento ativo" in command("!finalizar", PROFESSOR)


@pytest.mark.parametrize("body", ["!ajuda", "!entrar extra", "!desconhecido", "!"])
def test_help_and_invalid_input(command, body):
    response = command(body)
    assert "!ajuda" in response or "!entrar" in response
    assert command("!fila") == "A fila está vazia."


def test_non_commands_are_not_recorded(handler, database):
    for body in ["", "olá", " !entrar"]:
        assert handler.handle(ROOM, ANA, "$normal", body) is None
    with database.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM eventos_processados").fetchone()[0] == 0


def test_idempotency_survives_handler_restart(handler, database):
    assert handler.handle(ROOM, ANA, "$entrar", "!entrar")
    assert handler.handle(ROOM, BRUNO, "$bruno", "!entrar")
    assert handler.handle(ROOM, PROFESSOR, "$chamar", "!proximo")
    assert handler.handle(ROOM, PROFESSOR, "$finalizar", "!finalizar")
    restarted = CommandHandler(database, {PROFESSOR})
    assert restarted.handle(ROOM, PROFESSOR, "$chamar", "!proximo") is None
    assert restarted.handle(ROOM, ANA, "$entrar", "!entrar") is None
    with database.transaction() as connection:
        assert QueueService(connection).active(ROOM) is None
        assert QueueService(connection).waiting(ROOM) == [BRUNO]


def test_rejected_command_is_also_idempotent(handler):
    assert "fila está vazia" in handler.handle(ROOM, PROFESSOR, "$vazia", "!proximo")
    handler.handle(ROOM, ANA, "$aluno", "!entrar")
    assert handler.handle(ROOM, PROFESSOR, "$vazia", "!proximo") is None


def test_mutation_and_event_registration_roll_back_together(handler, database):
    with database.transaction() as connection:
        connection.execute("""CREATE TRIGGER fail_join BEFORE INSERT ON fila_espera
                           BEGIN SELECT RAISE(ABORT, 'falha simulada'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        handler.handle(ROOM, ANA, "$repetir", "!entrar")
    with database.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM eventos_processados").fetchone()[0] == 0
        connection.execute("DROP TRIGGER fail_join")
    assert "Posição: 1" in handler.handle(ROOM, ANA, "$repetir", "!entrar")


def test_handler_isolates_rooms(command):
    command("!entrar")
    assert command("!fila", room_id="!outra:example.org") == "A fila está vazia."
    assert "Posição: 1" in command("!entrar", room_id="!outra:example.org")
