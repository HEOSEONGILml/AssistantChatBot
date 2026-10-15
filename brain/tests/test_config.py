import keyring.errors
import pytest

from brain import config


def test_data_dir_under_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    d = config.data_dir()
    assert d == tmp_path / "TamagotchiChatBot" / "brain"
    assert d.is_dir()


@pytest.fixture
def fake_keyring(monkeypatch):
    store = {}
    monkeypatch.setattr(config.keyring, "set_password", lambda s, n, v: store.__setitem__((s, n), v))
    monkeypatch.setattr(config.keyring, "get_password", lambda s, n: store.get((s, n)))
    return store


def test_write_then_read_keys(fake_keyring):
    config.write_key("gemini", "  abc  ")
    assert config.read_keys() == {"typesafe": None, "gemini": "abc"}


def test_write_key_rejects_unknown_name(fake_keyring):
    with pytest.raises(ValueError):
        config.write_key("openai", "x")


def test_write_key_rejects_blank(fake_keyring):
    with pytest.raises(ValueError):
        config.write_key("gemini", "   ")
    assert fake_keyring == {}


def test_keyring_error_reads_as_missing(monkeypatch):
    def boom(service, name):
        raise keyring.errors.KeyringError("backend down")
    monkeypatch.setattr(config.keyring, "get_password", boom)
    assert config.read_keys() == {"typesafe": None, "gemini": None}
