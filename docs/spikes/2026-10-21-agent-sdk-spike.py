# 버리는 시험: Agent SDK로 띄운 Claude Code에서 (1) 크롬 조작, (2) 질문·권한 콜백, (3) 고를 답 밖의 글로 답하기
import asyncio, json, sys
from claude_agent_sdk import (ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, ResultMessage,
                              SystemMessage, TextBlock, ToolUseBlock, PermissionResultAllow)

FREE_ANSWER = "진행해. 그런데 example.com 말고 example.org로 가 줘"


def log(*a):
    print(*a, flush=True)


async def can_use_tool(name, tool_input, ctx):
    log(f"\n[콜백] 도구={name} title={getattr(ctx, 'title', None)}")
    log("       입력=" + json.dumps(tool_input, ensure_ascii=False)[:600])
    if name == "AskUserQuestion":
        answers = {q["question"]: FREE_ANSWER for q in tool_input.get("questions", [])}
        log(f"       → 고를 답 밖의 글로 답함: {FREE_ANSWER}")
        return PermissionResultAllow(updated_input={**tool_input, "answers": answers})
    log("       → 허용")
    return PermissionResultAllow()


async def main():
    opts = ClaudeAgentOptions(
        can_use_tool=can_use_tool,
        permission_mode="default",
        max_turns=20,
        extra_args={"chrome": None},
    )
    prompt = ("먼저 AskUserQuestion 도구로 '브라우저로 example.com을 열까요?'라고 물어봐. 선택지는 '열기', '취소' 두 개. "
              "그다음 내 답에 따라 크롬 브라우저 도구로 페이지를 열고 제목을 알려 줘. "
              "크롬 브라우저 도구가 없으면 없다고만 말하고 끝내.")
    async with ClaudeSDKClient(options=opts) as client:
        await client.query(prompt)
        async for m in client.receive_response():
            if isinstance(m, SystemMessage) and m.subtype == "init":
                tools = m.data.get("tools", [])
                log("[init] 크롬 관련 도구:", [t for t in tools if "chrome" in t.lower()])
                log("[init] AskUserQuestion 있음:", "AskUserQuestion" in tools)
                log("[init] apiKeySource:", m.data.get("apiKeySource"))
            elif isinstance(m, AssistantMessage):
                for b in m.content:
                    if isinstance(b, TextBlock):
                        log("[말]", b.text[:300])
                    elif isinstance(b, ToolUseBlock):
                        log("[도구 사용]", b.name)
            elif isinstance(m, ResultMessage):
                log(f"\n[끝] is_error={m.is_error} turns={m.num_turns} result={str(m.result)[:300]}")


asyncio.run(asyncio.wait_for(main(), 300))
