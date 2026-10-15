"""기본 성격과 대사(Gemini) 지시·프롬프트를 두는 한곳 (vision 캐릭터 절, 두뇌 스펙 v2 7절).
Gemini에도 Jev와 같은 데이터를 수치 그대로 준다 (사용자 결정)."""
import json
import re

from .model import ACTION_NAMES, REACTION_NAMES

PERSONA = "호기심 많고 수다스러운 강아지. 사용자를 좋아한다."
STYLE = "사람 말(반말)에 강아지 의성어(멍, 멍멍, 왈 등)를 섞는다. 말풍선이 작으니 한 번에 한두 문장으로 짧게 말한다."


def system_instruction() -> str:
    return ("너는 사용자의 컴퓨터 화면 위에 사는 강아지다. 아래 JSON의 성격(기준값·민감도·변덕), 기분, 친밀도(모두 0~1)와 "
            "이번에 뽑힌 반응·동작을 말투에 반영한다.\n"
            f"기본 성격: {PERSONA}\n말투: {STYLE}")


def dialogue_prompt(state: dict, reaction: str, action: str) -> str:
    data = {**state, "이번에 뽑힌 반응": REACTION_NAMES[reaction], "이번에 뽑힌 동작": ACTION_NAMES[action]}
    return json.dumps(data, ensure_ascii=False) + "\n강아지가 지금 할 말 한마디만 써라. 따옴표나 이름표 없이 대사만 쓴다."


_SENTENCE = re.compile(r"[^.!?~…]*[.!?~…]+|[^.!?~…]+$")
_LABEL = re.compile(r"^강아지\s*[:：]\s*")


def trim_line(text: str, max_sentences: int = 2) -> str:
    """LLM 출력을 말풍선 대사로 다듬는다: 줄바꿈·이름표·따옴표를 없애고 앞의 몇 문장만 남긴다."""
    t = " ".join(line.strip() for line in text.splitlines() if line.strip())
    t = _LABEL.sub("", t).strip().strip("\"'“”‘’").strip()
    parts = [p.strip() for p in _SENTENCE.findall(t) if p.strip()]
    return " ".join(parts[:max_sentences])
