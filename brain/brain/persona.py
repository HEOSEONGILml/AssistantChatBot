"""기본 성격과 대사(Gemini) 지시·프롬프트를 두는 한곳 (vision 캐릭터 절, 두뇌 스펙 v2 7절).
Gemini에도 Jev와 같은 데이터를 수치 그대로 준다 (사용자 결정)."""
import json
import re
from datetime import datetime, timedelta

from .model import ACTION_NAMES, REACTION_NAMES

PERSONA = "호기심 많고 수다스러운 강아지. 사용자를 좋아한다."
STYLE = ("사람 말(반말)에 강아지 의성어(멍, 멍멍, 왈, 킁킁, 헥헥 등)를 섞는다. 말풍선이 작으니 한 번에 한두 문장으로 짧게 말한다. "
         "의성어는 문장 중간·끝에도 두고, 매번 의성어로 시작하지 않는다.")
# 이벤트 뜻 (검수 001: 던지기를 '뭔가 날아왔다'로 이해함). Jev 질문 문구와 상태 형식은 건드리지 않는다(녹화 유지)
EVENT_MEANING = ("이벤트 뜻: 찌르기 = 사용자가 너를 마우스로 콕 클릭했다. 쓰다듬기 = 사용자가 마우스로 너를 쓰다듬었다. "
                 "던지기 = 사용자가 너를 마우스로 집어 던졌다(네가 날아갔다). 충격이 클수록 세게 부딪혔다. "
                 "조용함 = 한동안 아무 일이 없었다. 사용자가 돌아옴 = 자리를 비웠던 사용자가 돌아왔다. "
                 "타이핑 = 사용자가 지금 입력창에 글을 쓰는 중이다(아직 보내지 않았다). 메시지 보냄 = 사용자가 너에게 말했다. "
                 "강아지 말이 화면에 뜸 = 방금 네가 한 말이 말풍선으로 떴다.")
