from backend import config


def test_data_dir_under_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    d = config.data_dir()
    assert d == tmp_path / "TamagotchiChatBot" / "backend"
    assert d.is_dir()


def test_db_path_and_work_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.db_path() == config.data_dir() / "assistant.db"
    w = config.work_dir()
    assert w == config.data_dir() / "work" and w.is_dir()


def test_screenpipe_cmd():
    assert config.screenpipe_cmd() == ["npx", "-y", "screenpipe", "record", "--retention-days", "2", "--retention-mode", "all"]
