import pytest

from fila_academica.config import ConfigError, load_config


@pytest.fixture
def environment(monkeypatch, tmp_path):
    values = {
        "MATRIX_HOMESERVER": "https://matrix.example.org/",
        "MATRIX_USER_ID": "@bot:example.org",
        "MATRIX_ACCESS_TOKEN": "token-apenas-de-teste",
        "MATRIX_ROOM_IDS": "!sala:example.org, !outra:example.org",
        "PROFESSOR_IDS": "@professor:example.org",
        "DATABASE_PATH": str(tmp_path / "fila.sqlite3"),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return tmp_path / "ausente.env"


def test_valid_config_and_token_not_in_repr(environment):
    config = load_config(environment)
    assert config.homeserver == "https://matrix.example.org"
    assert len(config.room_ids) == 2
    assert config.access_token not in repr(config)


def test_room_id_can_be_opaque_without_a_server_suffix(environment, monkeypatch):
    monkeypatch.setenv("MATRIX_ROOM_IDS", "!opaque_room_hash")
    assert load_config(environment).room_ids == frozenset({"!opaque_room_hash"})


@pytest.mark.parametrize("name,value", [
    ("MATRIX_ACCESS_TOKEN", ""),
    ("MATRIX_HOMESERVER", "ftp://matrix.example.org"),
    ("MATRIX_HOMESERVER", "https://usuario:segredo@matrix.example.org"),
    ("MATRIX_HOMESERVER", "https://matrix.example.org?access_token=segredo"),
    ("MATRIX_HOMESERVER", "https://matrix.example.org:invalida"),
    ("MATRIX_ROOM_IDS", "#alias:example.org"),
    ("MATRIX_ROOM_IDS", "!sala:example.org,"),
    ("PROFESSOR_IDS", "Professor"),
    ("MATRIX_USER_ID", "@bot:"),
])
def test_invalid_config(environment, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError) as error:
        load_config(environment)
    assert name in str(error.value)
    assert "segredo" not in str(error.value)


def test_env_file_does_not_override_environment(environment, monkeypatch):
    environment.write_text("MATRIX_USER_ID=@outro:example.org\n", encoding="utf-8")
    assert load_config(environment).user_id == "@bot:example.org"