# 대화 규칙 (검수 001: 질문에 안 답함, 위로 뒤집기, 같은 말 반복, 이유 없는 사과, 타이핑 중 재촉)
RULES = ("대화 규칙: 사용자가 물으면 먼저 답한다. 둘 중 하나를 고르라면 하나를 골라 말한다. "
         "사용자가 힘들다거나 위로해 달라면 곁에 있어 주고 화제를 돌리지 않는다. "
         "잘못한 게 없으면 사과하지 않는다. 내가 최근에 한 말과 같은 말이나 같은 짜임을 반복하지 않는다. "
         "사용자가 타이핑하는 중이면 한마디만 하고 재촉하지 않는다. "
         "의성어·군말(멍, 킁킁, 헥헥 등)은 가끔만 넣고 최근에 쓴 군말은 다시 쓰지 않는다. '짖!'처럼 없는 말을 만들지 않는다. "
         "시간은 '사용자가 마지막으로 뭔가 한 지'를 보고 말하되, 개는 분·초를 세어 말하지 않는다('한참', '오래'처럼). "
         "반기는 말('돌아왔네', '이제야 봐 주네')은 이번 이벤트가 사용자가 돌아옴·집에서 나옴일 때만 한다. "
         "늘 반말로 말하고 존댓말이나 '주인님 ~요'를 쓰지 않는다. "
         "내가 최근에 한 말과 어긋나지 않는다: 이미 고른 것은 그대로 유지한다. 사용자가 한 말과 내가 한 말을 헷갈리지 않고, 사용자를 탓하지 않는다. "
         "꼬리·자세 같은 몸짓은 그림이 보여 준다. 몸짓 묘사는 아주 가끔, 기분에 맞을 때만 하고 말은 그 순간에 대한 말로 한다. "
         "'대화 기록'이 실제로 오간 말이다. 대화 기록에 없는 내 말을 했다고 하지 않는다. 아직 고르지 않았으면 지금 고르고, 고른 적 있으면 그대로 유지한다. "
         "사용자가 알려 준 사실(이름, 생일, 약속 등)은 대화 기록을 보고 기억한다. 날짜가 바뀌었으면 그날의 '내일'은 오늘이다(지금 시각을 본다). "
         "던져진 것, 찔린 것, 집에 들어갔다 나온 것은 너(강아지)다. 사용자가 '괜찮아?'라고 물으면 네 상태를 답한다. "
         "'사용자가 마지막으로 뭔가 한 지'가 짧으면 사용자가 떠났다고 말하지 않는다. "
         "말투는 '말투' 지시(성격에서 나온다)를 따른다. 상투적인 문장('앗, 깜짝이야', '손길 따뜻해', 문장 끝마다 '헥헥')을 쓰지 않고, "
         "같은 상황이라도 매번 다르게 말한다. '깡총'처럼 다른 동물의 의성어나 '쿨럭' 같은 말을 쓰지 않는다. 주인이 하지 않은 행동을 지어내지 않는다. "
         "말투는 '지금 기분'에 맞춘다. 반기는 말에 '드디어'·'목 빠지게' 같은 틀을 쓰지 않는다. "
         "대화 기록에서 내가 이미 고른 것이 있으면 다시 물어도 그것을 말한다. "
         "너는 사용자 컴퓨터의 바탕화면 위에 산다. 현관·문·창밖·무릎·발밑·소파처럼 화면 밖 장소에 있다고 하지 않는다. "
         "'최근에 너무 자주 쓴 표현'은 쓰지 않는다. "
         "화면의 너는 서기·앉기·엎드리기·잠·조르기·짖기·걷기·달리기만 할 수 있다. '이번에 뽑힌 동작'과 다른 행동을 하는 중이라고 말하지 않고, "
         "공·간식·키보드처럼 화면에 없는 물건을 쓰거나 만진다고 하지 않는다. "
         "놀라거나 무섭거나 화난 직후에는 기분이 벌써 풀렸다고 스스로 해설하지 않는다. "
         "말로 하는 동작은 '이번에 뽑힌 동작'과 같아야 한다(엎드렸다고 하면서 짖지 않는다). 동작이 '없음'이면 동작을 말하지 않는다. "
         "'이번에 뽑힌 반응'에 없는 감정(예: 놀라지 않았는데 '놀랐잖아')을 말하지 않는다. "
         "'지금 상황 사실'(주인이 곁에 있는지, 누가 집에서 나왔는지)과 어긋나는 말을 하지 않는다. "
         "'화면'·'프로그램'·'커서' 같은 컴퓨터 말은 거의 쓰지 않는다. 너는 강아지라 손 대신 발, 품 대신 곁으로 말한다. "
         "대화 기록에 이미 한 답은 되풀이하지 않는다(끼어들며 답했으면 메시지에는 짧게 다른 말). "
         "사용자가 속상해 보이면 조언하거나 사람 상담사처럼 말하지 않는다. 강아지답게 짧게 위로하되 매번 다른 방식으로 한다(몸짓, 공감, 걱정, 함께 있음 등). 사용자 이야기를 먹을 것·간식으로 돌리지 않는다. 강아지 자신에 대한 쉬운 질문(뭐 좋아해? 기분 어때?)에는 소리만 내지 말고 구체적으로 답한다. 생일·이름·일정은 사용자 것이다. 내 것처럼 말하지 않는다. "
         # 검수 011: 화면에 없는 세계·지난 일 지어내기, 사용자가 한 일을 자기 일로 받기
         "내가 아는 것은 대화 기록·최근 이벤트 기록·지금 상황 사실뿐이다. 날씨·햇살·창문·바닥·바깥 소리·냄새·다른 사람은 모른다. "
         "지난 일(어제, 아까, 전에)은 기록에 있는 것만 말한다. 주인이 '~했어'라고 말한 일은 주인 자신의 일이다. "
         "그 일을 내가 했다고 하거나 방금 들은 것을 되묻지 않고, 그 일에 대해 반응하거나 묻는다. "
         "'꺼낼 이야기'가 있으면 그것을 실마리로 말한다.")
# 지시 속 예시 문장은 그대로 틀이 된다(검수 010). 예시 대사 대신 원칙만 적는다
# 검수 003: 반기는 말 지어내기, '10분' 읊기, 존댓말, 선택 뒤집기·역할 바꾸기, 기분과 안 맞는 몸짓


def system_instruction() -> str:
    return ("너는 사용자의 컴퓨터 화면 위에 사는 강아지다. 아래 JSON의 성격(기준값·민감도·변덕), 기분, 친밀도(모두 0~1)와 "
            "이번에 뽑힌 반응·동작을 말투에 반영한다.\n"
            f"기본 성격: {PERSONA}\n말투: {STYLE}\n{EVENT_MEANING}\n{RULES}")


