"""Carregamento de configuração, sem autenticação própria."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


class ConfigError(ValueError):
    """Configuração ausente ou inválida."""


@dataclass(frozen=True)
class Config:
    homeserver: str
    user_id: str
    access_token: str = field(repr=False)
    room_ids: frozenset[str]
    professor_ids: frozenset[str]
    database_path: Path


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Configure {name} no ambiente ou no .env.")
    return value


def _matrix_id(value: str, prefix: str, name: str) -> str:
    local, separator, server = value.partition(":")
    if (not local.startswith(prefix) or len(local) < 2
            or (prefix == "@" and (not separator or not server))
            or (separator and not server)):
        raise ConfigError(f"{name} deve conter IDs Matrix reais iniciados por {prefix}.")
    if any(character.isspace() for character in value):
        raise ConfigError(f"{name} contém um ID Matrix com espaços.")
    return value


def _ids(name: str, prefix: str) -> frozenset[str]:
    values = _required(name).split(",")
    if any(not value.strip() for value in values):
        raise ConfigError(f"{name} contém um item vazio.")
    return frozenset(_matrix_id(value.strip(), prefix, name) for value in values)


def load_config(env_file: str | Path = ".env") -> Config:
    load_dotenv(env_file, override=False)
    homeserver = _required("MATRIX_HOMESERVER").rstrip("/")
    try:
        url = urlsplit(homeserver)
        port = url.port
    except ValueError:
        raise ConfigError("MATRIX_HOMESERVER deve ser uma URL HTTP(S) válida.") from None
    if (url.scheme not in {"http", "https"} or not url.hostname
            or url.username is not None or url.password is not None
            or url.query or url.fragment or port == 0):
        raise ConfigError("MATRIX_HOMESERVER deve ser uma URL HTTP(S) sem credenciais.")
    return Config(
        homeserver=homeserver,
        user_id=_matrix_id(_required("MATRIX_USER_ID"), "@", "MATRIX_USER_ID"),
        access_token=_required("MATRIX_ACCESS_TOKEN"),
        room_ids=_ids("MATRIX_ROOM_IDS", "!"),
        professor_ids=_ids("PROFESSOR_IDS", "@"),
        database_path=Path(_required("DATABASE_PATH")).expanduser(),
    )
