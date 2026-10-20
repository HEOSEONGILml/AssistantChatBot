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


def test_rules_keep_the_dialogue_honest_and_roles_straight():
    s = system_instruction()
    for rule in ("대화 기록에 없는", "아직 고르지 않았으면", "날짜가 바뀌었으면", "던져진 것", "집에 들어갔다 나온 것", "떠났다고 말하지 않는다"):
        assert rule in s


def test_prompt_carries_the_conversation_log():
    p = dialogue_prompt({}, "none", "none", ["message"], [], 0, ["어제 19:02 · 사용자: 내일이 내 생일이야"])
    assert json.loads(p.split("\n")[0])["대화 기록(오래된 것부터)"] == ["어제 19:02 · 사용자: 내일이 내 생일이야"]


# ---- 단순화: 성격·친밀도 없이 기분으로 말한다 ----


def test_system_speaks_from_mood_not_personality_numbers():
    s = system_instruction()
    assert "기분" in s and "강아지:" in s
    for gone in ("기준값", "민감도", "변덕", "친밀도"):
        assert gone not in s


def test_rules_ban_stock_phrases():
    s = system_instruction()
    assert "상투" in s and "앗, 깜짝이야" in s


def test_rules_say_how_to_comfort_an_upset_owner():
    assert "상담사" in system_instruction()


def test_prompt_carries_facts_and_rule():
    p = dialogue_prompt({}, "none", "none", ["quiet"], [], 0, [], ["주인은 곁에서 조용히 뭔가 하고 있다"])
    assert json.loads(p.split("\n")[0])["지금 상황 사실"] == ["주인은 곁에서 조용히 뭔가 하고 있다"]
    assert "상황 사실" in system_instruction()


def test_rules_against_meta_words_human_body_and_repeating_an_answer():
    s = system_instruction()
    for rule in ("'화면'", "발", "이미 한 답"):
        assert rule in s


def test_prompt_states_the_current_mood_for_tone():
    p = dialogue_prompt({}, "none", "none", ["dog_spoke"], [], 0, [], [], mood_now="무서움")
    assert "움츠" in json.loads(p.split("\n")[0])["지금 기분"]
    s = system_instruction()
    assert "깡총" in s and "하지 않은 행동" in s


# ---- 검수 007 대사 ----


def test_interjection_does_not_assert_or_choose_on_unfinished_text():
    p = dialogue_prompt({}, "curious", "sit", ["typing"], [])
    sit = json.loads(p.split("\n")[0])["지금 말하는 상황"]
    assert "덜 끝났" in sit and "고르지" in sit


def test_return_greeting_knows_how_long_and_avoids_stock_words():
    state = {"이번 이벤트들": [{"종류": "사용자가 돌아옴", "맥락": {"떠나 있던 시간(초)": 5400}}]}
    p = dialogue_prompt(state, "happy", "beg", ["returned"], [], 0)
    assert json.loads(p.split("\n")[0])["비운 시간"] == "1시간 30분"
    s = system_instruction()
    assert "드디어" in s and "목 빠지" in s


# ---- 검수 008 대사 ----


def test_rules_against_invented_actions_and_self_commentary():
    s = system_instruction()
    for rule in ("화면의 너는", "공·간식", "풀렸다고"):
        assert rule in s


# ---- 검수 009 대사 ----

from brain.persona import frequent_phrases


def test_frequent_phrases_finds_repeated_templates():
    lines = ["많이 힘들었지, 내가 옆에 있을게.", "괜찮아, 옆에 있을게 멍.", "목 빠지는 줄 알았어!", "기다리느라 목 빠지는 줄 알았어", "오늘 날씨 좋다"]
    found = frequent_phrases(lines)
    assert "옆에 있을게" in found and "목 빠지는" in found
    assert all("날씨" not in f for f in found)


def test_prompt_lists_overused_phrases_and_screen_rule():
    p = dialogue_prompt({}, "sad", "none", ["message"], [], 0, [], [], "", ["옆에 있을게"])
    assert json.loads(p.split("\n")[0])["최근에 너무 자주 쓴 표현(쓰지 않는다)"] == ["옆에 있을게"]
    s = system_instruction()
    assert "바탕화면" in s and "현관" in s and "무릎" in s


def test_rule_speak_only_feelings_that_happened():
    assert "뽑힌 반응'에 없는" in system_instruction()


def test_rule_spoken_action_matches_picked_action():
    assert "말로 하는 동작" in system_instruction()


def test_instructions_have_no_template_examples():
    # 지시 속 예시 문장이 그대로 틀이 됐다 (검수 010: 집 = "좁고 답답" 9/9, 위로 = "옆에 있을게")
    s = system_instruction()
    house = dialogue_prompt({}, "happy", "none", ["house_out"], [])
    for example in ("집 안 답답했어", "내가 옆에 있을게"):
        assert example not in s and example not in house
    assert "먹을 것" in s and "갇혀" in house


# ---- 검수 011 대사 ----

from brain.persona import quiet_topics


def test_frequent_phrases_includes_repeated_sentence_endings():
    # "곁에 있을게", "여기 앉아 있을게", "가만히 있을게"처럼 끝맺음 틀도 되풀이다 (검수 011: 위로 12줄)
    lines = ["곁에 있을게.", "여기 앉아 있을게 멍.", "가만히 있을게!", "놀자"]
    assert "있을게" in frequent_phrases(lines)


def test_quiet_topics_offer_earlier_talk_mood_and_action():
    # 혼자 둘 때 할 말의 거리: 아까 주인이 한 말, 지금 기분, 지금 동작 (검수 011: "심심해·언제 와" 한 틀)
    topics = quiet_topics(["이따 같이 공놀이 하자"], "심심함", "엎드리기")
    assert any("공놀이" in x for x in topics)
    assert any("심심" in x for x in topics) and any("엎드리기" in x for x in topics)
    assert len(quiet_topics([], "", "")) >= 1


def test_prompt_carries_the_topic():
    p = dialogue_prompt({}, "bored", "none", ["quiet"], [], 1800, topic="아까 주인이 한 말: 이따 같이 공놀이 하자")
    assert "공놀이" in json.loads(p.split("\n")[0])["꺼낼 이야기"]


def test_rules_for_known_world_body_and_roles():
    s = system_instruction()
    for rule in ("그림이 보여", "날씨", "냄새", "주인 자신의 일", "기록에 있는 것만"):
        assert rule in s
    assert "꼬리 살랑" not in s  # 지시에 쓴 몸짓 낱말이 틀이 된다


# ---- 검수 012 묶음 3 ----


# ---- 검수 013 묶음 3: 의성어만 남는 대답, 몸 해설, 집 역할 ----


