"""검수 하네스 분석 (검수 루프 스펙 2·3절): 기록을 사람이 읽는 분석표와 상태 커버리지로 바꾼다."""
from collections import Counter, defaultdict
from datetime import datetime

from brain.model import ACTION_NAMES, REACTION_NAMES, REACTIONS
from brain.questions import EVENT_NAMES
from brain.tuning import EVENT_KINDS, MOODS, REST

# 함께 높으면 어색한 기분 쌍 (검수자 정의 A)
OPPOSITES = [("무서움", "행복"), ("무서움", "들뜸"), ("분노", "행복"), ("시무룩", "들뜸"), ("시무룩", "행복"),
             ("졸림", "들뜸"), ("졸림", "놀람")]
HIGH = 0.5
KIND_OF = {v: k for k, v in EVENT_NAMES.items()}
SPEECH = {"typing": "끼어들기", "message": "답하기", "quiet": "먼저 말 걸기", "returned": "먼저 말 걸기",
          "house_out": "먼저 말 걸기", "dog_spoke": "연달아 말하기"}


def human(seconds: float) -> str:
    s = int(round(seconds))
    if s < 60:
        return f"{s}초"
    if s < 3600:
        return f"{s // 60}분 {s % 60}초" if s % 60 else f"{s // 60}분"
    h, m = divmod(s // 60, 60)
    return f"{h}시간 {m}분" if s < 86400 else f"{s / 86400:.1f}일"


def clock(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%m-%d %H:%M:%S")


def _kinds(entry: dict) -> list[str]:
    return [KIND_OF.get(e.get("종류"), e.get("종류")) for e in entry.get("events", [])]


def half_recoveries(recs: list[dict], min_rise: float = 0.05) -> list[dict]:
    """판단으로 min_rise 이상 오른 기분이 돌아가는 자리 초과분의 절반으로 돌아오기까지의 가상 시간."""
    snaps = [r for r in recs if r["type"] == "snap"]
    out = []
    for j in (r for r in recs if r["type"] == "judgement"):
        e = j["entry"]
        for mood, d in (e.get("mood_change") or {}).items():
            if mood not in MOODS or d < min_rise:
                continue
            after = [s for s in snaps if s["t"] >= e["ts"]]
            if not after:
                continue
            base = REST[mood]
            excess0 = after[0]["mood"][mood] - base
            if excess0 <= 0.02:
                continue
            row = {"mood": mood, "rise": round(d, 3), "kinds": _kinds(e), "t": e["ts"], "excess": round(excess0, 3)}
            for s in after[1:]:
                if s["mood"][mood] - base <= excess0 / 2:
                    row["seconds"] = s["t"] - e["ts"]
                    break
            else:
                row["seconds"] = None
                row["observed"] = after[-1]["t"] - e["ts"]
            out.append(row)
    return out


def opposite_overlaps(recs: list[dict]) -> list[dict]:
    """반대 기분 쌍이 함께 HIGH 이상이었던 가상 시간과 그때 둘 중 작은 값의 최대."""
    snaps = [r for r in recs if r["type"] == "snap"]
    out = []
    for a, b in OPPOSITES:
        secs, mx = 0.0, 0.0
        for s0, s1 in zip(snaps, snaps[1:] + [None]):
            lo = min(s0["mood"][a], s0["mood"][b])
            if lo >= HIGH:
                mx = max(mx, lo)
                if s1 is not None:
                    secs += s1["t"] - s0["t"]
        if mx:
            out.append({"a": a, "b": b, "seconds": secs, "max_min": round(mx, 3)})
    return out


def _table(header: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def _step_label(s: dict) -> str:
    if "say" in s:
        return f"말: {s['say'][:20]}"
    if "event" in s:
        return f"이벤트 {s['event']}"
    if "wait" in s:
        return f"{human(s['wait'])} 기다림" + (" (자리 비움)" if s.get("away") else "")
    return next(iter(s))


def _one(recs: list[dict]) -> str:
    parts = []
    t0 = recs[0]["t"]
    # 기분 흐름: 단계가 끝날 때마다
    rows, label = [], "시작"
    for r in recs:
        if r["type"] == "step":
            label = _step_label(r["step"])
        if r["type"] == "snap" and not r["tick"]:
            m = r["mood"]
            rows.append([f"+{human(r['t'] - t0)}", label, *[f"{m[d]:.2f}" for d in MOODS]])
    parts.append("### 기분 흐름 (단계 끝마다)\n\n" + _table(["시각", "단계", *MOODS], rows))
    # 기분 시계 흐름: 기다리는 동안 10분 간격
    ticks, last = [], None
    for r in recs:
        if r["type"] == "snap" and r["tick"] and (last is None or r["t"] - last >= 600):
            last = r["t"]
            ticks.append([f"+{human(r['t'] - t0)}", *[f"{r['mood'][d]:.2f}" for d in MOODS]])
    if ticks:
        parts.append("### 기다리는 동안 기분 (10분 간격)\n\n" + _table(["시각", *MOODS], ticks[:80]))
    hr = half_recoveries(recs)
    parts.append("### 반쯤 회복 시간 (오른 기분의 기준값 초과분이 절반이 되기까지, 가상 시간)\n\n" + (_table(
        ["시각", "이벤트", "기분", "오름", "초과분", "반쯤 회복"],
        [[f"+{human(h['t'] - t0)}", ",".join(h["kinds"]), h["mood"], h["rise"], h["excess"],
          human(h["seconds"]) if h["seconds"] is not None else f"관찰 {human(h['observed'])} 동안 안 풀림"] for h in hr])
        if hr else "0.05 이상 오른 기분 없음"))
    ov = opposite_overlaps(recs)
    parts.append(f"### 반대 기분이 함께 높음 (둘 다 {HIGH} 이상)\n\n" + (_table(
        ["쌍", "함께 높았던 시간", "둘 중 작은 값 최대"], [[f"{o['a']}·{o['b']}", human(o["seconds"]), o["max_min"]] for o in ov])
        if ov else "없음"))
    chain = []
    for r in recs:
        if r["type"] != "judgement":
            continue
        e = r["entry"]
        if "error" in e:
            chain.append([f"+{human(e['ts'] - t0)}", ",".join(_kinds(e)), "", "", "", f"오류: {e['error']}", ""])
            continue
        mc = sorted((e.get("mood_change") or {}).items(), key=lambda x: -abs(x[1]))[:3]
        p = e.get("picked", {})
        chain.append([f"+{human(e['ts'] - t0)}", ",".join(_kinds(e)), " ".join(f"{k}{v:+.2f}" for k, v in mc),
                      REACTION_NAMES.get(p.get("reaction"), "없음"), ACTION_NAMES.get(p.get("action"), "없음"),
                      e.get("model", {}).get("speak", ""), e.get("utterance", "")])
    parts.append("### 인과 사슬 (판단마다)\n\n" + _table(["시각", "이벤트", "기분 변화 상위", "반응", "동작", "말할 확률", "대사"], chain))
    picks = [r["entry"].get("picked", {}) for r in recs if r["type"] == "judgement" and "picked" in r["entry"]]
    rc = Counter(REACTION_NAMES.get(p["reaction"], "없음") for p in picks)
    ac = Counter(ACTION_NAMES.get(p["action"], "없음") for p in picks)
    sk = Counter()
    for r in recs:
        if r["type"] == "judgement" and "picked" in r["entry"]:
            k = _kinds(r["entry"])[-1]
            sk[(k, r["entry"]["picked"]["speak"])] += 1
    speak_rows = [[k, sk[(k, True)], sk[(k, True)] + sk[(k, False)]] for k in EVENT_KINDS if sk[(k, True)] + sk[(k, False)]]
    parts.append("### 분포\n\n" + f"판단 {len(picks)}번\n\n- 반응: " + ", ".join(f"{k} {v}" for k, v in rc.most_common())
                 + "\n- 동작: " + ", ".join(f"{k} {v}" for k, v in ac.most_common()) + "\n\n"
                 + _table(["마지막 이벤트", "말함", "판단 수"], speak_rows))
    mv = defaultdict(list)
    for r in recs:
        if r["type"] == "out" and r["msg"]["type"] == "movement":
            mv[r["msg"]["mood"]].append(r["msg"])
    mrows = []
    for mood, ms in mv.items():
        w = {k: sum(m["weights"][k] for m in ms) / len(ms) for k in ms[0]["weights"]}
        tot = sum(w.values())
        mrows.append([mood, len(ms), *[f"{w[k] / tot:.0%}" for k in w], f"{sum(m['run'] for m in ms) / len(ms):.2f}",
                      f"{sum(m['idle_scale'] for m in ms) / len(ms):.2f}"])
    keys = list(next(iter(mv.values()))[0]["weights"]) if mv else []
    parts.append("### 움직임 경향 (두드러진 기분별, 두뇌가 보낸 movement 평균. 비율은 움직임 범주 선택 확률)\n\n"
                 + (_table(["두드러진 기분", "보낸 수", *keys, "달리기 비율", "머무는 시간 배율"], mrows) if mrows else "없음"))
    snaps = [r for r in recs if r["type"] == "snap"]
    parts.append(f"경과: {human(snaps[-1]['t'] - snaps[0]['t'])}")
    end = next((r for r in recs if r["type"] == "end"), {})
    parts.append(f"호출: {end.get('calls')}, 실패: {end.get('failures')}")
    return "\n\n".join(parts)


def analyze(scenario_name: str, runs: dict[str, list[dict]]) -> str:
    return f"# 상태 분석표: {scenario_name}\n\n" + "\n\n".join(_one(recs) for recs in runs.values())


# 필수 칸: 시나리오로 반드시 일으킬 수 있는 칸. 나머지(반응·동작·대사 종류·두드러진 기분 등)는 확률 칸이다.
# 사람은 조금만 써 봐도 판단이 서므로 회차마다 생성을 많이 하지 않는다 (사용자, 2026-10-16)
REQUIRED = {("이벤트", k) for k in EVENT_KINDS} | {
    ("두뇌 단계", "idle"), ("두뇌 단계", "judging"),
    ("AI 상태", "ok"), ("AI 상태", "no_keys"), ("AI 상태", "bad_key"), ("AI 상태", "호출 실패"),
    ("장기", "다시 켬 기억"), ("장기", "초기화"),
    ("연결", "끊김"), ("연결", "다시 연결"), ("연결", "상태 조회"), ("연결", "로그 조회")}


def coverage(all_runs: dict[str, list[dict]]) -> tuple[str, list[str]]:
    """스펙 3절 칸마다 일어난 횟수. 돌려주는 값: (마크다운 표, 필수 빈 칸 목록)."""
    c: dict[str, Counter] = defaultdict(Counter)
    axes = {
        "이벤트": list(EVENT_KINDS),
        "두뇌 단계": ["idle", "judging", "speaking", "대사 버림(말하는 중 메시지)"],
        "AI 상태": ["ok", "no_keys", "bad_key", "호출 실패"],
        "반응": list(REACTIONS),
        "동작": list(ACTION_NAMES),
        "대사": ["끼어들기", "답하기", "먼저 말 걸기", "연달아 말하기", "연달아 상한(3번)", "무응답(메시지)"],
        "기분": ["calm", *[r for r in REACTIONS if r != "none"], "감쇠로 움직임 전송"],
        "장기": ["다시 켬 기억", "초기화"],
        "연결": ["끊김", "다시 연결", "상태 조회", "로그 조회"],
    }
    for recs in all_runs.values():
        streak = 0
        for r in recs:
            ty = r["type"]
            if ty == "sent":
                c["이벤트"][r["kind"]] += 1
                c["두뇌 단계"][r["phase"]] += 1
                if r["kind"] == "message" and r["phase"] == "speaking":
                    c["두뇌 단계"]["대사 버림(말하는 중 메시지)"] += 1
                if r["kind"] not in ("dog_spoke",):
                    streak = 0
            elif ty == "out":
                m = r["msg"]
                if m["type"] == "status":
                    c["AI 상태"][m["ai"]] += 1
                if m["type"] == "movement":
                    c["기분"][m["mood"]] += 1
                    if r.get("during") == "tick":
                        c["기분"]["감쇠로 움직임 전송"] += 1
            elif ty == "judgement":
                e = r["entry"]
                if "error" in e:
                    c["AI 상태"]["호출 실패" if "실패" in e["error"] else "bad_key"] += 1
                    continue
                if "picked" not in e:
                    continue
                c["AI 상태"]["ok"] += 1
                p = e["picked"]
                c["반응"][p["reaction"]] += 1
                c["동작"][p["action"]] += 1
                kinds = _kinds(e)
                if e.get("utterance"):
                    c["대사"][SPEECH.get(kinds[-1], kinds[-1])] += 1
                    streak = streak + 1 if kinds[-1] == "dog_spoke" else 1
                    if streak >= 3:
                        c["대사"]["연달아 상한(3번)"] += 1
                elif kinds[-1] == "message":
                    c["대사"]["무응답(메시지)"] += 1
            elif ty == "restart" and r["remembered"] > 0:
                c["장기"]["다시 켬 기억"] += 1
            elif ty == "reset":
                c["장기"]["초기화"] += 1
            elif ty == "connect":
                c["연결"]["다시 연결" if r["on"] else "끊김"] += 1
            elif ty == "state":
                c["연결"]["상태 조회"] += 1
            elif ty == "log":
                c["연결"]["로그 조회"] += 1
    lines, missing, chance_missing = ["# 상태 커버리지", ""], [], []
    for axis, cells in axes.items():
        lines.append(f"- **{axis}**: " + ", ".join(f"{x} {c[axis][x]}" for x in cells))
        for x in cells:
            if not c[axis][x]:
                (missing if (axis, x) in REQUIRED else chance_missing).append(f"{axis}: {x}")
    lines += ["", f"필수 칸 {len(REQUIRED) - len(missing)} / {len(REQUIRED)}",
              "", "필수 빈 칸: " + (", ".join(missing) if missing else "없음"),
              "", "확률 칸(짧은 사용에서 안 나올 수 있다. 안 나온 것 자체가 이상하면 검수자가 지적한다) 빈 칸: "
              + (", ".join(chance_missing) if chance_missing else "없음")]
    return "\n".join(lines), missing
