# ARCHITECTURE

TamagotchiChatBot의 구조와 동작 원리다. 지금 코드가 **어떻게 동작하는지**만 적는다. 왜 그렇게 바뀌었는지(검수 회차별 지적과 수정)는 [검수 요약](docs/review/summary.md)과 각 절에 링크한 스펙에 있다.

> 기준: 브랜치 `feat/rollback`, 프로토콜 v4. 숫자는 `brain/brain/tuning.py`·`app/src/body/*.ts`의 현재 값이다. 표에 "잠정값"이 없어도 대부분 시뮬레이션·검수로 맞춘 값이고, 근거는 코드 주석에 있다.

## 1. 한눈에 보기

```mermaid
flowchart LR
  U["사용자"] -->|"입력, 클릭, 자리 비움"| DET["화면<br>이벤트 판정"]
  DET -->|"이벤트"| DEC["두뇌<br>판단"]
  ST[("두뇌<br>강아지 상태")] <-->|"읽고 바꾼다"| DEC
  JEV["Jev<br>판단 분포"] -.-> DEC
  GEM["Gemini<br>대사"] -.-> DEC
  DEC -->|"반응, 동작, 대사"| OUT["화면<br>그리기"]
  ST -->|"움직임 경향"| BEH["화면<br>평소 행동 뽑기"]
  BEH --> OUT
  OUT --> U
  OUT -->|"말풍선이 뜸"| DET
```

1. **강아지 상태**는 기분 9개뿐이다. 두뇌가 갖고 저장한다 (4절).
2. **이벤트가 오면** 두뇌가 Jev에 상황을 묻고, 그 분포와 우리 모형으로 기분을 바꾼 뒤 반응·동작·말할지를 확률로 뽑는다. 말하기로 뽑히면 Gemini가 대사를 쓴다 (5·6절).
3. **이벤트가 없으면** 기분은 고정된 자리로 천천히 돌아간다 (4.2).
4. **평소 움직임**은 두뇌가 기분으로 경향만 정하고, 화면이 그 경향으로 초 단위 행동을 혼자 뽑는다 (7절).

화면(Tauri 앱, `app/`)과 두뇌(파이썬 서비스, `brain/`)는 localhost WebSocket으로 통신한다. 두뇌는 화면을 모르므로 화면만 바꿔 다른 기기로 옮길 수 있다 ([0012](docs/decisions/0012-brain-as-frontend-independent-service.md)). 그 예로 **웹 프로토타입**이 있다: 두뇌의 웹 모드가 브라우저용 화면과 WebSocket을 한 포트에서 함께 낸다 ([0017](docs/decisions/0017-web-prototype-brain-serves-page.md)). 웹은 접속마다 강아지가 새로 태어나고 저장하지 않는다 ([0021](docs/decisions/0021-web-dog-per-connection.md)).

## 2. 원칙

| 원칙 | 뜻 | 근거 |
|---|---|---|
| 두뇌는 화면을 모른다 | 둘은 [프로토콜](docs/brain-protocol.md)로만 이어진다 | [0012](docs/decisions/0012-brain-as-frontend-independent-service.md) |
| 이벤트가 판단의 단위 | Jev는 이벤트가 올 때만 부른다. **언제** 이벤트를 낼지는 화면이 정한다 | [0013](docs/decisions/0013-event-driven-brain-with-event-log.md) |
| 이벤트 기록이 기억 | 대화·찌르기·돌아옴·강아지 반응이 한 줄로 쌓인다 | [0013](docs/decisions/0013-event-driven-brain-with-event-log.md) |
| Jev는 분포, 결정은 확률 모델 | Jev가 준 확률과 우리 모형으로 뽑는다. 같은 상황에서도 가끔 다르게 행동한다 | [0014](docs/decisions/0014-probabilistic-model-with-jev-distributions.md) |
| 뜻이 분명한 일은 우리 모형이, 글은 Jev가 | 글 없는 사건의 기분, 동작 선택, 이어 말하기는 우리 모형이 정한다. 글이 일으키는 기분은 Jev 질문 하나가 정한다 | [0016](docs/decisions/0016-action-model-ours-first.md), [0019](docs/decisions/0019-message-mood-from-one-question.md) |
| 대사의 사실은 우리 모형이 | 주인이 곁에 있는지, 주인 말의 뜻, 날짜처럼 LLM이 틀리기 쉬운 것은 두뇌가 사실 문장으로 준다 | [검수 요약](docs/review/summary.md) |
| 빠른 일은 화면, 느린 일은 두뇌 | 초 단위 행동 선택은 화면이, 분 단위 경향은 두뇌가 맡는다 | [스펙 6.5](docs/superpowers/specs/2026-10-15-brain-v2-design.md) |

## 3. 구성 요소

| 구성 요소 | 맡는 일 | 위치 |
|---|---|---|
| 화면 | 강아지 그리기, 입력·클릭·창 감지, 이벤트 판정, 평소 행동 뽑기, 입력창·설정 창 | `app/` (Tauri: Rust + TypeScript) |
| 웹 화면 (프로토타입) | 같은 몸 로직을 브라우저 창 안에서. 창 위 올라앉기·단축키·트레이 없음, 입력창(집 위에 작게)과 설정 패널은 페이지 안 | `app/web.html`, `app/src/web/` |
| 두뇌 | 강아지 상태, 판단, 기분 시계, 이벤트 기록, API 키 보관 | `brain/` (파이썬, WebSocket 서버) |
| Jev | 상황에 대한 판단 분포(선택지 확률, 예/아니오 확률). 대사는 쓰지 않는다 | TypeSafe System One ([요약](docs/references/typesafe-jev.md)) |
| Gemini | 대사 한마디 | `gemini-3.1-flash-lite` ([0007](docs/decisions/0007-dialogue-llm.md)) |

