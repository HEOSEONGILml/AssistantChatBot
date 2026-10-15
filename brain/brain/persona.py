"""강아지 성격·말투와 대사 프롬프트를 두는 한곳 (vision 캐릭터 절). Jev state와 Gemini 프롬프트가 함께 쓴다."""
import re

PERSONA = "호기심 많고 수다스러운 강아지. 사용자를 좋아해서 말을 자주 걸고, 사용자가 타이핑하는 중에도 잘 끼어든다."
STYLE = "사람 말(반말)에 강아지 의성어(멍, 멍멍, 왈 등)를 섞는다. 말풍선이 작으니 한 번에 한두 문장으로 짧게 말한다."

SPEAKER_NAMES = {"user": "사용자", "dog": "강아지"}


def system_instruction() -> str:
    return f"너는 사용자의 컴퓨터 화면 위에 사는 강아지다.\n성격: {PERSONA}\n말투: {STYLE}"


def dialogue_prompt(*, situation: str, emotion: str, action: str,
                    recent: list[tuple[float, str, str]], typing: str) -> str:
    history = "\n".join(f"{SPEAKER_NAMES.get(who, who)}: {text}" for _, who, text in recent) or "(없음)"
    lines = [
        f"상황: {situation}",
        f"강아지의 지금 감정: {emotion}",
        f"강아지의 지금 동작: {action}",
        f"최근 대화:\n{history}",
    ]
    if typing:
        lines.append(f"사용자가 아직 보내지 않고 타이핑 중인 글: {typing}")
    lines.append("강아지가 지금 할 말 한마디만 써라. 따옴표나 이름표 없이 대사만 쓴다.")
    return "\n".join(lines)


_SENTENCE = re.compile(r"[^.!?~…]*[.!?~…]+|[^.!?~…]+$")
_LABEL = re.compile(r"^강아지\s*[:：]\s*")


def trim_line(text: str, max_sentences: int = 2) -> str:
    """LLM 출력을 말풍선 대사로 다듬는다: 줄바꿈·이름표·따옴표를 없애고 앞의 몇 문장만 남긴다."""
    t = " ".join(line.strip() for line in text.splitlines() if line.strip())
    t = _LABEL.sub("", t).strip().strip("\"'“”‘’").strip()
    parts = [p.strip() for p in _SENTENCE.findall(t) if p.strip()]
    return " ".join(parts[:max_sentences])
