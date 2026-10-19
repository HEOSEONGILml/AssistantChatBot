import keyring.errors
import pytest

from brain import config


@pytest.fixture(autouse=True)
def no_key_env(monkeypatch):
    for name in config.KEY_ENV.values():
        monkeypatch.delenv(name, raising=False)


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


# ---- 웹 프로토타입 (스펙 2026-10-19) ----


def test_keys_fall_back_to_environment(fake_keyring, monkeypatch):
    # 자격 저장소가 없는 서버에서는 환경 변수로 키를 준다. 자격 저장소 값이 있으면 그쪽이 먼저다
    monkeypatch.setenv("TYPESAFE_API_KEY", "t-env")
    monkeypatch.setenv("GEMINI_API_KEY", "g-env")
    config.write_key("gemini", "g-ring")
    assert config.read_keys() == {"typesafe": "t-env", "gemini": "g-ring"}


def test_keyring_error_still_reads_environment(monkeypatch):
    def boom(service, name):
        raise keyring.errors.KeyringError("no backend on server")
    monkeypatch.setattr(config.keyring, "get_password", boom)
    monkeypatch.setenv("GEMINI_API_KEY", "g-env")
    assert config.read_keys() == {"typesafe": None, "gemini": "g-env"}


def test_web_data_dir_is_separate(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.web_data_dir() == tmp_path / "TamagotchiChatBot" / "brain" / "web"
    assert config.web_data_dir().is_dir()