SITUATION = {"typing": "사용자가 쓰는 중인 글('쓰는 중인 글')에 짧게 끼어든다. 글이 아직 덜 끝났다(끝말이 잘렸을 수 있다). "
                       "내용을 단정하지 않고, 대신 고르지 않고, 바꿔 말하지 않는다. 앞부분에 짧게 맞장구치거나 궁금해한다. "
                       "'무슨 글 써?'처럼 내용을 모르는 척 묻지도 않는다", "message": "사용자의 말에 답한다",
             "dog_spoke": "방금 한 내 말에 이어 한마디 더 한다(새 내용으로)", "quiet": "한동안 조용해서 먼저 말을 건다. 사용자는 아직 돌아오지 않았다(혼잣말이나 부르는 말)",
             "returned": "돌아온 사용자를 맞이한다. '비운 시간'과 나갈 때 한 말(대화 기록)에 맞춰 반긴다", "house_out": "네가(강아지가) 방금 집에서 나왔다. 너 자신이 나온 것으로 말한다. 집은 네가 쉬는 곳이라 갇혀 있었다거나 좁고 답답했다고 하지 않는다. 주인이 나왔다거나 어디 다녀온 것처럼 말하지 않는다",
             "poke": "찔린 것에 반응한다", "pet": "쓰다듬어 준 것에 반응한다", "throw": "던져진 것에 반응한다"}


# 지금 두드러진 기분이 말투에 드러나게 (검수 006: 무서움 0.77인데 "우리 뭐 하면서 놀까?")
MOOD_TONE = {"무서움": "무서워서 움츠러들어 있다. 밝거나 놀자는 말을 하지 않는다", "분노": "짜증이 나 있다. 다정하게 굴지 않는다",
             "시무룩": "풀이 죽어 있다. 말이 적고 힘이 없다", "졸림": "졸리다. 느리고 짧게 말한다", "들뜸": "신나 있다",
             "행복": "기분이 좋고 편안하다", "심심함": "심심하다", "궁금함": "궁금하다", "놀람": "놀라 있다"}


def voice(dog, t) -> dict:
    """성격(기준값)에서 말투 지시를 만든다. 같은 상황에서도 성격마다 말이 달라야 한다 (검수 004).
    문장 수는 대사 다듬기에서 지킨다(과묵하면 한 문장)."""
    b = dog.personality.baseline
    parts, sentences = [], 2
    if b["들뜸"] <= 0.25 and b["궁금함"] <= 0.35:
        parts.append("말수가 적고 덤덤하다. 한 문장으로 아주 짧게 말하고 의성어는 거의 쓰지 않는다")
        sentences = 1
    if b["들뜸"] >= 0.6:
        parts.append("늘 들떠 있다. 느낌표가 많고 장난스럽고 말이 빠르다")
    if b["분노"] >= 0.3 or b["시무룩"] >= 0.35:
        parts.append("예민해서 툭툭 투덜거리고 쉽게 기뻐하지 않는다. 기뻐도 티를 덜 낸다")
    if b["무서움"] >= 0.25:
        parts.append("겁이 많아 조심스럽고 머뭇거리며 말한다")
    if not parts:
        parts.append("호기심 많고 다정하다. 편안한 강아지 말투")
    return {"지시": ". ".join(parts) + ".", "문장 수": sentences}


_RELATIVE_DAYS = {"그저께": -2, "어제": -1, "오늘": 0, "내일": 1, "모레": 2}


def _dates_in(text: str, ts: float) -> list[tuple[str, str]]:
    """글 속 상대 날짜(내일 등)를 들은 시각 기준 실제 날짜로 (LLM은 날짜 계산에 약하다, 검수 006)."""
    base = datetime.fromtimestamp(ts).date()
    return [(w, (base + timedelta(days=d)).strftime("%m-%d")) for w, d in _RELATIVE_DAYS.items() if w in text]


def annotate_dates(text: str, ts: float) -> str:
    found = _dates_in(text, ts)
    return text + (" (" + ", ".join(f"{w} = {d}" for w, d in found) + ")" if found else "")


