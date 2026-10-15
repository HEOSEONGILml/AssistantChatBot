"""Jev 질문 정의와 state를 두는 한곳 (CLAUDE.md 4절, 두뇌 스펙 4.1·4.2절).
질문 문구나 Jev 모델을 바꾸면 점수가 달라지므로 임계값(tuning.speak_threshold)을 다시 산출한다."""
from datetime import datetime

from typesafe_sdk import Choice, Noul

from .persona import PERSONA, SPEAKER_NAMES

# 감정 7개 (vision, 2026-10-15 사용자 결정). 키는 프로토콜 어휘다
EMOTIONS = {
    "excited": "신남: 즐겁고 들떠 있다",
    "angry": "분노: 화가 나거나 짜증이 났다",
    "curious": "궁금함: 무언가가 궁금하고 알고 싶다",
    "surprised": "놀람: 예상 못 한 일에 깜짝 놀랐다",
    "sad": "슬픔: 서운하거나 슬프다",
    "sleepy": "졸림: 졸리고 나른하다",
    "calm": "평온: 특별한 감정 없이 편안하다",
}

# 제자리 동작만 (vision, 2026-10-15 사용자 결정). 이동은 화면의 평소 움직임 규칙이 고른다
ACTIONS = {
    "stand": "서서 바라본다",
    "sit": "앉는다",
    "lie_down": "엎드린다",
    "sleep": "잠든다",
    "beg": "두 발로 서서 조른다",
    "bark": "짖는다",
    "none": "특별한 동작 없이 하던 대로 한다",
}

SITUATIONS = {
    "typing": "사용자가 강아지에게 할 말을 타이핑하는 중이다(아직 보내지 않았다)",
    "sent": "사용자가 방금 강아지에게 말을 보냈다",
    "quiet": "한동안 별일이 없다",
    "just_spoke": "강아지가 방금 말했다",
    "interaction:poke": "사용자가 방금 강아지를 콕 찔렀다",
    "interaction:pet": "사용자가 방금 강아지를 쓰다듬었다",
    "interaction:throw": "사용자가 방금 강아지를 들어서 던졌다",
    "user_return": "자리를 비웠던 사용자가 방금 돌아왔다",
    "house_out": "강아지가 방금 자기 집에서 나왔다",
}

QUESTIONS = {
    "emotion": Choice(instructions="이 강아지의 지금 감정은 무엇인가?", criteria=EMOTIONS),
    "action": Choice(instructions="이 강아지가 지금 할 동작은 무엇인가?", criteria=ACTIONS),
    # 끼어들기·선발화·답할지·한 마디 더 할지를 모두 이 질문 하나로 묻는다. 상황은 state로만 구분한다
    "speak_now": Noul(instructions="이 강아지가 지금 말을 하는 것이 자연스럽다"),
}


def human_duration(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}초"
    if s < 3600:
        return f"{s // 60}분"
    return f"{s // 3600}시간 {s % 3600 // 60}분"


def format_recent(recent: list[tuple[float, str, str]]) -> str:
    return "\n".join(f"{SPEAKER_NAMES.get(who, who)}: {text}" for _, who, text in recent)


def jev_state(*, situation: str, now: datetime, typing: str, recent: list[tuple[float, str, str]],
              since_last_s: float | None, unread: bool, emotion: str, consecutive: int,
              house_away_s: float | None) -> dict[str, object]:
    # 자리 비움 여부는 넣지 않는다. 호출 주기에만 쓴다 (첫 버전 스펙 4.2절)
    state: dict[str, object] = {
        "강아지 성격": PERSONA,
        "지금 시각": now.strftime("%Y-%m-%d %H:%M (%a)"),
        "상황": SITUATIONS[situation],
        "최근 대화": format_recent(recent) or "(없음)",
        "마지막 대화 이후": "대화한 적 없음" if since_last_s is None else human_duration(since_last_s),
        "강아지의 안 읽힌 말풍선": "있음" if unread else "없음",
        "강아지의 지금 감정": EMOTIONS[emotion],
        "사용자 입력 없이 강아지가 연달아 말한 횟수": consecutive,
    }
    if typing:
        state["사용자가 타이핑 중인 글"] = typing
    if house_away_s is not None:
        state["집에 있던 시간"] = human_duration(house_away_s)
    return state
