# 0023. 에이전트는 Claude Code로 먼저 만들고, 나중에 직접 설계한 에이전트로 바꾼다

- 상태: 채택
- 날짜: 2026-10-21

## 배경

조수의 핵심은 에이전트다 ([vision](../vision.md)). 에이전트를 직접 코드로 짤지, Claude Code 같은 완성된 에이전트 제품을 연결할지 정해야 했다.

Claude Code의 공식 문서(2026-10-21 확인)로 본 사실:

- `claude --chrome`은 Claude in Chrome 확장을 통해 사용자의 실제 크롬·엣지를 로그인 상태 그대로 조작한다. Windows 네이티브에서 된다. → [문서](https://code.claude.com/docs/en/chrome)
- `claude -p --output-format stream-json`으로 외부 프로그램이 부르고 진행 상황을 받는다. `--resume`·`--session-id`로 세션을 잇는다. → [문서](https://code.claude.com/docs/en/headless)
- 시스템 프롬프트 덧붙이기·바꾸기, 기본 도구 끄기, 권한 모드를 정할 수 있다. CLAUDE.md와 자동 메모리로 기억한다.
- 크롬 조작은 Pro·Max·Team·Enterprise 구독 로그인에서만 켜진다. API 키 로그인에서는 꺼진다.
- Anthropic은 사전 승인 없이 제3자 제품이 claude.ai 로그인을 제공하는 것을 허용하지 않는다. → [문서](https://code.claude.com/docs/en/agent-sdk/overview)

## 결정

1단계에서는 Claude Code로 구현한다. 2단계에서 Claude Code 부분을 직접 설계한 에이전트로 대체한다. 사용자가 정한 순서다.

## 검토한 대안

| 대안 | 장점 | 단점 | 채택하지 않은 이유 |
|---|---|---|---|
| 처음부터 직접 만든다 | 컨텍스트·도구·기억을 처음부터 우리가 쥔다. 약관 제약이 없다 | 동작하는 조수가 나오기까지 오래 걸린다. 무엇이 필요한지 써 보기 전에 설계해야 한다 | 사용자가 먼저 Claude Code로 만들기로 했다 |
| Claude Code만 계속 쓴다 | 가장 빠르다. Claude Code가 좋아지면 같이 좋아진다 | 컨텍스트를 우리가 설계하지 못한다. 배포하면 약관 때문에 브라우저 조작이 막힌다. 외부 제품 변경에 흔들린다 | 사용자가 2단계에서 직접 설계해 바꾸기로 했다 |

## 결과

- 1단계는 **개발자 본인 PC에서 본인 구독 로그인**으로 돌린다. 크롬 조작이 구독 로그인에서만 켜지기 때문이다. 팀 내부 사용이 약관상 괜찮은지는 문서로 확정되지 않는다. 다른 사람에게 배포하기 전에 Anthropic에 확인하거나 2단계를 끝낸다.
- 사용자 PC에 Claude Code, Claude in Chrome 확장, 유료 구독이 필요하다.
- 2단계 교체가 쉽도록 Claude Code는 두뇌 안의 외부 호출 계층 뒤에만 둔다 (Claude 판단, CLAUDE.md 3절 "외부 호출 격리"). 화면과 프로토콜은 Claude Code를 모른다.
- 1단계를 써 보며 얻은 것(필요한 컨텍스트, 도구, 기억의 모양)을 2단계 설계의 근거로 기록한다.