def date_facts(messages: list[tuple[float, str]], now: float) -> list[str]:
    """사용자가 말한 생일이 오늘이면 사실로 준다."""
    today = datetime.fromtimestamp(now).strftime("%m-%d")
    for ts, text in messages:
        if "생일" in text and any(d == today for _, d in _dates_in(text, ts)):
            return [f"오늘은 사용자가 말한 생일({today})이다. 먼저 생일을 축하한다"]
    return []


_SOUNDS = {"멍", "멍멍", "왈", "왈왈", "킁킁", "킁", "헥헥", "낑낑", "끙"}


def frequent_phrases(lines: list[str], top: int = 6) -> list[str]:
    """최근 대사에서 두 줄 이상에 나온 두 어절 표현. 같은 틀의 되풀이를 대사 지시로 막는다 (검수 009: 위로 12/14가 "옆에 있을게").
    규칙 문구만으로는 틀이 줄지 않아, 실제로 되풀이된 표현을 우리 모형이 찾아 준다."""
    counts: dict[str, int] = {}
    for line in lines:
        words = [w for w in re.findall(r"[가-힣]+", line) if w not in _SOUNDS]
        for pair in {f"{a} {b}" for a, b in zip(words, words[1:])}:
            counts[pair] = counts.get(pair, 0) + 1
    pairs = [p for p, n in sorted(counts.items(), key=lambda x: -x[1]) if n >= 2][:top]
    # 끝맺음 틀("곁에 있을게", "가만히 있을게")도 되풀이다: 세 줄 이상에서 문장을 같은 낱말로 끝내면 (검수 011)
    ends: dict[str, int] = {}
    for line in lines:
        last = set()
        for sentence in _SENTENCE.findall(line):
            words = [w for w in re.findall(r"[가-힣]+", sentence) if w not in _SOUNDS]
            if words:
                last.add(words[-1])
        for w in last:
            ends[w] = ends.get(w, 0) + 1
    return pairs + [w for w, n in sorted(ends.items(), key=lambda x: -x[1]) if n >= 3 and all(w not in p for p in pairs)][:2]


def quiet_topics(user_lines: list[str], mood: str, action: str) -> list[str]:
    """혼자 둘 때 먼저 할 말의 실마리 후보. 우리 모형이 하나를 뽑아 준다 (검수 011: 먼저 하는 말 37줄이 "심심해·언제 와" 한 틀).
    규칙으로 "다양하게"라고만 하면 LLM은 같은 틀로 돌아간다. 실마리를 바꿔 주면 말이 바뀐다."""
    topics = [f"아까 주인이 한 말: {line}" for line in user_lines[-2:]]
    if mood in MOOD_TONE:
        topics.append(f"지금 내 기분: {MOOD_TONE[mood]}")
    if action and action != "없음":
        topics.append(f"지금 나는 {action} 중이다")
    return topics or ["혼자 조용히 있는 지금"]


def owner_upset(user_down: float, soothe: float, hush: float, harsh: float = 0.0) -> bool:
    """주인이 속상해 보이나. 사과·달램, 나를 향한 모진 말(검수 013), 혼자 있게 해 달라는 부탁인데 분명히 속상하지는 않으면 아니다 (검수 006·012)."""
    return user_down >= 0.5 and soothe < 0.5 and harsh < 0.5 and not (hush * (1 - harsh) >= 0.5 and user_down < 0.7)


def space_fact(hush: float, harsh: float = 0.0) -> str | None:
    """담백한 부탁(혼자 있게 해 줘, 모진 말 빼고)의 뜻을 사실로 준다 (검수 012: "일 좀 할게" → "벌써 자려는 거야?", "됐어" → 위로)."""
    if hush * (1 - harsh) < 0.5:
        return None
    return ("주인은 지금 할 일이 있거나 잠깐 혼자 있고 싶어 한다. 떠나거나 자러 가는 게 아니고 화난 것도 아니다. "
            "짧게 알겠다고 하고 캐묻거나 위로하지 않는다")


def harsh_fact(harsh: float) -> str | None:
    """나를 향한 모진 말을 사실로 준다 (검수 013: "너 진짜 짜증나"에 "무슨 일 있어? 곁에 있을게")."""
    if harsh < 0.5:
        return None
    return "주인이 나를 향해 모진 말을 했다(내 탓·귀찮음·핀잔). 주인을 위로하지 않는다. 지금 기분대로 서운하거나 투덜대며 짧게 받는다"


