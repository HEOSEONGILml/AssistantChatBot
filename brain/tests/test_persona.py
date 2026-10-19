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


# ---- 성격별 말투 (검수 004: 네 성격이 같은 말투) ----

from brain.persona import voice
from brain.tuning import Tuning
from sim.simulate import archetype_dog


def test_each_archetype_gets_a_different_voice():
    t = Tuning()
    voices = {n: voice(archetype_dog(n), t) for n in ("평균", "과묵·차분", "예민·성마름", "활발·변덕쟁이")}
    assert len(set(v["지시"] for v in voices.values())) == 4
    assert voices["과묵·차분"]["문장 수"] == 1 and voices["활발·변덕쟁이"]["문장 수"] == 2
    assert "짧" in voices["과묵·차분"]["지시"] and "투덜" in voices["예민·성마름"]["지시"] and "들떠" in voices["활발·변덕쟁이"]["지시"]


def test_rules_ban_stock_phrases():
    s = system_instruction()
    assert "상투" in s and "앗, 깜짝이야" in s


def test_prompt_tells_when_the_owner_looks_down():
    p = dialogue_prompt({}, "sad", "beg", ["message"], [], 0, [], "", owner_down=True)
    assert json.loads(p.split("\n")[0])["사용자 기분"] == "속상해 보인다"
    assert "상담사" in system_instruction()


def test_prompt_carries_facts_and_rule():
    p = dialogue_prompt({}, "none", "none", ["quiet"], [], 0, [], "", False, ["주인은 곁에서 조용히 뭔가 하고 있다"])
    assert json.loads(p.split("\n")[0])["지금 상황 사실"] == ["주인은 곁에서 조용히 뭔가 하고 있다"]
    assert "상황 사실" in system_instruction()


def test_rules_against_meta_words_human_body_and_repeating_an_answer():
    s = system_instruction()
    for rule in ("'화면'", "발", "이미 한 답"):
        assert rule in s


def test_prompt_states_the_current_mood_for_tone():
    p = dialogue_prompt({}, "none", "none", ["dog_spoke"], [], 0, [], "", False, [], mood_now="무서움")
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

from brain.persona import trim_line


def test_trim_drops_stock_opening_finally():
    assert trim_line("드디어 왔네! 밥은 먹었어?") == "왔네! 밥은 먹었어?"
    assert trim_line("드디어, 나왔다!") == "나왔다!"
    assert trim_line("우와, 드디어 왔네!") == "우와, 왔네!"


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
    p = dialogue_prompt({}, "sad", "none", ["message"], [], 0, [], "", False, [], "", ["옆에 있을게"])
    assert json.loads(p.split("\n")[0])["최근에 너무 자주 쓴 표현(쓰지 않는다)"] == ["옆에 있을게"]
    s = system_instruction()
    assert "바탕화면" in s and "현관" in s and "무릎" in s


def test_trim_drops_sentences_with_offscreen_places_and_banned_words():
    assert trim_line("언제 오려나... 창밖만 계속 보게 되네. 나랑 놀자!") == "언제 오려나... 나랑 놀자!"
    assert trim_line("짖! 우울한 공기는 털어내자.") == "우울한 공기는 털어내자."
    assert trim_line("목 빠지는 줄 알았어! 밥은 먹었어?") == "밥은 먹었어?"


def test_rule_speak_only_feelings_that_happened():
    assert "뽑힌 반응'에 없는" in system_instruction()


def test_rule_spoken_action_matches_picked_action():
    assert "말로 하는 동작" in system_instruction()


def test_trim_replaces_system_word_user():
    assert trim_line("나는 사용자랑 노는 게 좋아.") == "나는 너랑 노는 게 좋아."


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


def test_trim_drops_repeated_body_narration():
    # 꼬리·자세는 그림이 보여 준다. 최근에 이미 말했으면 그 문장을 뺀다 (검수 011: 306줄 중 26줄 "꼬리")
    assert trim_line("심심해서 꼬리가 축 처져. 놀아 줘!", recent=["꼬리 살랑 흔들게"]) == "놀아 줘!"
    assert trim_line("꼬리가 신나서 멈추질 않아!", recent=["안녕"]) == "꼬리가 신나서 멈추질 않아!"
    assert trim_line("꼬리가 살랑거려. 공놀이 좋아!") == "공놀이 좋아!"  # 다른 말이 있으면 해설은 뺀다


def test_trim_drops_invented_world():
    # 바탕화면 강아지는 햇살·창문·냄새를 모른다 (검수 011)
    assert trim_line("창문 틈 햇살이 따뜻해. 같이 놀자!") == "같이 놀자!"
    assert trim_line("커피 냄새가 솔솔 나네. 맛있었어?") == "맛있었어?"


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


def test_command_fact_says_whether_the_dog_obeyed():
    # 검수 012: "엎드려"에 앉아 놓고 "납작하게 배 깔고 있을게"라고 말했다
    from brain.persona import command_fact
    assert "하지 않았다" in command_fact({"lie_down": 0.9, "none": 0.1}, "sit")
    assert "엎드리기" in command_fact({"lie_down": 0.9, "none": 0.1}, "sit")
    assert "했다" in command_fact({"lie_down": 0.9, "none": 0.1}, "lie_down")
    assert command_fact({"none": 0.9, "sit": 0.1}, "sit") is None
    assert command_fact({}, "sit") is None


# ---- 검수 012 묶음 3: 주인 말의 뜻을 사실로 준다 ----


def test_space_request_is_not_read_as_upset():
    # "아 아니다 됐어 신경 쓰지 마": 속상함 0.48~0.53, 조용히 0.58~0.67 → "말하기 어려우면 곁에 있을게"(위로)였다
    from brain.persona import owner_upset, space_fact
    assert not owner_upset(0.53, 0.17, 0.67)
    assert owner_upset(0.89, 0.06, 0.06)          # "오늘 회의 너무 힘들었어"
    assert owner_upset(0.85, 0.05, 0.7)           # 힘들어서 혼자 있고 싶다: 속상한 것은 맞다
    assert space_fact(0.61) and "자러" in space_fact(0.61)   # "일 좀 할게" → "벌써 자려는 거야?"였다
    assert space_fact(0.2) is None


def test_trim_drops_things_the_dog_never_did_or_has():
    from brain.persona import trim_line
    assert trim_line("나는 방금 먹고 왔어! 너는 뭐 먹었어?") == "너는 뭐 먹었어?"
    assert trim_line("집 안에서 문밖만 보고 있었어. 나왔다, 멍!") == "나왔다, 멍!"
    assert trim_line("내가 좋아하는 장난감으로 놀자. 심심해!") == "심심해!"
    assert trim_line("얼른 문 열어 줘! 왈!") == "왈!"
    assert trim_line("무슨 문제 있어? 질문해도 돼") == "무슨 문제 있어? 질문해도 돼"