**프로토콜 v4** ([전체](docs/brain-protocol.md)): 화면 → 두뇌는 `hello`(인증), `event`, `set_key`, `clear_history`, `reset`, `get_state`, `get_log`. 두뇌 → 화면은 `reaction`(반응·동작·대사), `status`(AI 상태), `movement`(움직임 경향), `state`, `log`.

**시간 척도**: 과정마다 빠르기가 크게 다르다. 빠른 과정을 볼 때는 느린 과정을 상수로 봐도 된다. 화면과 두뇌의 분담이 여기에 기댄다.

| 과정 | 빠르기 | 담당 |
|---|---|---|
| 행동 하나 (걷기, 앉기 등) | 3~20초 | 화면 |
| 이벤트 사이 간격 | 0.6초(타이핑) ~ 30분(조용함) | 화면 |
| 판단 한 번 | Jev ≤ 3초, 말하면 + Gemini ≤ 5초 | 두뇌 |
| 기분이 절반 풀림 | 놀람 36초, 궁금함 5분, 분노 6분, 들뜸 6분, 무서움 9분, 시무룩 21분, 행복 27분, 심심함 33분, 졸림 48분 | 두뇌 |

## 4. 강아지 상태

### 4.1 무엇을 갖나

| 값 | 범위 | 어떻게 변하나 |
|---|---|---|
| 기분 9개: 심심함, 졸림, 들뜸, 시무룩, 분노, 궁금함, 놀람, 무서움, 행복 | 0~1 | 돌아갈 자리로 풀리고(4.2), 이벤트에 튄다(4.3) |

- 저장하는 것은 기분 9개와 갱신 시각뿐이다. 성격·관계·습관화·말수는 없다 ([0018](docs/decisions/0018-simplify-to-reaction-and-mood.md)).
- **돌아가는 자리 `REST`** (고정, 강아지마다 같다): 심심함 0.6, 졸림 0.3, 들뜸 0.4, 시무룩 0.2, 분노 0.1, 궁금함 0.5, 놀람 0.1, 무서움 0.1, 행복 0.4. "호기심 많고 수다스러운 강아지"를 숫자로 옮긴 값이다.
- 처음 기분은 `REST`다. 설정 창 **초기화**는 기분을 `REST`로 되돌리고 기록을 지운다. 키는 남는다.
- 예전 저장본을 읽으면 기분만 쓰고 나머지는 버린다.

### 4.2 시간이 흐를 때: 돌아갈 자리로 당겨진다

기분은 기분별 반감기로 고정 자리 `REST`에 돌아간다. 흔들림·하루 리듬은 없다 ([0020](docs/decisions/0020-minimal-brain-rules.md)).

```math
m_d \leftarrow R_d + (m_d - R_d)\, e^{-\ln 2 \cdot \Delta t / h_d}
```

$m_d$는 기분 $d$, $R_d$는 돌아가는 자리(`REST`), $h_d$는 반감기, $\Delta t$는 지난 갱신 뒤 흐른 시간이다.

- 반감기 $h_d$: 놀람 36초, 궁금함 5분, 분노 6분, 들뜸 6.3분, 무서움 9분, 시무룩 21분, 행복 27분, 심심함 33분, 졸림 48분.
- 계산은 값을 읽을 때(판단, 30초 기분 시계, 상태 조회) 위 식의 정확한 풀이로 한다. 읽는 간격과 상관없이 같은 결과가 나온다.
- 상세: [시간 모형](docs/superpowers/specs/2026-10-16-time-model-design.md), [기분 갱신 수식](docs/superpowers/specs/2026-10-16-mood-update-math-design.md), [단순화](docs/superpowers/specs/2026-10-20-simplify-brain-design.md).

### 4.3 이벤트가 올 때: 글 없는 사건은 우리 값, 글은 Jev

글 없는 사건은 **우리가 정한 평가값**만 쓰고, 글(메시지·타이핑)은 **Jev 기분 질문 하나**만 쓴다 ([0019](docs/decisions/0019-message-mood-from-one-question.md)).

```mermaid
flowchart LR
  F["글 없는 사건"] -->|"① 우리 평가값의 합"| S["신호"]
  M["메시지·타이핑"] -->|"② 0.3 × P_Jev(기분)"| S
  S --> O["③ 반대 기분 억제<br>오른 만큼 같은 양"]
  O --> C["④ 기분 += 신호<br>0~1로 자름"]
```

**① 우리 평가값** (글 없는 사건):

| 이벤트 | 평가값 |
|---|---|
| 찌르기 | 놀람 +0.20, 분노 +0.06, 궁금함 +0.03, 졸림 −0.12 |
| 던지기 (충격 i) | 무서움 +0.35i, 놀람 +0.10 + 0.15i, 분노 +0.05i, 행복·졸림 −0.10i |
| 쓰다듬기 | 행복 +0.12, 들뜸 +0.04, 분노·시무룩·무서움 −0.03 |
| 돌아옴 | 행복 +0.15, 들뜸 +0.22, 심심함 −0.10, 시무룩 −0.08, 졸림 −0.15 |
| 집에서 나옴 | 들뜸 +0.08, 행복 +0.06 |
| 조용함 | 심심함 +0.04 |
| 강아지 자기 말, 집에 들어감 | 없음 |

- 던지기의 충격 말고는 고정값이다. 한 묶음에 여러 사건이 있으면 그냥 더한다(찌르기 3번이면 놀람 +0.6).

**② Jev 기분** (메시지·타이핑): Jev 질문 `change`는 "이 글이 강아지에게 새로 일으키는 기분"을 기분 9개 + 없음 중에서 묻는다. 지난 일로 남은 기분은 시간 회복이 맡으므로, 지금 기분과 최근 기록은 빼고 글 내용만 보라고 지시한다(그러지 않으면 모욕 뒤의 사과에도 분노를 다시 얹었다). 묶음에 글이 하나라도 있으면 한 번 더한다. 오르기만 하고, 오른 합은 최대 0.3(없음이 0일 때)이다.

