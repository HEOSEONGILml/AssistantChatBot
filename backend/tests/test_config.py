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
    assert config.screenpipe_cmd() == ["npx", "-y", "screenpipe", "record", "--retention-days", "2", "--retention-mode", "all", "--language", "korean", "--language", "english"]


def test_screenpipe_dir_and_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config.Path, "home", lambda: tmp_path)
    assert config.screenpipe_dir() == tmp_path / ".screenpipe"
    assert config.screenpipe_db() == tmp_path / ".screenpipe" / "db.sqlite"


def test_mcp_descriptions():
    assert config.MCP_DESCRIPTIONS == {"screenpipe": "화면 기록 검색", "claude-in-chrome": "크롬 브라우저 조작"}
