"""Jev 질문 6개(동작·말하기·변화·사용자 속상함·달램·조용히 부탁)와 선택지 정책 설명. 반응은 따로 묻지 않고 기분 변화에서 나온다(기분 8개 스펙), Jev state를 두는 한곳 (CLAUDE.md 4절, 두뇌 스펙 v2 5절).
문구를 바꾸면 분포가 달라지므로 Jev를 다시 녹화하고 보정값을 다시 맞춘다 (brain/sim)."""
from datetime import datetime

from typesafe_sdk import Choice, Noul

from .model import ACTION_NAMES, REACTION_NAMES, Dog
from .persona import PERSONA
from .tuning import MOODS

# 정책: 반응·기분과 동작의 연결 (스펙 5절). 조르기가 모든 상황에 들어맞지 않게 쓴다 (성격 유형 실측)
ACTION_TEXT = {
    "stand": "서기: 서서 지켜본다. 궁금하거나 무언가를 기다릴 때",
    "sit": "앉기: 앉아서 쉰다. 차분하고 별일 없을 때",
    "lie_down": "엎드리기: 엎드린다. 졸리거나 시무룩할 때",
    "sleep": "잠: 잠든다. 아주 졸리고 아무 일이 없을 때만",
    "beg": "조르기: 두 발로 서서 조른다. 기뻐서 반기거나 무언가를 바랄 때",
    "bark": "짖기: 짖는다. 놀라거나 짜증 나거나 무섭거나 아주 신날 때",
    "none": "없음: 특별한 동작 없이 하던 대로 한다. 대부분의 평범한 순간",
}
# 시킨 동작은 따로 묻는다: 동작 질문은 기분 위주라 "일어나"를 '하던 대로'로 읽었다 (검수 011). 따를지는 우리 모형이 정한다
COMMAND_TEXT = {
    "stand": "서기: 일어나라고(몸을 일으켜 서라고), 서 있으라고 시킨다",  # "일어나"를 잠 깨라는 말로 읽어 없음 0.77이었다
    "sit": "앉기: 앉으라고 시킨다",
    "lie_down": "엎드리기: 엎드리라고 시킨다",
    "sleep": "잠: 자라고 시킨다",
    "beg": "조르기: 두 발로 서라고, 손을 달라고 시킨다",
    "bark": "짖기: 짖으라고 시킨다",
    "none": "없음: 강아지에게 동작을 시키지 않는다",
}
# 첫 실측에서 상황 순서(보냄 > 방금 말함 > 타이핑·조용함)를 바로잡은 "차례" 문구
SPEAK_TEXT = ("대화 흐름상 지금은 강아지가 말할 차례다. 사용자의 대답을 기다려야 하거나 "
              "사용자가 아직 할 말을 다 하지 않았다면 강아지의 차례가 아니다")
CHANGE_TEXT = {f"{d}{s}": f"이 일 자체로 강아지의 {d}이(가) {'올라간다' if s == '↑' else '내려간다'}"
               for d in (*MOODS, "친밀도") for s in ("↑", "↓")}
CHANGE_TEXT["변화없음"] = "이 일로 기분과 친밀도는 거의 변하지 않는다. 시간이 흘러 생기는 변화(혼자 있으면 심심해짐 등)는 여기서 따지지 않는다"

