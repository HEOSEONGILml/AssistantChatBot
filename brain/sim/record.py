"""대표 상황의 실제 Jev 응답을 녹화한다 (두뇌 스펙 v2 10절). 실행: brain/에서 uv run python -m sim.record
키는 OS 자격 저장소에서 읽는다(앱 설정에서 넣은 키). 결과: sim/jev_recording.json"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from brain import config, model
from brain.clients import CallError, TypeSafeJev
from brain.questions import jev_state

PRESETS = {"기본": {}, "심심함": {"심심함": 0.9}, "졸림": {"졸림": 0.9}, "분노": {"분노": 0.9}, "들뜸": {"들뜸": 0.9}, "시무룩": {"시무룩": 0.9},
           "궁금함": {"궁금함": 0.9}, "놀람": {"놀람": 0.9}, "무서움": {"무서움": 0.9}, "행복": {"행복": 0.9}}
INTIMACY = (0.2, 0.8)
CONTEXTS = {"typing": {"text": "회의록 정리해야 하는데 자료가"}, "message": {"text": "오늘 점심 뭐 먹지"},
            "dog_spoke": {"text": "멍! 간식 먹을래?"}, "quiet": {"seconds": 600}, "returned": {"away_seconds": 3600},
            "house_in": {}, "house_out": {"away_seconds": 7200}, "poke": {}, "pet": {"seconds": 3},
            "throw": {"impact": 0.7, "bounces": 2, "flight_seconds": 1.2}}
UTTERANCES = ["멍! 고생했어", "간식 먹을래?", "나랑 놀자 멍멍"]
OUT = Path(__file__).with_name("jev_recording.json")
NOW = 1_760_000_000.0


def key(kind: str, preset: str, intimacy: float, streak: int) -> str:
    return f"{kind}|{preset}|{intimacy}|{streak}"


def cases():
    for kind in CONTEXTS:
        for preset in PRESETS:
            for intimacy in INTIMACY:
                for streak in ((0, 1, 2) if kind == "dog_spoke" else (0,)):
                    yield kind, preset, intimacy, streak


def _ev(kind, data, ago=0.0, source="user"):
    return SimpleNamespace(ts=NOW - ago, source=source, kind=kind, data=data)


def state_for(kind: str, preset: str, intimacy: float, streak: int) -> dict:
    dog = model.default_dog(NOW)
    dog.mood.update(PRESETS[preset])
    dog.intimacy = intimacy
    recent = [_ev("message", {"text": "오늘 회의 너무 길었어"}, 300)]
    recent += [_ev("dog", {"utterance": UTTERANCES[i]}, 60 * (streak - i), "dog") for i in range(streak)]
    return jev_state(dog, [_ev(kind, CONTEXTS[kind])], recent, NOW)


async def main() -> None:
    keys = config.read_keys()
    if not keys["typesafe"]:
        sys.exit("TypeSafe 키가 없다. 앱 설정에서 넣는다")
    jev = TypeSafeJev(keys["typesafe"], 10.0)
    data = {}
    for c in cases():
        for attempt in range(3):  # 녹화는 실시간이 아니므로 일시적인 API 오류는 다시 시도한다
            try:
                rd = await jev.judge(state_for(*c))
                break
            except CallError:
                if attempt == 2:
                    raise
                await asyncio.sleep(2)
        data[key(*c)] = {"action": rd.action, "speak": rd.speak, "change": rd.change, "user_down": rd.user_down, "soothe": rd.soothe}
    await jev.aclose()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(data)}개 녹화 → {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
