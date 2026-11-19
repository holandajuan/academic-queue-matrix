"""Comandos e permissões. Nenhuma dependência do SDK Matrix."""

from collections.abc import Collection

from .database import Database
from .queue_service import QueueError, QueueService


HELP = (
    "!entrar — entrar na fila\n"
    "!sair — sair da espera\n"
    "!fila — listar a espera\n"
    "!posicao — consultar sua posição\n"
    "!status — ver atendimento e espera\n"
    "!proximo — chamar próximo (professor)\n"
    "!finalizar — finalizar atendimento (professor)\n"
    "!ajuda — listar comandos"
)
COMMANDS = {"!ajuda", "!entrar", "!sair", "!fila", "!posicao", "!proximo", "!finalizar", "!status"}


class CommandHandler:
    def __init__(self, database: Database, professor_ids: Collection[str]):
        self.database = database
        self.professor_ids = frozenset(professor_ids)

    def handle(
        self, room_id: str, sender: str, event_id: str, body: str,
        *, display_name: str | None = None,
    ) -> str | None:
        """Retorna None para mensagem comum ou evento já processado."""
        if not body.startswith("!"):
            return None
        if not event_id or not room_id or not sender:
            raise ValueError("Evento sem event_id, room_id ou sender.")
        with self.database.transaction() as connection:
            inserted = connection.execute(
                """INSERT INTO eventos_processados (event_id, room_id) VALUES (?, ?)
                   ON CONFLICT(event_id) DO NOTHING""",
                (event_id, room_id),
            )
            if inserted.rowcount == 0:
                return None
            service = QueueService(connection)
            try:
                return self._dispatch(service, room_id, sender, body, display_name)
            except QueueError as error:
                return str(error)

    def _dispatch(
        self, service: QueueService, room_id: str, sender: str, body: str,
        display_name: str | None,
    ) -> str:
        parts = body.split()
        command = parts[0]
        if command not in COMMANDS:
            return "Comando desconhecido. Use !ajuda."
        if len(parts) != 1:
            return "Este comando não aceita argumentos. Use !ajuda."
        if command in {"!proximo", "!finalizar"} and sender not in self.professor_ids:
            return "Apenas usuáris autorizados podem usar este comando."
        if command == "!ajuda":
            return HELP
        if command == "!entrar":
            position = service.join(room_id, sender)
            name = display_name or sender
            return f"{name} entrou na fila. Posição: {position}."
        if command == "!sair":
            service.leave(room_id, sender)
            return f"{name} saiu da fila de espera."
        if command == "!fila":
            waiting = service.waiting(room_id)
            if not waiting:
                return "A fila está vazia."
            return "Fila de espera:\n" + "\n".join(
                f"{position}. {user_id}" for position, user_id in enumerate(waiting, 1)
            )
        if command == "!posicao":
            if service.active(room_id) == sender:
                return "Você está em atendimento."
            position = service.position(room_id, sender)
            return f"Posição na fila de {name}: {position}." if position else "Você não está na fila de espera."
        if command == "!proximo":
            return f"Próximo aluno: {service.call_next(room_id)}. Atendimento iniciado."
        if command == "!finalizar":
            return f"Atendimento de {service.finish(room_id)} finalizado."
        status = service.status(room_id)
        active = status.active_user or "ninguém"
        return f"Em atendimento: {active}. Em espera: {status.waiting_count}."