**③ 반대 기분 억제**: 반대 쌍 $\mathcal{O}$ = {무서움↔행복·들뜸, 분노↔행복, 시무룩↔들뜸·행복, 졸림↔들뜸}에서 한쪽이 오른 만큼 반대쪽에서 같은 양을 뺀다. 그래서 "미안해"로 행복이 오르면 그만큼 시무룩·분노가 내려간다.

**④ 반영**: 0~1로 자른다. 여유 비례가 없어 기분이 0·1에 붙을 수 있다(시뮬레이션 고착 0.13, 사용자가 감수하기로 함).

①~④를 식으로 쓰면 다음과 같다.

```math
\begin{aligned}
s_d &= \sum_{e \in B_{\text{글 없음}}} a_d(e) \;+\; 0.3 \cdot P_{\text{Jev}}(d)\cdot \mathbb{1}[B \text{에 글이 있음}] \\
\tilde s_d &= s_d - \sum_{c\,:\,(c,d) \in \mathcal{O}} \max(s_c, 0) \\
m_d &\leftarrow \operatorname{clip}_{[0,1]}\!\left(m_d + \tilde s_d\right)
\end{aligned}
```

$B$는 이번 이벤트 묶음, $a_d(e)$는 위 표의 평가값, $P_{\text{Jev}}(d)$는 `change` 질문에서 기분 $d$의 확률이다.

- Jev가 실패하거나 키가 틀려도 ①의 평가값으로 기분·반응·동작은 낸다. 글의 기분 변화와 대사는 없다.
- 숫자 감각: 이벤트가 없으면 기분은 자리에 머문다. 세게 던지면 무서움 약 +0.3, 찌르면 놀람 +0.2, 분명한 메시지면 한 기분이 +0.2~0.3 오른다.

### 4.4 상태에서 계산하는 값 (저장하지 않음)

| 값 | 계산 | 쓰는 곳 |
|---|---|---|
| 두드러진 기분 | $\hat d = \arg\max_d (m_d - R_d)$. $m_{\hat d} - R_{\hat d} \ge 0.15$일 때만, 아니면 `calm` | 평소 모습(7절), 대사 말투(6절) |

## 5. 판단: 이벤트에서 행동까지

### 5.1 파이프라인

```mermaid
flowchart LR
  IN["상태 + 이번 이벤트들<br>+ 최근 기록 30줄"] --> JEV["Jev 질문 3개"]
  JEV --> DM["기분 변화 (4.3)"]
  DM --> R["반응"]
  R --> A["동작"]
  JEV -.-> A
  JEV -.-> S["말할지"]
  S -->|"말함"| U["Gemini 대사 (6절)"]
  R --> U
  A --> U
```

| 결정 | 어떻게 정하나 |
|---|---|
| **반응** | $\hat d = \arg\max_d \tilde s_d$의 표출. $\tilde s_{\hat d} \ge 0.03$이어야 한다. 타이핑 중이면 늘 하나를 낸다(오른 게 없으면 궁금함) |
| **동작** | 아래 점수의 softmax에서 뽑는다 |
| **말할지** | 아래 확률로 동전을 던진다 |
| **대사** | 말하기로 뽑혔을 때만 Gemini가 쓴다 (6절) |

반응 어휘(기분 → 반응): 심심함 지루함, 졸림 하품, 들뜸 신남, 시무룩 서운함, 분노 짜증, 궁금함 궁금함, 놀람 놀람, 무서움 무서움, 행복 행복.

**동작** (서기, 앉기, 엎드리기, 잠, 조르기, 짖기, 없음 = 하던 대로):

```math
\begin{aligned}
z_a &= b_a + \sum_{e \in B} p_a(e) + 5\sum_d w_{ad}\,(m_d - R_d) + 1.5\, r_a(\rho)
      + 1.5 \log\!\left(P_{\text{Jev}}(a) + 0.05\right)\cdot \mathbb{1}[\text{메시지}]
      - 10 \cdot \mathbb{1}[a = \text{잠},\; m_{\text{졸림}} - R_{\text{졸림}} < 0.1] \\
P(a) &= \frac{e^{z_a}}{\sum_{a'} e^{z_{a'}}}
\end{aligned}
```

$b_a$는 동작 기본값, $p_a(e)$는 이벤트 사전값, $w_{ad}$는 기분→동작 친화도, $r_a(\rho)$는 이번 반응 $\rho$의 동작 친화도다.

- Jev 동작 판단은 메시지에만 쓴다. "앉아"처럼 글 내용이 동작을 정할 수 있기 때문이다 ([0020](docs/decisions/0020-minimal-brain-rules.md)).
- 친화도 예: 졸림 → 잠·엎드리기, 분노 → 짖기, 분노 → 조르기 −1, 무서움 → 엎드리기, 무서움 → 조르기 −2. 표는 `tuning.py`의 `MOOD_ACTION`·`REACTION_ACTION`·`EVENT_ACTION`.
- 강아지 자기 말 뒤에는 동작을 뽑지 않는다('없음').
- 상세: [동작 모형](docs/superpowers/specs/2026-10-16-action-model-design.md), [0016](docs/decisions/0016-action-model-ours-first.md).

**말할지**:

```math
P(\text{말함}) = \sigma\!\left(\operatorname{logit} P_{\text{Jev}}(\text{말함}) + \beta_k - n\right), \qquad n < 3
```

$\sigma$는 시그모이드, $\beta_k$는 이벤트 종류 $k$의 보정값, $n$은 사용자 입력 없이 연달아 말한 횟수다. $n \ge 3$이면 0이다.

- **0이 되는 때**: 연달아 3번 말했을 때, 집에 들어가는 순간, Jev 실패·키 오류, 이번 메시지를 치는 동안 이미 끼어들었거나 친 글이 15자 미만일 때.

