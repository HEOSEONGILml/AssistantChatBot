# TypeSafe Jev 레퍼런스

2026-10-14 기준으로 조사했다. Jev 릴리스마다 출력 값이 바뀔 수 있다.

## 개요

- TypeSafe AI(샌프란시스코)의 첫 **System One** 모델. 2026-09-15 공개, 얼리 액세스.
- 상태(state)와 타입이 지정된 질문(questions)을 받아 **구조화된 결정**을 확률과 함께 돌려준다.
- 대화, 코드 생성, 도구 호출은 하지 않는다. 용도는 분류·라우팅·점수·추출이다.
- 업체 발표 수치: 응답 70~500ms, 입력 100만 토큰당 $0.042, 출력 토큰 무료. **독립 검증된 값이 아니다.**
- 보안: 도구를 호출하지 않아 위험이 줄지만, state에 주입된 문구가 판단을 조종할 수 있다. 사용자 입력은 state에 들어가므로 이 점을 고려한다.

## API

`POST https://api.typesafe.ai/v1/systemone`, 헤더 `Authorization: Bearer <key>`

```json
{
  "state": "판단 대상. 문자열 또는 구조화된 객체",
  "model": "jev-latest",
  "questions": {
    "emotion":   { "type": "choice", "instructions": "...", "criteria": { "happy": "...", "sad": "..." } },
    "intensity": { "type": "score",  "instructions": "...", "criteria": ["낮음 설명", "중간 설명", "높음 설명"] },
    "interrupt": { "type": "noul",   "instructions": "참/거짓을 판단할 문장" }
  }
}
```

응답:

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "emotion":   { "type": "choice", "choice": "happy", "confidence": 1.0, "probabilities": { "happy": 0.9, "sad": 0.1 } },
    "intensity": { "type": "score", "score": 0.67, "confidence": 0.5, "legend": {}, "probabilities": {} },
    "interrupt": { "type": "noul", "noul": 0.12 }
  },
  "usage": { "input_tokens": 428, "output_tokens": 73 }
}
```

| 타입 | 필드 | 결과 |
|---|---|---|
| `choice` | `instructions`, `criteria` (라벨 → 설명) | `choice`, `confidence`, `probabilities` |
| `score` | `instructions`, `criteria` (단계 설명 배열) | `score`, `confidence`, `legend`, `probabilities` |
| `noul` | `instructions` | `noul` (0~1) |

- SDK: Python `typesafe-sdk` (3.10+), JS/TS `@typesafe-ai/sdk` (Node 20+, TS는 질문 정의로부터 응답 타입을 추론).
- 문서에 명시되지 않은 것: rate limit, state 크기 제한, 질문 개수 제한. 사용 전에 확인한다.

## 사내 사용 사례: 용인FC 챗봇

위치: `C:\Users\lab2ai\Bigglz-AI-core`

- 클라이언트: `src/core/clients/providers/typesafe.py` (`TypeSafeClassifyManager`). 키는 `TYPESAFE_API_KEY_{SERVICE}`. aiohttp로 직접 호출하고 타임아웃 기본 10초.
- 사용 방식: `src/api/YonginChatbot/ARCHITECTURE.md`
  - noul 질문 22개를 **요청 1회**로 병렬 판정해 조회할 정보원을 고른다.
  - 정보원마다 임계값을 따로 둔다(0.48~0.61). 누락을 막기 위해 최적값보다 0.12 낮게 잡았다.
  - Jev가 실패하면 LLM 분류로, LLM도 실패하면 전체 조회로 fallback한다.
  - 임계값 산출 방법과 평가 데이터: `tests/eval/yongin_classify_*`
- 이 프로젝트에 가져올 점: 질문 묶음 1회 호출, 질문별 임계값과 근거 기록, 평가 기반 임계값 재산출, 실패 기록과 fallback.

## 출처

- [TypeSafe Quickstart](https://docs.typesafe.ai/introduction/quickstart)
- [TypeSafe AI Launches Jev – Let's Data Science](https://letsdatascience.com/news/typesafe-ai-launches-jev-decision-model-889a38c0)
- [VKTR](https://www.vktr.com/ai-platforms/chatgpt-cocreator-launches-typesafe-ai-with-jev/)
- [The Register](https://www.theregister.com/a/5296711)
- [NeuralTrust 보안 리뷰](https://neuraltrust.ai/blog/jev-typesafe-ai-security)

## TypeScript SDK 메모 (Context7, 2026-10-14)

- `new TypeSafeClient({ apiKey, fetch, dangerouslyAllowBrowser, timeout, retry, defaultModel })`
  - `fetch`: 커스텀 HTTP 구현. Tauri에서는 `@tauri-apps/plugin-http`의 `fetch`를 넘긴다.
  - `dangerouslyAllowBrowser`: 브라우저(웹뷰)에서 쓰려면 `true`. 키가 페이지에 노출되므로 사용자 본인 키일 때만 쓴다.
  - `timeout`: 시도당 ms, 기본 10000. `defaultModel` 기본 `jev-latest`.
- `client.systemOne({ state, questions }, options?)` → `answers`가 질문 이름과 criteria로 타입 추론된다. `options`로 호출별 timeout·retry·취소를 준다.
- 질문 헬퍼 예: `noul("...")`.
- 문서: https://docs.typesafe.ai/sdk/javascript/api/classes/TypeSafeClient
