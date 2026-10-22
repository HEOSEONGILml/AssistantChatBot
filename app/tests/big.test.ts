import { describe, expect, it } from "vitest";
import type { BackendMessage, Outgoing, Schedule, Session } from "../src/shared/protocol";
import { apply, bigFollowUps, bigRequests, fromSnapshot, initialState, mergeRequests, toSnapshot, type State, type View } from "../src/shared/state";

const session = (id: number, o: Partial<Session> = {}): Session => ({
  id, source: "user", title: `작업 ${id}`, state: "done", seen: true, claude_session_id: null, created_at: "2026-10-22T09:00:00", ...o,
});
const schedule: Schedule = {
  session_id: 3, name: "주간 보고", rule: { repeat: "daily", time: "09:00" }, instruction: "정리", label: "매일 09:00",
  enabled: true, next_run: null, last_run_at: null, last_result: null,
};
const run = (s: State, ...ms: BackendMessage[]) => ms.reduce((a, m) => apply(a, m, 1000), s);
const online = () => run(initialState(), { type: "status", logged_in: true });
const at = (view: View, s = online()): State => ({ ...s, view });

const alerts1: Outgoing = { type: "list_sessions", page: 1, view: "alerts" };
const user1: Outgoing = { type: "list_sessions", page: 1, view: "user" };

describe("큰 창 상태 넘기기", () => {
  it("survives JSON (Tauri 이벤트) with its maps", () => {
    const s = run(online(),
      { type: "session_detail", session: session(2, { state: "working" }), entries: [{ id: 1, session_id: 2, at: "2026-10-22T09:00:00", kind: "progress", text: "줄", choices: null, data: null }], schedule: null },
      { type: "schedule", schedule },
      { type: "activity", session_id: 2, kind: "tool", text: "파일 읽는 중" },
      { type: "sessions", view: "user", page: 1, pages: 1, items: [session(2, { state: "working" })] });
    const view: View = { tab: "tasks", screen: "task", sessionId: 2, page: 1 };
    const back = fromSnapshot(JSON.parse(JSON.stringify(toSnapshot({ ...s, view }))));
    expect(back.sessions.get(2)?.state).toBe("working");
    expect(back.entries.get(2)?.[0].text).toBe("줄");
    expect(back.schedules.get(3)?.name).toBe("주간 보고");
    expect(back.activity.get(2)).toEqual({ kind: "tool", text: "파일 읽는 중", since: 1000 });
    expect(back.lists.user?.items.map((t) => t.id)).toEqual([2]);
    expect(back.view).toEqual(view);
    expect(back.connected).toBe(true);
  });
});

describe("bigRequests", () => {
  it("asks for the left list too when a conversation is open in a two-column tab", () => {
    expect(bigRequests(at({ tab: "tasks", screen: "task", sessionId: 9, page: 2 }))).toEqual([
      alerts1, user1, { type: "get_session", session_id: 9 }, { type: "list_sessions", page: 2, view: "user" },
    ]);
    expect(bigRequests(at({ tab: "schedules", screen: "schedule", sessionId: 3, page: 1 }))).toEqual([
      alerts1, user1, { type: "get_session", session_id: 3 }, { type: "list_schedules", page: 1 },
    ]);
    expect(bigRequests(at({ tab: "schedules", screen: "newSchedule", page: 1 }))).toEqual([alerts1, user1, { type: "list_schedules", page: 1 }]);
  });

  it("is the same as the panel's for one-column tabs and list screens, without repeats", () => {
    expect(bigRequests(at({ tab: "settings", screen: "list", page: 1 }))).toEqual([alerts1, user1, { type: "get_settings" }]);
    expect(bigRequests(at({ tab: "tasks", screen: "list", page: 1 }))).toEqual([alerts1, user1]);
  });
});

describe("mergeRequests", () => {
  it("sends a request the panel and the big window both need once", () => {
    expect(mergeRequests([alerts1, user1], [alerts1, user1, { type: "get_settings" }])).toEqual([alerts1, user1, { type: "get_settings" }]);
  });
});

describe("bigFollowUps", () => {
  it("refetches the schedule list shown on the left while a schedule conversation is open", () => {
    const s = at({ tab: "schedules", screen: "schedule", sessionId: 3, page: 1 },
      run(online(), { type: "schedules", page: 1, pages: 1, items: [] }));
    expect(bigFollowUps(s, { type: "schedule", schedule })).toEqual([{ type: "list_schedules", page: 1 }]);
  });
});

describe("큰 창의 화면", () => {
  it("keeps the page it shows on the left while a conversation is open", () => {
    const s = run(at({ tab: "tasks", screen: "task", sessionId: 9, page: 2 }),
      { type: "sessions", view: "user", page: 2, pages: 2, items: [session(9)] });
    expect(s.lists.user?.page).toBe(2);
  });

  it("goes back to that tab's list when the shown session is deleted", () => {
    const s = run(at({ tab: "schedules", screen: "schedule", sessionId: 3, page: 2 }), { type: "session_deleted", session_id: 3 });
    expect(s.view).toEqual({ tab: "schedules", screen: "list", page: 2 });
  });
});
