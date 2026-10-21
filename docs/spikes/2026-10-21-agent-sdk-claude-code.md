# 스파이크: Agent SDK로 띄운 Claude Code에서 크롬 조작·질문·권한

2026-10-21, 이 PC(Windows 10, Claude Code 2.1.305, `claude-agent-sdk` 최신)에서 한 번 돌렸다. 버리는 시험이다. 코드: [2026-10-21-agent-sdk-spike.py](2026-10-21-agent-sdk-spike.py).

## 확인하려던 것

문서([chrome](https://code.claude.com/docs/en/chrome.md), [user-input](https://code.claude.com/docs/en/agent-sdk/user-input.md))에 나와 있지 않던 세 가지.

1. 파이썬 Agent SDK로 띄운 Claude Code에서 크롬 조작(`--chrome`)이 켜지는가
2. 질문(`AskUserQuestion`)과 권한 요청이 백엔드 콜백(`can_use_tool`)으로 오는가
3. 질문에 고를 답 밖의 글로 답할 수 있는가

## 방법

- `ClaudeSDKClient` + `ClaudeAgentOptions(can_use_tool=..., permission_mode="default", extra_args={"chrome": None})`
- `ANTHROPIC_API_KEY` 환경 변수를 빼고 돌렸다. 크롬 조작은 구독 로그인에서만 켜지기 때문이다.
- 요청: "AskUserQuestion으로 'example.com을 열까요?'[열기, 취소]를 묻고, 답에 따라 크롬으로 열어 제목을 알려 줘."
- 콜백은 질문에 선택지 밖의 글 "진행해. 그런데 example.com 말고 example.org로 가 줘"로 답했다. 다른 도구는 모두 허용했다.

## 결과

| 확인 | 결과 |
|---|---|
| 1. 크롬 조작 | **됐다.** 시작 정보(`init`)에 `mcp__claude-in-chrome__*` 도구 22개가 실렸다(navigate, read_page, computer, form_input 등). 실제로 탭을 열고 페이지를 읽었다. 로그인 출처는 `apiKeySource: none`(구독 로그인) |
| 2. 질문·권한 콜백 | **됐다.** `AskUserQuestion`이 콜백으로 왔다. 입력은 `questions[{question, header, options[{label, description}], multiSelect}]`. 크롬 도구(`tabs_context_mcp`, `navigate`)의 권한 요청도 콜백으로 왔다 |
| 3. 선택지 밖의 글로 답 | **됐다.** `updated_input`에 `answers: {질문 글: "자유 글"}`을 넣어 허용하자, Claude Code가 그 글을 따라 example.org를 열었다 |

- 작업은 9턴에 끝났고 오류 없이 결과 글을 냈다.
- 같은 도구를 두 번째 쓸 때는 권한 콜백이 다시 오지 않았다(`tabs_context_mcp`, `tabs_close_mcp`).
- 사용자 설정의 스킬·플러그인이 함께 불려 왔다(`Skill`, `ToolSearch` 사용). 실제 구현에서는 불러올 설정을 정해야 한다.
