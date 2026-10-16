"""검수 하네스 (검수 루프 스펙 2·3절). 가짜 Jev·Gemini로만 돈다."""
from collections import Counter

from review.analysis import analyze, coverage, half_recoveries, opposite_overlaps
from review.harness import LONG_TICK_S, QUIET_PRESENT_S, run_scenario


def scenario(steps, **kw):
    return {"name": "t", "personality": "평균", "seed": 1, "start": "2026-10-19T09:00", "steps": steps, **kw}


def kinds_sent(records):
    return [r["kind"] for r in records if r["type"] == "sent"]


async def test_say_expands_to_typing_then_message(tmp_path):
    runs = await run_scenario(scenario([{"say": "안녕 강아지야 오늘 날씨가 정말 좋다 산책 갈래"}]), fake=True, out_dir=tmp_path)
    sent = kinds_sent(runs["평균"])
    assert sent[:2] == ["typing", "typing"] and "message" in sent
    msg = next(r for r in runs["평균"] if r["type"] == "sent" and r["kind"] == "message")
    assert msg["context"] == {"text": "안녕 강아지야 오늘 날씨가 정말 좋다 산책 갈래"}


async def test_utterance_is_followed_by_dog_spoke(tmp_path):
    runs = await run_scenario(scenario([{"say": "안녕"}], fake_speak=1.0), fake=True, out_dir=tmp_path)
    recs = runs["평균"]
    assert any(r["type"] == "out" and "utterance" in r["msg"] for r in recs)
    assert "dog_spoke" in kinds_sent(recs)


async def test_wait_advances_clock_and_sends_quiet_like_the_screen(tmp_path):
    runs = await run_scenario(scenario([{"event": "poke"}, {"wait": QUIET_PRESENT_S * 2 + 60}]), fake=True, out_dir=tmp_path)
    recs = runs["평균"]
    assert kinds_sent(recs).count("quiet") == 2
    ticks = [r for r in recs if r["type"] == "snap" and r.get("tick")]
    assert ticks[-1]["t"] - ticks[0]["t"] >= QUIET_PRESENT_S * 2


async def test_restart_keeps_history_and_dog(tmp_path):
    runs = await run_scenario(scenario([{"say": "기억해 줘"}, {"restart": True}]), fake=True, out_dir=tmp_path)
    rs = next(r for r in runs["평균"] if r["type"] == "restart")
    assert rs["remembered"] > 0
    snaps = [r for r in runs["평균"] if r["type"] == "snap"]
    assert snaps[-1]["baseline"] == snaps[0]["baseline"]


async def test_keys_fail_and_bad_and_none(tmp_path):
    steps = [{"keys": "fail"}, {"event": "poke"}, {"keys": "ok"}, {"keys": "bad"}, {"event": "poke"},
             {"keys": "none"}, {"event": "poke"}, {"keys": "ok"}, {"event": "poke"}]
    runs = await run_scenario(scenario(steps), fake=True, out_dir=tmp_path)
    recs = runs["평균"]
    statuses = [r["msg"]["ai"] for r in recs if r["type"] == "out" and r["msg"]["type"] == "status"]
    assert "bad_key" in statuses and "no_keys" in statuses and statuses[-1] == "ok"
    assert any("error" in r["entry"] for r in recs if r["type"] == "judgement")
    end = next(r for r in recs if r["type"] == "end")
    assert end["failures"] >= 1


async def test_reset_gives_new_personality(tmp_path):
    runs = await run_scenario(scenario([{"event": "pet"}, {"reset": True}]), fake=True, out_dir=tmp_path)
    snaps = [r for r in runs["평균"] if r["type"] == "snap"]
    assert snaps[-1]["baseline"] != snaps[0]["baseline"]