QUESTIONS = {
    "action": Choice(instructions="이 강아지가 지금 할 동작은?", criteria=ACTION_TEXT),
    "speak": Noul(instructions=SPEAK_TEXT),
    "change": Choice(instructions="이번 이벤트(들) 자체로 강아지의 기분·친밀도는 어떻게 변하나?", criteria=CHANGE_TEXT),
    # 사용자의 감정은 Jev가 잘 판단한다. 강아지의 공감은 우리 모형이 정한다 (검수 005)
    "user_down": Noul(instructions="사용자가 이번에 쓴 글로 보아 지금 속상하거나 힘들거나 슬프다"),
    # 사과·달램은 사용자 속상함과 헷갈리기 쉽다. 따로 묻고 강아지가 풀리는 쪽은 우리 모형이 정한다 (검수 006)
    "soothe": Noul(instructions="사용자가 이번에 쓴 글로 강아지에게 사과하거나 강아지를 달래고 있다"),
    # 조용히 해 달라는 부탁은 기억해 두고 먼저 말 걸기를 줄인다 (검수 007: "말 걸지 마" 뒤 10분 만에 말 걸기)
    "hush": Noul(instructions="사용자가 이번에 쓴 글로 강아지에게 한동안 말 걸지 말라고, 조용히 해 달라고 부탁하고 있다"),
    "command": Choice(instructions="사용자가 이번에 쓴 글로 강아지에게 시킨 동작은?", criteria=COMMAND_TEXT),
}

EVENT_NAMES = {"typing": "타이핑", "message": "메시지 보냄", "dog_spoke": "강아지 말이 화면에 뜸", "quiet": "조용함",
               "returned": "사용자가 돌아옴", "house_in": "강아지가 집에 들어감", "house_out": "강아지가 집에서 나옴",
               "poke": "찌르기", "pet": "쓰다듬기", "throw": "던지기"}
CONTEXT_NAMES = {"text": "글", "seconds": "시간(초)", "away_seconds": "떠나 있던 시간(초)", "impact": "충격(0~1)",
                 "bounces": "튕긴 횟수", "flight_seconds": "날아간 시간(초)"}


def describe_event(kind: str, context: dict) -> dict:
    d = {"종류": EVENT_NAMES.get(kind, kind)}
    if context:
        d["맥락"] = {CONTEXT_NAMES.get(k, k): v for k, v in context.items()}
    return d


def relative(seconds: float) -> str:
    s = int(max(0, seconds))
    if s < 10:
        return "방금"
    if s < 60:
        return f"{s}초 전"
    if s < 3600:
        return f"{s // 60}분 전"
    if s < 86400:
        return f"{s // 3600}시간 전"
    return f"{s // 86400}일 전"


def log_line(ev, now: float) -> str | None:
    """이벤트 기록 한 줄. 타이핑과 말풍선 표시는 대화·강아지 줄과 겹치므로 뺀다."""
    if ev.kind in ("typing", "dog_spoke"):
        return None
    if ev.kind == "message":
        what = f"사용자: {ev.data.get('text', '')}"
    elif ev.kind == "dog":
        if "utterance" in ev.data:
            what = f"강아지: {ev.data['utterance']}"
        else:
            what = f"강아지 반응 {REACTION_NAMES.get(ev.data.get('reaction'), '없음')}, 동작 {ACTION_NAMES.get(ev.data.get('action'), '없음')}"
    else:
        d = describe_event(ev.kind, ev.data)
        what = d["종류"] + (" (" + ", ".join(f"{k} {v}" for k, v in d["맥락"].items()) + ")" if "맥락" in d else "")
    return f"{relative(now - ev.ts)} · {what}"


def format_log(events: list, now: float) -> list[str]:
    return [line for e in events if (line := log_line(e, now))]


def _r(x: float) -> float:
    return round(x, 2)


def jev_state(dog: Dog, batch: list, recent: list, now: float) -> dict:
    """Jev와 Gemini가 함께 보는 데이터 (스펙 5절). 수치는 소수 둘째 자리."""
    p = dog.personality
    return {
        "강아지 성격": {"기본 성격": PERSONA, "기준값": {d: _r(p.baseline[d]) for d in MOODS},
                     "민감도": {d: _r(p.sensitivity[d]) for d in MOODS}, "변덕": _r(p.whim)},
        "지금 시각": datetime.fromtimestamp(now).strftime("%Y-%m-%d (%a) %H:%M"),
        "이번 이벤트들": [describe_event(e.kind, e.data) for e in batch],
        "최근 이벤트 기록": format_log(recent, now),
        "기분": {d: _r(dog.mood[d]) for d in MOODS},
        "친밀도": _r(dog.intimacy),
    }