| 이벤트 종류 | β | 목표 |
|---|---|---|
| 메시지 | +1.70 | 메시지에 85% 대답 |
| 조용함 | −0.73 | 말할 확률 약 1/3 → 30분에 한 번쯤 먼저 말 걸기 |
| 타이핑 | −0.77 | 30% 끼어들기 |
| 강아지 말이 뜸 | (쓰지 않음) | 이어 말하기는 5.4가 정한다 |
| 그 밖 | 0 | |

β는 9절의 시뮬레이션으로 맞춘 값이다.

### 5.2 Jev 질문

질문 정의와 선택지 문구는 `brain/brain/questions.py` 한곳에 둔다. 문구를 바꾸면 Jev를 다시 녹화하고 보정값을 다시 맞춘다(9절).

| 키 | 형식 | 묻는 것 | 쓰는 곳 |
|---|---|---|---|
| `action` | 선택 7개 | 강아지가 지금 할 동작 | 메시지의 동작 점수 |
| `speak` | 예/아니오 | 지금 강아지가 말할 차례인가 | 말할 확률의 출발점 |
| `change` | 선택 10개 | 이 글이 **새로** 일으키는 기분 (기분 9개 + 없음). 지금 기분과 최근 기록은 빼고 글 내용만 보라고 지시한다 | 메시지·타이핑의 기분 변화 (4.3) |

Jev에 넘기는 상황(`jev_state`): 강아지 한 줄 설명("호기심 많고 수다스러운 강아지. 사용자를 좋아한다."), 지금 시각, 이번 이벤트들, 최근 이벤트 기록 30줄, 기분. 수치는 소수 둘째 자리다.

### 5.3 처리 순서

두뇌는 판단을 **한 번에 하나씩** 한다. 판단 중에 온 이벤트는 쌓아 두었다가 끝나면 **한 묶음으로** 다음 판단에 넣는다. 이벤트가 몰려도 Jev는 판단 한 번에 한 번만 불린다.

```mermaid
stateDiagram-v2
  direction LR
  state "대기" as Idle
  state "판단 (Jev)" as Judging
  state "말하기 (Gemini)" as Speaking
  [*] --> Idle
  Idle --> Judging: 쌓인 이벤트 있음
  Judging --> Idle: 말 안 함
  Judging --> Speaking: 말함
  Speaking --> Idle: 대사 보냄, Gemini 실패
  Judging --> Idle: 집에 들어감 (취소)
  Speaking --> Idle: 메시지 옴, 집에 들어감 (취소)
```

- 화면에는 반응·동작을 먼저 보내고(`reaction`), 대사는 Gemini가 끝나면 따로 보낸다. 판단 직후 움직임 경향도 다시 계산해 문턱을 넘으면 보낸다.
- **취소**: 집에 들어가면 하던 판단과 쌓인 이벤트를 버린다. 대사를 만드는 중에 사용자가 메시지를 보내면 그 대사를 버린다.
- **판단할 수 없을 때**: 화면이 끊겼거나 키가 없으면 쌓인 이벤트를 버린다. 이벤트 기록에는 남아 다음 판단의 "최근 기록"으로 들어간다.

두뇌는 판단 사이에 **흐름 상태**를 기억한다. 모두 메모리에만 있다.

| 상태 | 켜지는 때 | 꺼지는 때 | 효과 |
|---|---|---|---|
| 연달아 말한 횟수 | 강아지가 말함 | 강아지 말 말고 다른 이벤트 | 말할 확률 감점, 3번이면 0 |
| 끼어듦 | 이번 메시지를 치는 동안 끼어들었다 | 메시지 보냄 | 끼어들기 0 |
| 자리 비움 | 30분 간격 조용함 | 사용자 행동 | 대사 사실 "주인은 자리를 비웠다" |
| 집 안 | 집에 들어감 | 집에서 나옴 | 판단·움직임 경향 보내지 않음 |

### 5.4 이어 말하기

강아지가 말하면 화면이 말풍선을 띄우고 "강아지 말이 뜸"(`dog_spoke`) 이벤트를 보낸다. 이 이벤트가 다시 판단을 부르므로 **강아지의 말이 다음 말을 부를 수 있다.**

```mermaid
flowchart LR
  SPK["강아지가 말함<br>연달아 횟수 k"] -->|"말풍선이 뜸"| JD{"또 말할까"}
  JD -->|"확률 q_k"| SPK
  JD -->|"1 − q_k, 또는 3번째"| STOP["흐름 끝"]
```

```math
q_k = 0.1 \times 0.3^{\,k-1}, \qquad k < 3
```

- Jev의 말할 확률은 쓰지 않는다. 우리 모형이 정한다. 세 마디는 드물다. 연달아 3번에서 끊는다. 0.1(`chain_base`)은 9절의 시뮬레이션으로 맞춘다.
- 사용자 입력이나 다른 이벤트가 오면 횟수가 0이 되어 새 흐름이다.

## 6. 대사 만들기

Gemini는 강아지 대사 **한마디**만 쓴다. 두뇌가 지시와 데이터를 정리해 주고, 결과를 다듬는다. 지시·문구는 `brain/brain/persona.py` 한곳에 둔다.

```mermaid
flowchart LR
  SYS["시스템 지시<br>강아지 설명, 말투, 이벤트 뜻, 대화 규칙"] --> G["Gemini"]
  DATA["데이터 (JSON)<br>상태·이벤트·뽑힌 반응·동작<br>대화 기록·사실·실마리"] --> G
  G --> T["다듬기"]
  T --> OUT["말풍선"]
```

**시스템 지시**: 강아지 한 줄 설명("호기심 많고 수다스러운 강아지"), 반말에 의성어를 섞는 말투, 이벤트의 뜻(던지기 = 네가 던져졌다 등), 대화 규칙(물으면 먼저 답한다, 고른 것을 뒤집지 않는다, 화면에 없는 장소·물건을 말하지 않는다 등).

**데이터**:

