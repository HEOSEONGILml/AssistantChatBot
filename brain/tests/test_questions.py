import json
from types import SimpleNamespace

from brain import model, persona, questions
from brain.tuning import MOODS

NOW = 1_760_000_000.0


def ev(kind, data=None, ago=0.0, source="user"):
    return SimpleNamespace(ts=NOW - ago, source=source, kind=kind, data=data or {})


def test_question_vocabulary():
    q = questions.QUESTIONS
    assert set(q) == {"action", "speak", "change"}  # 반응은 기분 변화에서 나온다 (기분 8개 스펙)
    assert set(q["action"].criteria) == set(model.ACTIONS)
    assert len(q["change"].criteria) == 21 and "변화없음" in q["change"].criteria and "무서움↑" in q["change"].criteria
    assert "분노↑" in q["change"].criteria and "친밀도↓" in q["change"].criteria


def test_relative_time():
    assert questions.relative(3) == "방금"
    assert questions.relative(42) == "42초 전"
    assert questions.relative(180) == "3분 전"
    assert questions.relative(7300) == "2시간 전"
    assert questions.relative(90000) == "1일 전"


def test_log_lines():
    assert questions.log_line(ev("typing", {"text": "안"}), NOW) is None
    assert questions.log_line(ev("dog_spoke", {"text": "멍"}), NOW) is None
    assert questions.log_line(ev("message", {"text": "안녕"}, 120), NOW) == "2분 전 · 사용자: 안녕"
    assert questions.log_line(ev("dog", {"utterance": "멍!"}, 60, "dog"), NOW) == "1분 전 · 강아지: 멍!"
    assert questions.log_line(ev("dog", {"reaction": "excited", "action": "beg"}, 5, "dog"), NOW) == "방금 · 강아지 반응 신남, 동작 조르기"
    assert questions.log_line(ev("throw", {"impact": 0.9}, 30), NOW) == "30초 전 · 던지기 (충격(0~1) 0.9)"
    assert questions.log_line(ev("poke"), NOW) == "방금 · 찌르기"


def test_jev_state_shape():
    dog = model.default_dog(NOW)
    dog.mood["분노"] = 0.123456
    state = questions.jev_state(dog, [ev("poke"), ev("poke")], [ev("message", {"text": "안녕"}, 60)], NOW)
    assert set(state) == {"강아지 성격", "지금 시각", "이번 이벤트들", "최근 이벤트 기록", "기분", "친밀도"}
    assert state["강아지 성격"]["기본 성격"] == persona.PERSONA
    assert set(state["강아지 성격"]["기준값"]) == set(MOODS)
    assert "변덕" in state["강아지 성격"] and "말수" not in state["강아지 성격"]
    assert state["기분"]["분노"] == 0.12
    assert state["이번 이벤트들"] == [{"종류": "찌르기"}, {"종류": "찌르기"}]
    assert state["최근 이벤트 기록"] == ["1분 전 · 사용자: 안녕"]
    json.dumps(state, ensure_ascii=False)


def test_dialogue_prompt_carries_state_and_picks():
    state = {"기분": {"시무룩": 0.9}}
    p = persona.dialogue_prompt(state, "sad", "lie_down", ["message"], [])  # 서운함
    assert '"시무룩": 0.9' in p and "서운함" in p and "엎드리기" in p


def test_system_instruction_mentions_numbers_and_style():
    s = persona.system_instruction()
    assert persona.PERSONA in s and "반말" in s and "0~1" in s


def test_trim_line():
    assert persona.trim_line("멍! 뭐 해? 나도 볼래 멍멍.") == "멍! 뭐 해?"
    assert persona.trim_line('강아지: "산책 가자 멍!"') == "산책 가자 멍!"
    assert persona.trim_line("  \n ") == ""
