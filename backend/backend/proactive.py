"""먼저 말 걸기의 판단 재료: 화면 기록 줄이기, Jev 질문 정의, 배지 조건. 질문과 임계값은 여기에만 둔다 (CLAUDE.md 4절)."""
from datetime import datetime, timedelta

BUDGET = 2000       # 글자. 2천 토큰을 한글 기준 약 2,000자로 근사 (잠정)
TEXT_LIMIT = 300    # 프레임마다 글 앞 300자
DECLINE_WINDOW = timedelta(hours=1)
NONE_DECLINED = "최근 [괜찮아]: 없음"

# 한 문장에 둘을 섞으면 판단이 흐려져 둘로 나눴다 (2026-10-22 실측, docs/superpowers/specs/2026-10-22-proactive-help-design.md 4절)
QUESTIONS = {
    "need_help": {
        "type": "noul",
        "instructions": "화면 기록을 보면 사용자가 지금 하는 일에서 막혀 있거나 헤매고 있다",
    },
    "declined_same": {
        "type": "noul",
        "instructions": "'최근 [괜찮아]'에 지금 하는 작업과 같은 앱·창이 있다. 즉 사용자는 지금 이 작업에 대한 도움 제안을 최근에 이미 거절했다",
    },
}

NEED_HELP_MIN = 0.7          # 잠정값
NEED_HELP_MIN_DECLINED = 0.9  # 같은 작업을 거절했으면 더 확실할 때만 (잠정값)
DECLINED_SAME_MIN = 0.5


def should_nudge(answers: dict[str, float]) -> bool:
    need = answers["need_help"]
    if answers["declined_same"] >= DECLINED_SAME_MIN:
        return need >= NEED_HELP_MIN_DECLINED
    return need >= NEED_HELP_MIN


def _local(dt: datetime) -> datetime:
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def summarize(frames: list[dict], declines: list[tuple[datetime, str, str]], now: datetime) -> str:
    """화면 기록을 Jev에 줄 글로 줄인다. 오래된 것부터 한 줄씩, 예산이 모자라면 오래된 줄을 버린다. 끝 줄은 거절 내역."""
    shown = [d for d in declines if _local(now) - DECLINE_WINDOW <= _local(d[0]) <= _local(now)]
    tail = ("최근 [괜찮아]: " + ", ".join(f"{_local(at):%H:%M} {app} · {win}" for at, app, win in shown)) if shown else NONE_DECLINED
    room = BUDGET - len(tail)
    lines: list[str] = []
    for f in reversed(frames):  # 새 것부터 채운다
        text = " ".join(f["text"].split())[:TEXT_LIMIT]
        line = f"{_local(f['at']):%H:%M:%S} {f['app']} · {f['window']} {text}".rstrip()
        room -= len(line) + 1
        if room < 0:
            break
        lines.append(line)
    return "\n".join([*reversed(lines), tail])
