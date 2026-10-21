"""백엔드의 환경 값과 경로를 읽는 유일한 곳 (CLAUDE.md 3절). 다른 모듈은 환경 변수를 직접 읽지 않는다."""
import os
from pathlib import Path


def data_dir() -> Path:
    """백엔드 데이터 폴더. 화면(Tauri)도 이 경로의 backend.json을 읽는다 (docs/backend-protocol.md)."""
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / "TamagotchiChatBot" / "backend"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / "assistant.db"


def work_dir() -> Path:
    """작업 폴더. Claude Code가 파일을 다루는 곳."""
    d = data_dir() / "work"
    d.mkdir(parents=True, exist_ok=True)
    return d
