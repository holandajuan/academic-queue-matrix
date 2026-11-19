"""Transporte Matrix sem E2EE; sincronização incremental via token do SDK."""

import asyncio
import logging

from aiohttp import ClientError
from nio import (
    AsyncClient,
    AsyncClientConfig,
    MatrixRoom,
    RoomMessageText,
    RoomSendResponse,
    SyncResponse,
)

from .command_handler import CommandHandler
from .config import Config


logger = logging.getLogger(__name__)


class MatrixConnectionError(RuntimeError):
    """Erro permanente que requer revisão das credenciais/permissões."""


class MatrixBot:
    def __init__(self, config: Config, handler: CommandHandler):
        self.config = config
        self.handler = handler
        self.client = AsyncClient(
            config.homeserver,
            user=config.user_id,
            config=AsyncClientConfig(max_timeouts=0, max_limit_exceeded=0),
        )
        self.client.user_id = config.user_id
        self.client.access_token = config.access_token

    async def run(self) -> None:
        try:
            # Sem callback: o lote inicial atualiza rooms/next_batch, mas não executa comandos.
            await self._sync_with_retry(timeout=30_000)
            for room_id in self.config.room_ids:
                room = self.client.rooms.get(room_id)
                if room is None:
                    raise MatrixConnectionError(
                        "A conta do bot deve participar de todas as salas configuradas."
                    )
                if room.encrypted:
                    raise MatrixConnectionError("Use uma sala de testes sem criptografia E2EE.")
            self.client.add_event_callback(self.on_message, RoomMessageText)
            logger.info("Bot pronto. Histórico inicial ignorado; aguardando comandos.")
            while True:
                # sync() reutiliza client.next_batch nas próximas requisições, inclusive nas reconexões.
                await self._sync_with_retry(timeout=30_000)
        finally:
            await self.client.close()

    async def _sync_with_retry(self, timeout: int) -> SyncResponse:
        delay = 1
        while True:
            try:
                response = await self.client.sync(timeout=timeout)
            except (ClientError, OSError, TimeoutError) as error:
                # Não imprimir a exceção: URLs de requisições podem conter credenciais.
                logger.warning("Conexão Matrix interrompida (%s).", type(error).__name__)
            else:
                if isinstance(response, SyncResponse):
                    return response
                if response.status_code in {"M_UNKNOWN_TOKEN", "M_MISSING_TOKEN", "M_FORBIDDEN"}:
                    raise MatrixConnectionError(
                        "Matrix recusou o acesso. Confira a conta, o token e as permissões."
                    )
                logger.warning("Sincronização Matrix recusada; nova tentativa em %ss.", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    async def on_message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        if (room.room_id not in self.config.room_ids
                or room.encrypted
                or event.sender == self.config.user_id
                or not event.body.startswith("!")):
            return
        # Edições não são novos comandos. O texto substituto não altera o evento original.
        if event.source.get("content", {}).get("m.relates_to", {}).get("rel_type") == "m.replace":
            return
        response = await asyncio.to_thread(
            self.handler.handle, room.room_id, event.sender, event.event_id, event.body,
            display_name=room.user_name(event.sender),
        )
        if response is None:
            return
        logger.info("Comando persistido: sala=%s evento=%s", room.room_id, event.event_id)
        try:
            sent = await self.client.room_send(
                room_id=room.room_id,
                message_type="m.room.message",
                content={"msgtype": "m.notice", "body": response},
            )
        except (ClientError, OSError, TimeoutError) as error:
            logger.warning(
                "Resposta não confirmada (%s): evento=%s. Estado já persistido.",
                type(error).__name__, event.event_id,
            )
        else:
            if not isinstance(sent, RoomSendResponse):
                logger.warning(
                    "Envio recusado: evento=%s. Estado já persistido.", event.event_id
                )
