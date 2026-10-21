"""백엔드의 환경 값과 키를 읽는 유일한 곳 (CLAUDE.md 3절). 다른 모듈은 환경 변수를 직접 읽지 않는다."""
import logging
import os
from pathlib import Path

import keyring
import keyring.errors

log = logging.getLogger(__name__)

KEY_NAMES = ("typesafe", "gemini")
# OS 자격 저장소(Windows 자격 증명 관리자)에 저장할 때 쓰는 서비스 이름
KEYRING_SERVICE = "TamagotchiChatBot.brain"


def data_dir() -> Path:
    """백엔드 데이터 폴더. 화면(Tauri)도 이 경로의 brain.json을 읽는다 (docs/brain-protocol.md)."""
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / "TamagotchiChatBot" / "brain"
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_keys() -> dict[str, str | None]:
    keys: dict[str, str | None] = {}
    for name in KEY_NAMES:
        try:
            keys[name] = keyring.get_password(KEYRING_SERVICE, name)
        except keyring.errors.KeyringError:
            log.exception("자격 저장소에서 키를 읽지 못해 없는 것으로 본다: %s", name)
            keys[name] = None
        keys[name] = keys[name] or None
    return keys


def write_key(name: str, value: str) -> None:
    if name not in KEY_NAMES:
        raise ValueError(f"모르는 키 이름: {name}")
    value = value.strip()
    if not value:
        raise ValueError("빈 키는 저장하지 않는다")
    keyring.set_password(KEYRING_SERVICE, name, value)
