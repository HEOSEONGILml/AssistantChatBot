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


def claude_env() -> dict[str, str]:
    """Claude Code에 줄 환경. ANTHROPIC_API_KEY가 있으면 그 키로 과금되고 크롬 조작이 꺼진다.
    SDK는 이 값을 os.environ 위에 덮어쓰므로, 키를 빼는 것만으로는 안 되고 빈 값으로 덮는다."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["ANTHROPIC_API_KEY"] = ""
    return env


def screenpipe_cmd() -> list[str]:
    """screenpipe 녹화 명령. 기록은 이틀만 두고 모두 지운다(사용자 결정). OCR 언어는 한국어·영어(빠지면 한글을 한자 등으로 잘못 읽었다, 2026-10-22 확인). 소리 설정은 기본값 그대로."""
    return ["npx", "-y", "screenpipe", "record", "--retention-days", "2", "--retention-mode", "all", "--language", "korean", "--language", "english"]