async def test_nowait_events_are_batched(tmp_path):
    steps = [{"event": "typing", "context": {"text": "가나다라마바사아자차"}, "nowait": True},
             {"event": "typing", "context": {"text": "가나다라마바사아자차카타파하"}, "nowait": True},
             {"event": "message", "context": {"text": "끝"}}]
    runs = await run_scenario(scenario(steps), fake=True, out_dir=tmp_path)
    phases = [r["phase"] for r in runs["평균"] if r["type"] == "sent"]
    assert phases[0] == "idle" and "judging" in phases[1:]


async def test_personality_all_runs_each_archetype(tmp_path):
    runs = await run_scenario(scenario([{"event": "poke"}], personality="all"), fake=True, out_dir=tmp_path)
    assert set(runs) == {"평균", "과묵·차분", "예민·성마름", "활발·변덕쟁이"}


def snap(t, **mood):
    base = {"심심함": .6, "졸림": .3, "들뜸": .4, "시무룩": .2, "분노": .1, "궁금함": .5, "놀람": .1, "무서움": .1, "행복": .4}
    return {"type": "snap", "t": t, "tick": True, "mood": {**base, **mood}, "baseline": base, "intimacy": .5}


def test_half_recovery_in_virtual_time():
    recs = [snap(0, 놀람=0.5),
            {"type": "judgement", "t": 0, "entry": {"ts": 0, "events": [{"종류": "찌르기"}], "mood_change": {"놀람": 0.4}}},
            snap(60, 놀람=0.4), snap(120, 놀람=0.3), snap(180, 놀람=0.25)]
    [hr] = half_recoveries(recs)
    assert hr["mood"] == "놀람" and hr["seconds"] == 120


def test_opposite_moods_high_together_are_measured():
    recs = [snap(0, 무서움=0.6, 행복=0.7), snap(30, 무서움=0.6, 행복=0.55), snap(60, 무서움=0.2)]
    over = {(o["a"], o["b"]): o for o in opposite_overlaps(recs)}
    assert over[("무서움", "행복")]["seconds"] == 60
    assert over[("무서움", "행복")]["max_min"] == 0.6


def test_coverage_reports_empty_cells():
    recs = [{"type": "sent", "kind": "poke", "phase": "idle", "context": {}, "t": 0}]
    table, missing = coverage({"x": recs})
    assert "이벤트" in table and "poke" in table
    assert "이벤트: message" in missing and "이벤트: poke" not in missing


async def test_analysis_renders(tmp_path):
    runs = await run_scenario(scenario([{"say": "안녕"}, {"event": "throw", "context": {"impact": 0.9}}, {"wait": 900}]),
                              fake=True, out_dir=tmp_path)
    text = analyze("t", runs)
    for title in ("기분 흐름", "반쯤 회복", "반대 기분", "인과 사슬", "분포", "움직임 경향", "성격·친밀도"):
        assert title in text
    assert (tmp_path / "t.jsonl").exists()
    assert Counter(r["type"] for r in runs["평균"])["end"] == 1


async def test_long_wait_without_quiet_uses_coarse_ticks(tmp_path):
    # 회차를 짧게 (사용자 요청): 조용함을 보내지 않는 2시간 넘는 기다림은 5분 간격으로 기분 시계를 돌린다
    runs = await run_scenario(scenario([{"wait": 6 * 3600, "quiet": False}]), fake=True, out_dir=tmp_path)
    ticks = [r for r in runs["평균"] if r["type"] == "snap" and r.get("tick")]
    assert len(ticks) == 6 * 3600 // LONG_TICK_S


def test_chance_cells_are_reported_but_not_required():
    # 짧게 써 봐도 판단이 서야 한다 (사용자). 확률로만 일어나는 칸은 통과 조건이 아니라 참고로 보인다
    recs = [{"type": "sent", "kind": "poke", "phase": "idle", "context": {}, "t": 0}]
    table, missing = coverage({"x": recs})
    assert "기분: excited" not in missing and "동작: bark" not in missing
    assert "확률 칸" in table and "excited" in table