| 항목 | 내용 |
|---|---|
| Jev와 같은 상황 | 강아지 설명·기분·지금 시각·이번 이벤트들·최근 이벤트 기록 |
| 이번에 뽑힌 반응·동작 | 대사가 말하는 동작은 이것과 같아야 한다 |
| 지금 말하는 상황 | 이벤트 종류별 지시(끼어들기는 짧게 맞장구, 메시지는 답한다, 조용함은 먼저 말을 건다 등) |
| 대화 기록 | 실제로 오간 말 최근 20줄(시각 포함). "내일·오늘·어제"에는 실제 날짜를 붙인다 |
| 내가 최근에 한 말 | 최근 대사 5줄 |
| 지금 기분 | 두드러진 기분의 말투(무서우면 움츠러들어 밝은 말을 하지 않는다, 화나면 다정하게 굴지 않는다 등) |
| 사용자가 마지막으로 뭔가 한 지 | 예: "1시간" |
| 최근에 너무 자주 쓴 표현 | 최근 대사 40줄에서 두 줄 이상 되풀이된 두 어절, 세 줄 이상 같은 끝맺음 |
| 꺼낼 이야기 | 조용함일 때만: 아까 주인이 한 말, 지금 기분, 지금 동작 중 하나를 뽑아 준다 |
| 지금 상황 사실 | "주인이 방금 돌아왔다" / "주인은 자리를 비웠다" / "주인은 곁에 있다" 중 하나 |

**다듬기** (`trim_line`): 줄바꿈·"강아지:" 이름표·따옴표를 없애고 앞의 두 문장만 남긴다.

## 7. 평소 움직임

두뇌는 **기분으로 경향만** 정한다. 화면은 그 경향으로 **다음 행동과 머무는 시간을 혼자 뽑는다.** 기분은 분 단위, 행동은 초 단위라 행동 수십 개 동안 경향은 사실상 그대로다.

```mermaid
flowchart LR
  subgraph SLOW["두뇌 (분~시간)"]
    X["기분"] --> TH["경향<br>범주 가중치, 달리기 비율,<br>머무는 시간 배율, 두드러진 기분"]
  end
  subgraph FAST["화면 (초)"]
    CAT["다음 행동 뽑기"] --> DW["머무는 시간만큼"]
    DW --> CAT
  end
  TH -->|"크게 바뀌면 전송"| CAT
  CTX["커서, 창, 클릭"] -.-> CAT
```

### 7.1 두뇌: 경향 계산

```math
\begin{aligned}
\Delta_d &= m_d - R_d \\
W_c &= W^0_c \exp\!\Big(4 \sum_d v_{cd}\,\Delta_d\Big) \\
\text{달리기 비율} &= \sigma\!\left(\operatorname{logit} 0.2 + 4\,(1.5\,\Delta_{\text{들뜸}} - \Delta_{\text{졸림}} - 0.5\,\Delta_{\text{무서움}})\right) \\
\text{머무는 시간 배율} &= \exp\!\left(4\,(\Delta_{\text{졸림}} + \Delta_{\text{시무룩}} - \Delta_{\text{들뜸}} + 0.5\,\Delta_{\text{행복}})\right)
\end{aligned}
```

$W^0_c$는 범주 기본값(쉬기 0.6, 잠 0.08, 돌아다니기 0.4, 사용자 곁으로 0.18, 놀기 0.12, 구경하기 0.2), $v_{cd}$는 기분→범주 친화도다.

- 친화도 예: 들뜸 → 놀기 1.5·돌아다니기, 졸림 → 쉬기·잠, 무서움 → 쉬기, 분노 → 돌아다니기(사용자를 피함), 궁금함 → 구경하기·사용자 곁으로. 표는 `tuning.py`의 `MOVE_MOOD`.
- 기분은 `REST` 대비로 4배 크게 본다. 들뜸이 평소보다 0.3 높으면 놀기·돌아다니기가 3배쯤, 달릴 확률이 0.2 → 0.5가 된다. 행복은 느긋한 기쁨이라 달리지 않는다.
- **전송**: 30초 기분 시계와 판단 직후에 다시 계산한다. 두드러진 기분이 바뀌었거나, 가중치·머무는 시간 배율이 30% 넘게, 달리기 비율이 0.1 넘게 바뀌었을 때만 보낸다. 집에 있는 동안은 보내지 않는다.

### 7.2 화면: 행동 뽑기

행동 하나가 끝나면 다음 행동을 뽑는다. 다음 행동은 직전 행동과 무관하게 같은 분포에서 뽑고, 머무는 시간은 행동마다 따로 뽑는다(반-마르코프 과정).

| 행동 | 가중치 | 후보 조건 | 머무는 시간 |
|---|---|---|---|
| 커서로 다가가기 / 따라가기 | 사용자 곁으로 × ⅔ / × ⅓ | 커서가 450px 안 | 도착까지 / 5~10초 |
| 커서 사냥 | 놀기 | 커서가 450px 안 | 최대 6초 |
| 창에 올라앉기 / 창 옆에서 구경 | 구경하기 × ½ / × ½ | 주변에 창이 있음 | 도착 뒤 8~20초 / 6~12초 |
| 제자리 쉬기 | 쉬기 | 늘 | 3~10초 × 머무는 시간 배율 |
| 낮잠 | 잠 | 늘 | 8~20초 × 머무는 시간 배율 |
| 돌아다니기 | 돌아다니기 | 늘 | 80~400px 떨어진 곳에 도착까지. 달리기 비율 확률로 뜀 |

- 최근 3초 안에 450px 안에서 클릭이 있었으면 커서 관련 행동이 4배가 된다.
- **끼어드는 것들**: 찌르기, 잡기·던지기, 두뇌가 준 동작, 집 들어가기는 지금 행동을 끊고 먼저 실행된다.
- **듣는 자세**: 타이핑이 시작되면 두뇌를 기다리지 않고 입력창 쪽을 바라보고, 250px보다 멀면 30% 확률로 몇 걸음 다가온다.
- 사용자 입력이 3분 없으면 그 자리에서 잔다. 설정의 "쉬기"를 켜면 경향과 상관없이 잔다. 두뇌가 없으면 기본 경향으로 움직인다.

