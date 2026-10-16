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
    assert "끼어든다" in data["지금 말하는 상황"]
    assert "같은 말" in p


def test_prompt_for_chained_line_says_continue_not_repeat():
    p = dialogue_prompt({}, "none", "none", ["dog_spoke"], ["멍, 놀자!"])
    assert "이어" in json.loads(p.split("\n")[0])["지금 말하는 상황"]


def test_interjection_reacts_to_what_is_being_typed():
    state = {"이번 이벤트들": [{"종류": "타이핑", "맥락": {"글": "오늘 팀장님이 내 발표를"}}]}
    data = json.loads(dialogue_prompt(state, "sad", "sit", ["typing"], []).split("\n")[0])
    assert data["쓰는 중인 글"] == "오늘 팀장님이 내 발표를"
    assert "무슨 글" in data["지금 말하는 상황"]  # '무슨 글 써?'처럼 모르는 척 묻지 말라는 지시


def test_rules_limit_filler_words():
    s = system_instruction()
    assert "군말" in s and "없는 말" in s


# ---- 검수 003 대사 ----


def test_rules_against_invented_returns_counted_minutes_formal_speech_and_flip_flops():
    s = system_instruction()
    for rule in ("돌아옴", "분·초를 세어", "존댓말", "이미 고른 것", "탓하지", "몸짓"):
        assert rule in s


def test_quiet_seconds_are_not_shown_to_the_dialogue():
    # 조용함 이벤트의 '10분'을 실제 경과로 읊지 않게, 대사 프롬프트에서는 조용함의 초를 뺀다 (검수 003)
    state = {"이번 이벤트들": [{"종류": "조용함", "맥락": {"시간(초)": 600}}], "최근 이벤트 기록": ["10분 전 · 조용함 (시간(초) 600)"]}
    p = dialogue_prompt(state, "bored", "none", ["quiet"], [], 3 * 3600)
    assert "600" not in p and "3시간" in p
    assert state["이번 이벤트들"][0]["맥락"] == {"시간(초)": 600}  # Jev에 쓰는 원본은 그대로


def test_quiet_situation_says_the_user_has_not_returned():
    p = dialogue_prompt({}, "bored", "none", ["quiet"], [], 1800)
    assert "돌아오지 않았" in json.loads(p.split("\n")[0])["지금 말하는 상황"]
