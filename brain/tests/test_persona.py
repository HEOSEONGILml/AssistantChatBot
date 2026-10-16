"""대사 지시·프롬프트 (검수 001 대사 지적: 반복, 던지기 오해, 질문에 안 답함, 위로 뒤집기, 이유 없는 사과)."""
import json

from brain.persona import dialogue_prompt, system_instruction


def test_system_explains_what_body_events_mean():
    s = system_instruction()
    assert "너를 마우스로 집어 던졌다" in s  # '뭔가 날아왔다'가 아니라 자기가 던져졌다
    assert "찌르기" in s and "쓰다듬기" in s


def test_system_has_conversation_rules():
    s = system_instruction()
    for rule in ("물으면 먼저 답", "하나를 골라", "위로", "사과하지 않는다", "반복하지 않는다", "의성어로 시작하지"):
        assert rule in s


def test_prompt_lists_own_recent_lines_and_why_speaking():
    p = dialogue_prompt({"기분": {}}, "happy", "beg", ["typing"], ["멍! 또 찔렀다!", "왈, 심심해"])
    data = json.loads(p.split("\n")[0])
    assert data["내가 최근에 한 말"] == ["멍! 또 찔렀다!", "왈, 심심해"]
    assert "타이핑" in data["지금 말하는 상황"]
    assert "같은 말" in p


def test_prompt_for_chained_line_says_continue_not_repeat():
    p = dialogue_prompt({}, "none", "none", ["dog_spoke"], ["멍, 놀자!"])
    assert "이어" in json.loads(p.split("\n")[0])["지금 말하는 상황"]