## 8. 이벤트 판정 (화면)

화면은 입력 신호를 주기적으로 읽어 이벤트로 바꾼다. 이벤트의 **뜻**은 프로토콜이, **언제 낼지**는 화면이 정한다 ([0013](docs/decisions/0013-event-driven-brain-with-event-log.md)).

| 이벤트 | 내는 때 | 읽는 주기 |
|---|---|---|
| 타이핑 | 마지막 입력 뒤 0.6초 멈춤, 또는 지난번보다 10자 넘게 바뀜 | 100ms |
| 메시지 보냄 | Enter | 즉시 |
| 강아지 말이 뜸 | 말풍선을 띄운 직후 | 즉시 |
| 조용함 | 마지막 이벤트 뒤 10분(자리에 있음) / 30분(비움). 계속 조용하면 그 간격으로 반복 | 100ms |
| 돌아옴 | 1분 넘게 입력이 없다가 다시 입력 | 1초 |
| 집에 들어감 / 나옴 | 집 클릭, 트레이, 단축키 | 프레임 |
| 찌르기 / 쓰다듬기 | 짧은 클릭 / 문지르기 | 50ms |
| 던지기 | 착지 순간. 충격 = min(1, 가장 세게 부딪힌 속도 ÷ 2000px/초) | 프레임 |

- 집에 있는 동안은 "집에서 나옴" 외에는 내지 않는다.
- 조용함 10분은 "30분에 한 번 먼저 말 걸기"를 조용함에서 말할 확률(약 1/3)로 나눈 값이다.

## 9. 보정값 맞추기: 녹화와 시뮬레이션

말하기 보정 β는 사람이 직접 써 보며 맞출 수 없으니 **가상 사용자 시뮬레이션**으로 맞춘다. Jev는 미리 녹화한 응답으로 대신한다.

```mermaid
flowchart LR
  REC[("Jev 녹화<br>대표 상황 120개")] --> SIM["가상 사용자와<br>며칠씩 시뮬레이션"]
  BETA["β, 이어 말하기 계수"] --> SIM
  SIM --> STAT["지표"]
  STAT -->|"목표와 다르면 조정"| BETA
```

| 단계 | 내용 |
|---|---|
| 녹화 (`sim.record`) | 이벤트 10종 × 기분 10가지(기본 + 한 기분만 0.9), 강아지 말은 연달아 횟수 3가지 = 120개 상황에서 Jev를 실제로 부른다. 메시지는 소식("오늘 점심 진짜 맛있었어")으로 녹화한다 |
| 시뮬레이션 (`sim.simulate`) | 지금 상태와 가장 가까운 녹화 응답을 쓴다. 가상 사용자는 평일 9~18시 자리(12~13시 점심), 분당 메시지 3%, 찌르기·쓰다듬기 0.5%, 던지기 0.2%, 강아지 말에 절반은 답한다 (잠정값) |
| 맞추기 (`--fit`) | β를 키우면 지표도 커지므로 이분 탐색한다. 10일, 3바퀴 |
| 확인 | 시드 1개, 시드 100개의 최소·중앙·최대 |

| 지표 | 목표 |
|---|---|
| 끼어들기 (타이핑에 말함) | 30% |
| 메시지에 답하기 | 85% |
| 먼저 말 걸기 (조용함에 말함) | 1/3 |
| 연달아 2번 이상 | 10% (실사용은 시뮬레이션의 약 2배라 실사용 20%를 노린다) |
| 가장 흔한 동작 비율 | ≤ 0.50 |
| 기분 고착 | ≤ 0.20 |

- 결과는 사람이 `tuning.py`에 옮긴다. `--fit`은 잡음이 커서 값 하나씩 훑어 확인하기도 한다.
- **한계**: 녹화 상황이 기분 10가지뿐이라 기분이 섞인 상태에서는 오차가 있다. 가상 사용자 행동은 잠정값이다.
- 실제 키로 짧게 써 보는 검증은 [검수 하네스](brain/review/README.md)가 한다.

## 10. 저장과 실행

| 무엇 | 어디 |
|---|---|
| 이벤트 기록, 강아지 상태 | `%APPDATA%\TamagotchiChatBot\brain\brain.db` (SQLite) |
| 두뇌 접속 정보 | `%APPDATA%\TamagotchiChatBot\brain\brain.json` (포트·토큰) |
| 두뇌 로그 | `%APPDATA%\TamagotchiChatBot\brain\logs\brain.log` (키·대화 내용은 쓰지 않음) |
| 판단 로그 | 두뇌 메모리, 최근 200개 (설정 창 로그 탭) |
| API 키 | Windows 자격 증명 관리자 (두뇌가 보관) |
| 화면 설정 | Tauri 앱 데이터 폴더 `settings.json` |

- 화면은 `brain.json`으로 접속을 시도하고, 안 되면 `brain/.venv`의 파이썬으로 두뇌를 띄운 뒤 2초마다 다시 접속한다.
- 두뇌는 시작할 때 다른 두뇌가 살아 있으면 바로 끝낸다. 같은 데이터를 두 두뇌가 쓰지 않게 하기 위해서다.
- 앱을 끄면 자기가 띄운 두뇌만 끈다. 두뇌가 죽어도 강아지는 기본 경향으로 계속 움직인다.

**웹 모드** (`uv run python -m brain.web`, 기본 `127.0.0.1:8787`):

```mermaid
flowchart LR
  B["브라우저"] -->|"GET / (app/dist-web)"| W["웹 모드 두뇌"]
  B -->|"GET /token (같은 출처)"| W
  B <-->|"/ws: Origin = Host일 때만"| W
```

