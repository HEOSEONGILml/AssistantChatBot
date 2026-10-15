from datetime import datetime

from brain import persona, questions


def test_vocabulary_matches_spec():
    assert list(questions.EMOTIONS) == ["excited", "angry", "curious", "surprised", "sad", "sleepy", "calm"]
    assert list(questions.ACTIONS) == ["stand", "sit", "lie_down", "sleep", "beg", "bark", "none"]
    assert set(questions.QUESTIONS) == {"emotion", "action", "speak_now"}
    assert set(questions.QUESTIONS["emotion"].criteria) == set(questions.EMOTIONS)
    assert set(questions.QUESTIONS["action"].criteria) == set(questions.ACTIONS)


def test_human_duration():
    assert questions.human_duration(42) == "42초"
    assert questions.human_duration(150) == "2분"
    assert questions.human_duration(3 * 3600 + 5 * 60) == "3시간 5분"


def test_format_recent():
    recent = [(1.0, "user", "안녕"), (2.0, "dog", "멍! 반가워")]
    assert questions.format_recent(recent) == "사용자: 안녕\n강아지: 멍! 반가워"


def base_state(**kw):
    args = dict(situation="quiet", now=datetime(2026, 10, 15, 9, 30), typing="", recent=[],
                since_last_s=None, unread=False, emotion="calm", consecutive=0, house_away_s=None)
    args.update(kw)
    return questions.jev_state(**args)


def test_state_basics():
    s = base_state()
    assert s["상황"] == questions.SITUATIONS["quiet"]
    assert s["지금 시각"].startswith("2026-10-15 09:30")
    assert s["최근 대화"] == "(없음)"
    assert s["마지막 대화 이후"] == "대화한 적 없음"
    assert s["강아지의 안 읽힌 말풍선"] == "없음"
    assert s["강아지의 지금 감정"] == questions.EMOTIONS["calm"]
    assert "사용자가 타이핑 중인 글" not in s
    assert "집에 있던 시간" not in s
    assert s["강아지 성격"] == persona.PERSONA


def test_state_optional_fields():
    s = base_state(situation="house_out", typing="뭐 해", since_last_s=90, unread=True, house_away_s=7200)
    assert s["사용자가 타이핑 중인 글"] == "뭐 해"
    assert s["마지막 대화 이후"] == "1분"
    assert s["강아지의 안 읽힌 말풍선"] == "있음"
    assert s["집에 있던 시간"] == "2시간 0분"


def test_dialogue_prompt_includes_context():
    p = persona.dialogue_prompt(situation="사용자가 방금 말을 보냈다", emotion="신남", action="짖는다",
                                recent=[(1.0, "user", "산책 갈래?")], typing="")
    assert "산책 갈래?" in p and "신남" in p and "짖는다" in p
    assert "타이핑 중" not in p
    p2 = persona.dialogue_prompt(situation="x", emotion="y", action="z", recent=[], typing="오늘 회의가")
    assert "오늘 회의가" in p2


def test_system_instruction_has_persona_and_style():
    s = persona.system_instruction()
    assert persona.PERSONA in s and "반말" in s


def test_trim_line_keeps_two_sentences():
    assert persona.trim_line("멍! 뭐 해? 나도 볼래 멍멍.") == "멍! 뭐 해?"


def test_trim_line_strips_label_quotes_and_newlines():
    assert persona.trim_line('강아지: "산책 가자 멍!"') == "산책 가자 멍!"
    assert persona.trim_line("첫 줄이야 멍\n\n둘째 줄") == "첫 줄이야 멍 둘째 줄"


def test_trim_line_blank():
    assert persona.trim_line("") == ""
    assert persona.trim_line("  \n ") == ""
