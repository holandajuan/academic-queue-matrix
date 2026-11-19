import asyncio
import logging
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from nio import Event, MatrixRoom, RoomMessageText, RoomSendError, RoomSendResponse, SyncError, SyncResponse

from fila_academica.config import Config
from fila_academica.matrix_client import MatrixBot, MatrixConnectionError


ROOM = "!sala:example.org"
ANA = "@ana:example.org"
PROFESSOR = "@professor:example.org"


def message(event_id="$evento", body="!entrar", sender=ANA):
    return {
        "type": "m.room.message", "event_id": event_id, "sender": sender,
        "origin_server_ts": 1,
        "content": {"msgtype": "m.text", "body": body},
    }


@pytest.fixture
def bot(handler, tmp_path):
    config = Config(
        "https://matrix.example.org", "@bot:example.org", "token-de-teste",
        frozenset({ROOM}), frozenset({PROFESSOR}), tmp_path / "fila.sqlite3",
    )
    return MatrixBot(config, handler)


@pytest.mark.parametrize("kind", ["other_room", "self", "plain", "edit", "encrypted", "non_text"])
def test_filters_messages(bot, kind):
    room = MatrixRoom(ROOM, bot.config.user_id)
    source = message()
    if kind == "other_room":
        room = MatrixRoom("!outra:example.org", bot.config.user_id)
    elif kind == "self":
        source["sender"] = bot.config.user_id
    elif kind == "plain":
        source["content"]["body"] = "olá"
    elif kind == "edit":
        source["content"]["m.relates_to"] = {"rel_type": "m.replace", "event_id": "$original"}
    elif kind == "encrypted":
        room.encrypted = True
    elif kind == "non_text":
        source["content"]["msgtype"] = "m.notice"
    bot.client.room_send = AsyncMock()
    event = Event.parse_event(source)
    if isinstance(event, RoomMessageText):
        asyncio.run(bot.on_message(room, event))
    assert bot.client.room_send.await_count == 0


@pytest.mark.parametrize("failure", [RoomSendError("recusado"), OSError("token-de-teste")])
def test_failed_response_does_not_repeat_persisted_command(bot, failure, caplog):
    room = MatrixRoom(ROOM, bot.config.user_id)
    event = Event.parse_event(message())
    if isinstance(failure, Exception):
        bot.client.room_send = AsyncMock(side_effect=failure)
    else:
        bot.client.room_send = AsyncMock(return_value=failure)
    with caplog.at_level(logging.WARNING):
        asyncio.run(bot.on_message(room, event))
        asyncio.run(bot.on_message(room, event))
    assert bot.client.room_send.await_count == 1
    assert "token-de-teste" not in caplog.text
    assert ANA in bot.handler.handle(ROOM, ANA, "$consulta", "!fila")


@pytest.mark.parametrize("profile, expected_name", [
    ("named", "Ana Silva"),
    ("no_name", ANA),
    ("unknown", ANA),
    ("duplicate_name", f"Ana Silva ({ANA})"),
])
def test_join_uses_room_display_name_and_keeps_matrix_identity(bot, profile, expected_name):
    room = MatrixRoom(ROOM, bot.config.user_id)
    if profile != "unknown":
        room.add_member(ANA, None if profile == "no_name" else "Ana Silva", None)
    if profile == "duplicate_name":
        room.add_member("@outra_ana:example.org", "Ana Silva", None)
    bot.client.room_send = AsyncMock(return_value=RoomSendResponse("$resposta", ROOM))

    asyncio.run(bot.on_message(room, Event.parse_event(message())))

    content = bot.client.room_send.await_args.kwargs["content"]
    assert content["body"] == (
        f"Olá, {expected_name}! Você entrou na fila de atendimento. Posição: 1."
    )
    assert bot.handler.handle(ROOM, ANA, "$consulta", "!fila") == f"Fila de espera:\n1. {ANA}"


@pytest.mark.parametrize("room_id", [ROOM, "!opaque_room_hash"])
def test_initial_sync_is_ignored_and_reconnection_keeps_sdk_cursor(bot, monkeypatch, room_id):
    bot.config = replace(bot.config, room_ids=frozenset({room_id}))
    paths = []
    bot.client.room_send = AsyncMock(return_value=RoomSendResponse("$resposta", ROOM))
    monkeypatch.setattr("fila_academica.matrix_client.asyncio.sleep", AsyncMock())

    async def send(response_class, method, path, **kwargs):
        paths.append(path)
        number = len(paths)
        if number == 2:
            raise OSError("falha simulada")
        if number == 4:
            raise asyncio.CancelledError
        event = message("$antigo", sender="@antigo:example.org") if number == 1 else message("$novo")
        response = SyncResponse.from_dict({
            "next_batch": f"token{number}",
            "rooms": {"join": {room_id: {
                "timeline": {"events": [event], "limited": False, "prev_batch": "prev"},
                "state": {"events": [{
                    "type": "m.room.create", "state_key": "", "event_id": "$create",
                    "sender": PROFESSOR, "origin_server_ts": 0,
                    "content": {"room_version": "12"},
                }]} if number == 1 else {"events": []},
                "ephemeral": {"events": []},
                "account_data": {"events": []},
            }}},
        })
        assert isinstance(response, SyncResponse)
        await bot.client.receive_response(response)
        return response

    bot.client._send = send
    bot.client.close = AsyncMock(wraps=bot.client.close)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(bot.run())
    assert "since=" not in paths[0]
    assert "since=token1" in paths[1]
    assert "since=token1" in paths[2]
    assert "since=token3" in paths[3]
    assert bot.client.room_send.await_count == 1
    assert bot.handler.handle(room_id, ANA, "$consulta", "!fila") == f"Fila de espera:\n1. {ANA}"
    bot.client.close.assert_awaited_once()


def test_permanent_auth_error_stops_and_closes(bot):
    bot.client.sync = AsyncMock(return_value=SyncError("token recusado", "M_UNKNOWN_TOKEN"))
    bot.client.close = AsyncMock(wraps=bot.client.close)
    with pytest.raises(MatrixConnectionError, match="recusou o acesso"):
        asyncio.run(bot.run())
    bot.client.close.assert_awaited_once()