- 판단은 PC 두뇌와 같은 `Brain`·`Link`다. 다만 **접속 하나마다** `Link`·`Brain`(메모리 저장소 `Store(None)`)·기분 시계를 새로 만들고, 끊기면 정리한다 ([0021](docs/decisions/0021-web-dog-per-connection.md)). 키는 시작 때 한 번 읽어 모두 같이 쓰고, 화면의 `set_key`는 받지 않는다. `…\brain\web\`에는 로그만 남는다. `brain.json`은 쓰지 않는다.
- 키는 자격 증명 관리자, 없으면 환경 변수 `TYPESAFE_API_KEY`·`GEMINI_API_KEY`(`config.py`).
- 웹 화면은 두뇌를 띄우지 않고 같은 주소로 2초마다 다시 접속한다(다시 접속하면 새 강아지). 자리 비움은 페이지 안 입력 1분 없음 또는 탭 숨김이다. 화면 설정은 `localStorage`.
- 서버 배포는 도커(`Dockerfile`, `compose.yaml`)다. 이미지가 웹 화면을 빌드하고 웹 모드 두뇌를 `0.0.0.0:8787`로 띄운다. 키는 `.env` 환경 변수, 로그는 `brain-data` 볼륨(`APPDATA=/data`).

## 11. 오류 처리

원칙: 강아지는 멈추지 않는다.

| 상황 | 동작 |
|---|---|
| 키 없음 | AI를 부르지 않고 이벤트를 판단하지 않는다. `status: no_keys`로 화면에 알린다("설정에서 키를 넣어 주세요") |
| 키 오류 | `status: bad_key`. 그 판단은 우리 평가값으로 기분·반응·동작만 내고 말하지 않는다 |
| Jev 실패·시간 초과(3초) | 우리 평가값으로 기분·반응·동작만 낸다. 말하지 않는다 |
| Gemini 실패·시간 초과(5초) | 대사 없이 반응·동작만 |
| 강아지 상태를 못 읽음 | 기본값으로 계속하고, 저장본을 덮어쓰지 않는다 |
| 기록 쓰기 실패 | 메모리로 계속 |

## 12. 코드 지도

| 위치 | 내용 |
|---|---|
| `brain/brain/model.py` | 확률 모델(순수 함수): 시간 흐름, 기분 변화, 반응·동작·말하기 확률, 움직임 경향 |
| `brain/brain/core.py` | 이벤트 대기열, 판단 순서, 흐름 상태, 대사의 사실 만들기, 기분 시계 |
| `brain/brain/questions.py` | Jev 질문 8개와 선택지 문구, Jev 상황 직렬화 |
| `brain/brain/persona.py` | 강아지 한 줄 설명, Gemini 지시·프롬프트, 사실 문장, 대사 다듬기 |
| `brain/brain/tuning.py` | 잠정값·방향표와 근거 주석 |
| `brain/brain/store.py` | 이벤트 기록·강아지 상태 (SQLite) |
| `brain/brain/clients.py` | Jev·Gemini 클라이언트, 실패를 키 오류/일시 실패로 정리 |
| `brain/brain/config.py` | 데이터 폴더, 키 읽기·쓰기 (환경 값을 읽는 유일한 곳) |
| `brain/brain/server.py`, `__main__.py` | WebSocket 서버, 실행·중복 실행 막기 |
| `brain/brain/web.py` | 웹 모드: 정적 파일·토큰·`/ws`를 한 포트에서, 출처 검사, 접속마다 강아지 하나 |
| `brain/sim/` | Jev 녹화, 시뮬레이터 |
| `brain/review/` | 검수 하네스: 시나리오 실행기, 상태 분석표, 커버리지 |
| `app/src/body/` | 강아지 상태 기계·행동 선택(`dog.ts`), 이벤트 판정(`events.ts`), 쓰다듬기·말풍선·집 등 순수 로직 |
| `app/src/character.ts` | 캐릭터 창: 그리기, 입력, 주기 작업, 두뇌 연결 |
| `app/src/input.ts`, `app/src/settings-page.ts` | 입력창, 설정 창 |
| `app/src/brain-link.ts`, `app/src/shared/brain-protocol.ts` | 두뇌 접속, 프로토콜 |
| `app/src-tauri/` | Rust 셸: 창, Win32 신호, 두뇌 실행 |
| `app/web.html`, `app/src/web/` | 웹 화면: 조립(`main.ts`), 같은 출처 접속(`link.ts`, `endpoint.ts`), 자리 비움(`presence.ts`), 설정(`prefs.ts`). 빌드 `npm run build:web` → `app/dist-web/` |

## 13. 문서 지도

모든 작업은 문서가 먼저다. 작업 규칙은 [`CLAUDE.md`](CLAUDE.md), 설치·실행은 [`README.md`](README.md).

| 문서 | 내용 |
|---|---|
| [`docs/vision.md`](docs/vision.md) | 제품 컨셉. 확정된 것과 미정인 것을 구분해 누적한다 |
| [`docs/glossary.md`](docs/glossary.md) | 용어 정의 |
| [`docs/decisions/`](docs/decisions/) | 결정 기록. 결정 하나에 파일 하나 |
| [`docs/brain-protocol.md`](docs/brain-protocol.md) | 화면 ↔ 두뇌 프로토콜. 화면은 이 문서만 보고 만들 수 있어야 한다 |
| [`docs/references/`](docs/references/) | [Jev API 요약](docs/references/typesafe-jev.md), [비슷한 프로젝트](docs/references/similar-projects.md) |
| [`docs/superpowers/specs/`](docs/superpowers/specs/) | 설계 스펙: [Windows 첫 버전](docs/superpowers/specs/2026-10-14-windows-desktop-pet-design.md), [두뇌 v1](docs/superpowers/specs/2026-10-15-brain-design.md), [두뇌 v2](docs/superpowers/specs/2026-10-15-brain-v2-design.md), [기분·즉각 반응](docs/superpowers/specs/2026-10-15-mood-reaction-design.md), [기분별 그림](docs/superpowers/specs/2026-10-15-mood-sprites-design.md), [검수 루프](docs/superpowers/specs/2026-10-15-review-loop-design.md), [평가 사전값](docs/superpowers/specs/2026-10-16-appraisal-prior-design.md), [동작 모형](docs/superpowers/specs/2026-10-16-action-model-design.md), [시간 모형](docs/superpowers/specs/2026-10-16-time-model-design.md), [기분 갱신 수식](docs/superpowers/specs/2026-10-16-mood-update-math-design.md), [웹 프로토타입](docs/superpowers/specs/2026-10-19-web-prototype-design.md), [두뇌 단순화](docs/superpowers/specs/2026-10-20-simplify-brain-design.md) |
| [`docs/superpowers/plans/`](docs/superpowers/plans/) | 스펙별 구현 계획 |
| [`docs/spikes/`](docs/spikes/) | 실측·기술 검증: [배경 모드](docs/spikes/background-mode.md), [Jev speak_now](docs/spikes/2026-10-15-jev-speak-now-probe.md), [두뇌 v2 가정](docs/spikes/2026-10-15-brain-v2-assumptions.md), [성격 유형](docs/spikes/2026-10-15-personality-types.md), [질문 문구](docs/spikes/2026-10-15-question-wording.md), [시뮬레이션](docs/spikes/2026-10-15-simulation.md) |
| [`docs/review/`](docs/review/) | 검수 루프: [회차별 요약](docs/review/summary.md), [진행 상황](docs/review/progress.md), [루프 프롬프트](docs/review/loop-prompt.md), [검수자 정의](docs/review/reviewer.md), [아는 결함](docs/review/known-defects.md), 회차별 판정·고친 기록(`rounds/`) |
| [`brain/review/README.md`](brain/review/README.md) | 검수 하네스 사용법 |
| [`docs/manual-checks/`](docs/manual-checks/) | 화면·Win32·실제 키·웹 동작 수동 확인 체크리스트 |

## 14. 결정 기록

| 번호 | 제목 | 상태 |
|---|---|---|
| [0001](docs/decisions/0001-jev-as-decision-engine.md) | 실시간 반응 결정에 Jev를 쓴다 | 채택 (일부 개정: 0014) |
| [0002](docs/decisions/0002-platform-order.md) | Windows PC 먼저, Android는 그다음 | 채택 |
| [0003](docs/decisions/0003-windows-display-modes.md) | Windows 배경·오버레이 모드 모두 지원, 설정으로 고정 | 대체됨 (0010) |
| [0004](docs/decisions/0004-input-box-trigger.md) | 캐릭터 클릭·전역 단축키로 입력창, 상시 표시는 설정 | 대체됨 (말풍선 아이콘) |
| [0005](docs/decisions/0005-local-history-storage.md) | 대화 기록은 PC에 저장 | 일부 대체됨 (0006) |
| [0006](docs/decisions/0006-user-provided-api-keys.md) | 서버 없이 사용자가 입력한 API 키로 직접 호출 | 채택 |
| [0007](docs/decisions/0007-dialogue-llm.md) | 캐릭터 대사는 gemini-3.1-flash-lite로 생성 | 채택 |
| [0008](docs/decisions/0008-tech-stack-tauri.md) | Windows 앱은 Tauri(Rust + TypeScript) | 채택 |
| [0009](docs/decisions/0009-background-mode-wallpaper-replacement.md) | 배경 모드는 배경화면 대체 방식 | 대체됨 (0010) |
| [0010](docs/decisions/0010-overlay-only-with-doghouse.md) | 오버레이 모드만, 강아지 집(비활성 모드) 추가 | 채택 |
| [0011](docs/decisions/0011-python-brain-local-sidecar.md) | 두뇌는 PC 안에서 도는 파이썬 프로세스 | 채택 (일부 개정: 0012) |
| [0012](docs/decisions/0012-brain-as-frontend-independent-service.md) | 두뇌는 화면과 독립된 WebSocket 서비스, 키도 두뇌가 보관 | 채택 |
| [0013](docs/decisions/0013-event-driven-brain-with-event-log.md) | 두뇌는 이벤트 단위로 판단, 이벤트 기록이 기억 | 채택 |
| [0014](docs/decisions/0014-probabilistic-model-with-jev-distributions.md) | Jev는 분포를 주고 확률 모델이 뽑아서 결정 | 채택 (기분 변화는 0015, 성격 파라미터는 0018로 개정) |
| [0015](docs/decisions/0015-appraisal-prior-mood-change.md) | 기분 변화는 우리 평가 사전값이 정하고 Jev는 조정만 | 대체됨(0019) |
| [0016](docs/decisions/0016-action-model-ours-first.md) | 동작 선택은 우리 모형 중심, Jev는 약한 조정 | 채택 |
| [0017](docs/decisions/0017-web-prototype-brain-serves-page.md) | 웹 프로토타입은 두뇌가 페이지와 WebSocket을 함께 낸다 | 채택 (프로토타입) |
| [0018](docs/decisions/0018-simplify-to-reaction-and-mood.md) | 두뇌 상태는 반응과 기분만. 성격·관계·습관화·말수 없앰 | 채택 |
| [0019](docs/decisions/0019-message-mood-from-one-question.md) | 글 없는 사건은 우리 값, 글은 Jev 기분 질문 하나. 의도·시킨 동작 질문 없앰 | 채택 |
| [0020](docs/decisions/0020-minimal-brain-rules.md) | 두뇌 규칙 최소화: 더하고 자르기, 고정 반감기, 말하기 세 항, 대사 사실 하나 | 채택 |
| [0021](docs/decisions/0021-web-dog-per-connection.md) | 웹은 접속마다 강아지가 새로 태어나고 저장하지 않는다 | 채택 (프로토타입) |