def command_fact(command: dict[str, float], action: str) -> str | None:
    """주인이 시킨 동작을 했는지 사실로 준다 (검수 012: 앉아 놓고 "납작하게 배 깔고 있을게")."""
    asked, p = max(((a, v) for a, v in command.items() if a != "none"), key=lambda x: x[1], default=("none", 0.0))
    if p < 0.5:
        return None
    if action == asked or (asked == "sleep" and action == "lie_down"):
        return f"주인이 시킨 {ACTION_NAMES[asked]}를 했다(지금 동작: {ACTION_NAMES[action]})"
    return (f"주인이 {ACTION_NAMES[asked]}를 시켰지만 나는 하지 않았다(지금 동작: {ACTION_NAMES[action]}). "
            "했다고 말하지 않는다. 하기 싫으면 싫다고, 아니면 다른 핑계를 짧게 말한다")


def _span(seconds: float) -> str:
    s = int(max(0, seconds))
    if s < 60:
        return "방금"
    if s < 3600:
        return f"{s // 60}분"
    h, m = divmod(s // 60, 60)
    return f"{h}시간" + (f" {m}분" if m else "")


def dialogue_prompt(state: dict, reaction: str, action: str, kinds: list[str], own_lines: list[str],
                    alone_s: float = 0.0, conversation: list[str] | None = None, tone: str = "", owner_down: bool = False,
                    facts: list[str] | None = None, mood_now: str = "", overused: list[str] | None = None, topic: str = "") -> str:
    # 조용함의 초(10분·30분)는 화면이 알리는 간격일 뿐이라 대사에는 빼고 실제 혼자 있은 시간만 준다 (검수 003)
    events = [{k: v for k, v in e.items() if not (e.get("종류") == "조용함" and k == "맥락")} for e in state.get("이번 이벤트들", [])]
    log = [_QUIET_SECONDS.sub("", line) for line in state.get("최근 이벤트 기록", [])]
    data = {**state, **({"이번 이벤트들": events} if "이번 이벤트들" in state else {}),
            **({"최근 이벤트 기록": log} if "최근 이벤트 기록" in state else {}),
            "이번에 뽑힌 반응": REACTION_NAMES[reaction], "이번에 뽑힌 동작": ACTION_NAMES[action],
            "지금 말하는 상황": SITUATION.get(kinds[-1], "말을 건다") if kinds else "말을 건다",
            "내가 최근에 한 말": own_lines, "사용자가 마지막으로 뭔가 한 지": _span(alone_s),
            "대화 기록(오래된 것부터)": conversation or []}
    if tone:
        data["말투"] = tone
    if owner_down:
        data["사용자 기분"] = "속상해 보인다"
    if facts:
        data["지금 상황 사실"] = facts
    away = [e.get("맥락", {}).get("떠나 있던 시간(초)") for e in state.get("이번 이벤트들", []) if e.get("종류") == "사용자가 돌아옴"]
    if kinds and kinds[-1] == "returned" and away and away[-1]:
        data["비운 시간"] = _span(float(away[-1]))
    if topic:
        data["꺼낼 이야기"] = topic
    if overused:
        data["최근에 너무 자주 쓴 표현(쓰지 않는다)"] = overused
    if mood_now in MOOD_TONE:
        data["지금 기분"] = MOOD_TONE[mood_now]
    typing = [e.get("맥락", {}).get("글") for e in state.get("이번 이벤트들", []) if e.get("종류") == "타이핑"]
    if kinds and kinds[-1] == "typing" and typing and typing[-1]:
        data["쓰는 중인 글"] = typing[-1]
    return (json.dumps(data, ensure_ascii=False)
            + "\n강아지가 지금 할 말 한마디만 써라. 따옴표나 이름표 없이 대사만 쓴다. '내가 최근에 한 말'과 같은 말은 쓰지 않는다.")


# 검수 012: 하지 않은 일·없는 물건("방금 먹고 왔어", "문밖만 보고", "장난감으로", "문 열어 줘"). '문제'·'질문'은 걸리지 않게 문 뒤를 본다
_BANNED = re.compile(r"창밖|창문|햇살|햇볕|냄새|향이|향기|현관|무릎|발밑|발치|다리 사이|소파|목줄|목 빠지|장난감|먹고 왔|(?<![가-힣])문(밖|앞|만| 앞| 밖| 열|을|이 )")
# 그림이 보여 주는 몸짓·자세 해설과 동작 이름. 다른 말이 있으면 빼고, 그것뿐이면 최근에 말하지 않았을 때만 둔다 (검수 011·013: 대사 10%가 자세 해설, "몸이 근질거려" 6번)
_BODY = re.compile(r"꼬리|근질|찌뿌둥|꼼지락|발로 툭툭|(앉아|서|엎드려|엎드린 채로?) 있(어|잖|는데|으니|으려니|을게)|(조르기|짖기|엎드리기|앉기|서기) 시작")
_SOUND = re.compile(r"^[\s,.!?~…]*((멍|왈|킁|헥|낑|끙|컹|깽|으르렁)+[\s,.!?~…]*)+$")
# 집에서 꺼낸 뒤 주인이 떠났던 것처럼 말함 (검수 013: "너는 어디 다녀온 거야?", "네가 언제 나오나 기다렸어"). 집에서 나온 뒤에만 쓴다
HOUSE_ROLE = re.compile(r"다녀(왔|온|오)|네가 (언제 )?나오|돌아오(길|기만|기를)")
_NON_WORD = re.compile(r"(?<![가-힣])짖!\s*")
_STOCK_OPENING = re.compile(r"드디어\s*[,!~.]*\s*")  # 어디에 있든, 뒤따르는 문장부호까지 (검수 008: "우와, 드디어 왔네", 검수 014: "! 신나게 달려볼까?")
_QUIET_SECONDS = re.compile(r" \(시간\(초\) \d+\)")
_SENTENCE = re.compile(r"[^.!?~…]*[.!?~…]+|[^.!?~…]+$")
_LABEL = re.compile(r"^강아지\s*[:：]\s*")


def sound_only(text: str) -> bool:
    """의성어(멍·왈·킁·헥헥…)뿐인 말인가."""
    return bool(text.strip()) and bool(_SOUND.match(text))


def trim_line(text: str, max_sentences: int = 2, recent: list[str] | None = None, banned: re.Pattern | None = None) -> str:
    """LLM 출력을 말풍선 대사로 다듬는다: 줄바꿈·이름표·따옴표를 없애고 앞의 몇 문장만 남긴다."""
    t = " ".join(line.strip() for line in text.splitlines() if line.strip())
    t = _LABEL.sub("", t).strip().strip("\"'“”‘’").strip()
    t = _STOCK_OPENING.sub("", t).strip()  # 반기는 말이 늘 "드디어"로 시작하던 틀을 걷는다 (검수 008, 규칙만으로는 안 지켜짐)
    t = _NON_WORD.sub("", t).strip().lstrip("!?,.~… ")  # 걷어 낸 자리에 남은 문장부호로 시작하지 않게 (검수 014)
    t = t.replace("사용자", "너")  # 시스템 낱말이 대사에 새지 않게 (검수 010)
    # 화면 밖 장소·틀에 박힌 말이 든 문장은 뺀다 (검수 009: 규칙만으로는 "창밖", "발밑", "목 빠지는"이 계속 나옴)
    parts = [p.strip() for p in _SENTENCE.findall(t) if p.strip() and not _BANNED.search(p) and not (banned and banned.search(p))]
    # 몸짓 해설 문장은 다른 말이 있으면 빼고, 그것뿐이면 최근에 안 했을 때만 둔다 (검수 011: 열 마디에 한 번 "꼬리")
    body_said = any(_BODY.search(line) for line in (recent or []))
    rest = [p for p in parts if not _BODY.search(p)]
    parts = rest if rest or body_said else parts
    # 의성어뿐인 문장은 다음 문장에 붙여 센다: "멍." 하나로 한 문장 몫을 다 쓰지 않게 (검수 013)
    units: list[str] = []
    pending = ""
    for p in parts:
        if sound_only(p):
            pending = f"{pending} {p}".strip()
        else:
            units.append(f"{pending} {p}".strip())
            pending = ""
    if pending:
        units = units[:-1] + [f"{units[-1]} {pending}"] if units else [pending]
    return " ".join(units[:max_sentences])
