import { describe, expect, it } from "vitest";
import type { BackendMessage, Entry, Schedule, Session } from "../src/shared/protocol";
import { alertRows, apply, badges, confirmOwner, disconnected, firstWaiting, followUps, initialState, needsSeen, pendingQuestion, pose, refreshRequests, rowNote, elapsedText, tooltip, type State } from "../src/shared/state";

const session = (id: number, o: Partial<Session> = {}): Session => ({
  id, source: "user", title: `작업 ${id}`, state: "done", seen: true, claude_session_id: null, created_at: "2026-10-22T09:00:00", ...o,
});
const entry = (id: number, session_id = 2): Entry => ({ id, session_id, at: "2026-10-22T09:00:00", kind: "progress", text: `줄 ${id}`, choices: null, data: null });
const schedule: Schedule = {
  session_id: 3, name: "주간 보고", rule: { repeat: "daily", time: "09:00" }, instruction: "정리", label: "매일 09:00",
  enabled: false, next_run: null, last_run_at: null, last_result: null,
};
const run = (s: State, ...ms: BackendMessage[]) => ms.reduce((a, m) => apply(a, m), s);
const online = () => run(initialState(), { type: "status", logged_in: true });

describe("apply", () => {
  it("connects and sets chatSessionId from status and the chat session", () => {
    const s = run(initialState(), { type: "status", logged_in: true }, { type: "session", session: session(1, { source: "chat", title: "대화" }) });
    expect(s.connected).toBe(true);
    expect(s.loggedIn).toBe(true);
    expect(s.chatSessionId).toBe(1);
    expect(s.sessions.get(1)?.title).toBe("대화");
  });

  it("does not mutate the previous state", () => {
    const s0 = online();
    const s1 = apply(s0, { type: "session", session: session(2) });
    expect(s0.sessions.size).toBe(0);
    expect(s1.sessions.size).toBe(1);
  });

  it("test_entries_merge_without_duplicates", () => {
    let s = run(online(), { type: "entry", session_id: 2, entry: entry(2) });
    s = run(s, { type: "session_detail", session: session(2), entries: [entry(1), entry(2)], schedule: null });
    s = run(s, { type: "entry", session_id: 2, entry: entry(2) }, { type: "entry", session_id: 2, entry: entry(3) });
    expect(s.entries.get(2)!.map((e) => e.id)).toEqual([1, 2, 3]);
  });

  it("applies the sessions list into lists and known sessions", () => {
    const s = run(online(), { type: "sessions", view: "alerts", page: 1, pages: 3, items: [session(4, { state: "waiting" })] });
    expect(s.lists.alerts).toEqual({ page: 1, pages: 3, items: [session(4, { state: "waiting" })] });
    expect(s.sessions.get(4)?.state).toBe("waiting");
    const s2 = run(s, { type: "sessions", view: "user", page: 1, pages: 2, items: [session(5)] });
    expect(s2.lists.user?.page).toBe(1);
    expect(s2.lists.alerts?.items[0].id).toBe(4);
  });

  it("a session message updates the session inside loaded lists", () => {
    let s = run(online(), { type: "sessions", view: "user", page: 1, pages: 1, items: [session(4, { state: "working" })] });
    s = run(s, { type: "session", session: session(4, { state: "done", seen: false }) });
    expect(s.lists.user?.items[0].state).toBe("done");
  });

  it("session_detail stores its schedule", () => {
    const s = run(online(), { type: "session_detail", session: session(3, { source: "schedule" }), entries: [], schedule });
    expect(s.schedules.get(3)).toEqual(schedule);
    expect(s.entries.get(3)).toEqual([]);
  });

  it("applies schedules, schedule, settings and usage", () => {
    let s = run(online(), { type: "schedules", page: 1, pages: 1, items: [{ session_id: 3, name: "주간 보고", label: "매일 09:00", next_run: "x", state: "next" }] });
    expect(s.lists.schedules?.items[0].state).toBe("next");
    s = run(s, { type: "schedule", schedule });
    expect(s.schedules.get(3)).toEqual(schedule);
    expect(s.lists.schedules?.items[0]).toEqual({ session_id: 3, name: "주간 보고", label: "매일 09:00", next_run: null, state: "off" });
    s = run(s, { type: "settings", permission_mode: "plan", recording: false, recording_dir: "/home/x/.screenpipe", recording_bytes: 2048, jev_key_set: true });
    expect(s.settings).toEqual({ permissionMode: "plan", recording: false, recordingDir: "/home/x/.screenpipe", recordingBytes: 2048, jevKeySet: true });
    const limits = [{ type: "five_hour", utilization: 0.5, resets_at: null, received_at: "2026-10-22T09:00:00" }];
    s = run(s, { type: "usage", limits });
    expect(s.limits).toEqual(limits);
  });
});

describe("nudge", () => {
  it("turns on and off, and is off after a disconnect", () => {
    expect(initialState().nudge).toBe(false);
    let s = run(online(), { type: "nudge", active: true });
    expect(s.nudge).toBe(true);
    expect(disconnected(s).nudge).toBe(false);
    s = run(s, { type: "nudge", active: false });
    expect(s.nudge).toBe(false);
  });
});

describe("badges", () => {
  it("counts waiting, unseen failed, unseen done", () => {
    const s = run(online(),
      { type: "session", session: session(1, { state: "waiting" }) },
      { type: "session", session: session(2, { state: "failed", seen: false }) },
      { type: "session", session: session(3, { state: "failed", seen: true }) },
      { type: "session", session: session(4, { state: "done", seen: false }) },
      { type: "session", session: session(5, { state: "done", seen: false }) },
      { type: "session", session: session(6, { state: "stopped", seen: false }) },
    );
    expect(badges(s)).toEqual({ red: 1, yellow: 1, green: 2 });
  });

  it("test_chat_session_excluded_from_badges", () => {
    const s = run(online(),
      { type: "session", session: session(1, { source: "chat", state: "waiting" }) },
      { type: "session", session: session(1, { source: "chat", state: "done", seen: false }) },
    );
    expect(badges(s)).toEqual({ red: 0, yellow: 0, green: 0 });
  });
});

describe("pose", () => {
  const with_ = (...ts: Session[]) => run(online(), ...ts.map((t) => ({ type: "session", session: t }) as BackendMessage));
  it("logged out sleeps", () => {
    expect(pose(run(with_(session(1, { state: "waiting" })), { type: "status", logged_in: false }))).toBe("sleep");
  });
  it("red begs", () => {
    expect(pose(with_(session(1, { state: "waiting" }), session(2, { state: "working" })))).toBe("beg");
  });
  it("working walks", () => {
    expect(pose(with_(session(1, { state: "working" }), session(2, { state: "failed", seen: false })))).toBe("walk");
  });
  it("yellow lays", () => {
    expect(pose(with_(session(1, { state: "failed", seen: false }), session(2, { state: "done", seen: false })))).toBe("lay");
  });
  it("green stands", () => {
    expect(pose(with_(session(1, { state: "done", seen: false })))).toBe("stand");
  });
  it("otherwise sits, also when the chat session works or when disconnected", () => {
    expect(pose(with_(session(1, { state: "done" }), session(2, { source: "chat", state: "working" })))).toBe("sit");
    expect(pose({ ...with_(session(1, { state: "waiting" })), connected: false })).toBe("sit");
    expect(pose(initialState())).toBe("sit");
  });
});

describe("tooltip", () => {
  it("working, logged out, default", () => {
    const working = run(online(), { type: "session", session: session(1, { state: "working" }) }, { type: "session", session: session(2, { state: "working" }) });
    expect(tooltip(working)).toBe("일하는 중 · 작업 2개");
    expect(tooltip(run(working, { type: "status", logged_in: false }))).toBe("눌러서 로그인하기");
    expect(tooltip(online())).toBe("눌러서 일 맡기기");
  });
  it("먼저 말 걸기 배지가 떠 있으면 일하는 중보다 앞선다", () => {
    const working = run(online(), { type: "session", session: session(1, { state: "working" }) }, { type: "nudge", active: true });
    expect(tooltip(working)).toBe("할 말이 있어요");
  });
});

describe("refreshRequests", () => {
  const alerts1 = { type: "list_sessions", page: 1, view: "alerts" };
  const user1 = { type: "list_sessions", page: 1, view: "user" };
  const at = (view: State["view"], s = online()): State => ({ ...s, view });

  it("test_reconnect_requests_current_view", () => {
    expect(refreshRequests(at({ tab: "tasks", screen: "list", page: 2 }))).toEqual([alerts1, user1, { type: "list_sessions", page: 2, view: "user" }]);
    expect(refreshRequests(at({ tab: "tasks", screen: "list", page: 1 }))).toEqual([alerts1, user1]);
    expect(refreshRequests(at({ tab: "tasks", screen: "task", sessionId: 9, page: 1 }))).toEqual([alerts1, user1, { type: "get_session", session_id: 9 }]);
    expect(refreshRequests(at({ tab: "settings", screen: "list", page: 1 }))).toEqual([alerts1, user1, { type: "get_settings" }]);
    expect(refreshRequests(at({ tab: "usage", screen: "list", page: 1 }))).toEqual([alerts1, user1, { type: "get_usage" }]);
    expect(refreshRequests(at({ tab: "schedules", screen: "list", page: 1 }))).toEqual([alerts1, user1, { type: "list_schedules", page: 1 }]);
    expect(refreshRequests(at({ tab: "schedules", screen: "schedule", sessionId: 3, page: 1 }))).toEqual([alerts1, user1, { type: "get_session", session_id: 3 }]);
    expect(refreshRequests(at({ tab: "tasks", screen: "newTask", page: 1 }))).toEqual([alerts1, user1]);
  });

  it("alerts tab relies on the badge sweep for later pages", () => {
    expect(refreshRequests(at({ tab: "alerts", screen: "list", page: 1 }))).toEqual([alerts1, user1]);
    expect(refreshRequests(at({ tab: "alerts", screen: "list", page: 2 }))).toEqual([alerts1, user1]);
  });

  it("chat tab opens the chat session once known", () => {
    expect(refreshRequests(at({ tab: "chat", screen: "list", page: 1 }))).toEqual([alerts1, user1]);
    const s = run(online(), { type: "session", session: session(1, { source: "chat" }) });
    expect(refreshRequests(at({ tab: "chat", screen: "list", page: 1 }, s))).toEqual([alerts1, user1, { type: "get_session", session_id: 1 }]);
  });
});

describe("badge sweep", () => {
  const alerts = (page: number, items: Session[]): BackendMessage => ({ type: "sessions", view: "alerts", page, pages: 3, items });

  it("followUps asks for the next alerts page until the last", () => {
    const s = online();
    expect(followUps(s, alerts(1, []))).toEqual([{ type: "list_sessions", page: 2, view: "alerts" }]);
    expect(followUps(s, alerts(2, []))).toEqual([{ type: "list_sessions", page: 3, view: "alerts" }]);
    expect(followUps(s, alerts(3, []))).toEqual([]);
    expect(followUps(s, { type: "sessions", view: "user", page: 1, pages: 3, items: [] })).toEqual([]);
    expect(followUps(s, { type: "status", logged_in: true })).toEqual([]);
  });

  it("counts every alerts page and drops stale alerts when the sweep restarts", () => {
    const w = (id: number) => session(id, { state: "waiting" });
    let s = run(online(),
      { type: "session", session: session(1, { source: "chat", state: "waiting" }) },
      { type: "session", session: session(20, { state: "working" }) },
      { type: "session", session: session(21, { state: "done", seen: true }) },
      alerts(1, [w(11), w(12), w(13), w(14)]), alerts(2, [w(15), w(16), w(17), w(18)]), alerts(3, [w(19)]),
    );
    expect(badges(s).red).toBe(9);
    expect(s.lists.alerts?.page).toBe(1); // 훑기 쪽이 보이는 1쪽을 덮지 않는다
    // 다시 훑기: 12·19는 답을 받아 알림에서 빠졌다
    s = run(s, alerts(1, [w(11), w(13), w(14), w(15)]));
    expect(badges(s).red).toBe(4);
    s = run(s, alerts(2, [w(16), w(17), w(18)]));
    expect(badges(s).red).toBe(7);
    expect([...s.sessions.keys()]).toEqual(expect.arrayContaining([1, 20, 21])); // 알림 대상이 아닌 세션은 남는다
  });

  it("shows the alerts page being viewed", () => {
    const s = { ...online(), view: { tab: "alerts", screen: "list", page: 2 } } as State;
    const s2 = run(s, alerts(1, [session(11, { state: "waiting" })]), alerts(2, [session(15, { state: "waiting" })]), alerts(3, []));
    expect(s2.lists.alerts?.page).toBe(2);
  });
});

describe("로그인 진행", () => {
  it("status가 오면 로그인하는 중이 풀리고, 끊겨도 풀린다", () => {
    const s = { ...online(), loggingIn: true };
    expect(run(s, { type: "status", logged_in: false }).loggingIn).toBe(false);
    expect(run(s, { type: "status", logged_in: true }).loggingIn).toBe(false);
    expect(disconnected(s).loggingIn).toBe(false);
    expect(initialState().loggingIn).toBe(false);
  });
});

describe("disconnected", () => {
  it("keeps view, panel and login, forgets backend data", () => {
    let s = run(online(),
      { type: "session", session: session(1, { state: "working" }) },
      { type: "entry", session_id: 1, entry: entry(1, 1) },
      { type: "schedule", schedule },
      { type: "sessions", view: "user", page: 1, pages: 1, items: [session(1, { state: "working" })] },
    );
    s = { ...s, panelOpen: true, view: { tab: "tasks", screen: "task", sessionId: 1, page: 1 } };
    expect(tooltip(s)).toBe("일하는 중 · 작업 1개");
    const d = disconnected(s);
    expect(d).toEqual({ ...initialState(), panelOpen: true, loggedIn: true, view: s.view });
    expect(d.connected).toBe(false);
    expect(tooltip(d)).toBe("눌러서 일 맡기기");
    expect(pose(d)).toBe("sit");
  });
});

describe("알림 카드와 행 부가 글", () => {
  const q = (id: number, session_id: number, text: string, kind: Entry["kind"] = "question"): Entry =>
    ({ id, session_id, at: "2026-10-22T09:12:00", kind, text, choices: kind === "question" ? ["결제", "취소"] : null, data: null });
  const alerts = (...items: Session[]) => run(online(), { type: "sessions", view: "alerts", page: 1, pages: 1, items });

  it("firstWaiting picks the first waiting session of the shown alerts page", () => {
    const s = alerts(session(1, { state: "failed", seen: false }), session(2, { state: "waiting" }), session(3, { state: "waiting" }));
    expect(firstWaiting(s)?.id).toBe(2);
    expect(alertRows(s).map((t) => t.id)).toEqual([1, 3]);
    expect(firstWaiting(alerts(session(1, { state: "done", seen: false })))).toBeUndefined();
    expect(firstWaiting(initialState())).toBeUndefined();
    expect(alertRows(initialState())).toEqual([]);
  });

  it("pendingQuestion is the last question after the last user line", () => {
    let s = run(online(), { type: "session_detail", session: session(2, { state: "waiting" }), entries: [q(1, 2, "누구?"), q(2, 2, "민지", "user"), q(3, 2, "결제할까요?")], schedule: null });
    expect(pendingQuestion(s, 2)?.text).toBe("결제할까요?");
    s = run(s, { type: "entry", session_id: 2, entry: q(4, 2, "결제", "user") });
    expect(pendingQuestion(s, 2)).toBeUndefined();
    expect(pendingQuestion(s, 9)).toBeUndefined();
  });

  it("rowNote shows the cached question or the state text", () => {
    const s = run(online(), { type: "entry", session_id: 2, entry: q(1, 2, "결제할까요?") });
    expect(rowNote(s, session(2, { state: "waiting" }))).toBe("결제할까요?");
    expect(rowNote(s, session(5, { state: "waiting" }))).toBe("답을 기다려요");
    expect(rowNote(s, session(5, { state: "working" }))).toBe("일하는 중");
    expect(rowNote(s, session(5, { state: "done" }))).toBe("다 했어요");
    expect(rowNote(s, session(5, { state: "failed" }))).toBe("못 했어요");
    expect(rowNote(s, session(5, { state: "stopped" }))).toBe("멈췄어요");
  });
});

describe("목록 쪽 맞추기", () => {
  const user = (page: number, pages: number, items: Session[] = []): BackendMessage => ({ type: "sessions", view: "user", page, pages, items });
  const at = (view: State["view"]): State => ({ ...online(), view });

  it("작업 탭 N쪽을 보는 중에는 작업 1쪽 답을 목록으로 삼지 않는다", () => {
    const s = run(at({ tab: "tasks", screen: "list", page: 2 }), user(1, 3, [session(1)]));
    expect(s.lists.user).toBeUndefined();
    const s2 = run(s, user(2, 3, [session(5)]));
    expect(s2.lists.user?.page).toBe(2);
    // 다른 탭에서는 작업 1쪽이 목록이다
    expect(run(at({ tab: "alerts", screen: "list", page: 2 }), user(1, 3)).lists.user?.page).toBe(1);
  });

  it("작업 쪽 수가 줄면 보던 쪽을 마지막 쪽으로 당기고 그 쪽을 요청한다", () => {
    const m = user(3, 2);
    const s = run(at({ tab: "tasks", screen: "list", page: 3 }), m);
    expect(s.view.page).toBe(2);
    expect(followUps(s, m)).toEqual([{ type: "list_sessions", page: 2, view: "user" }]);
    // 빈 목록(쪽 0)은 1쪽으로
    const e = user(2, 0);
    const s0 = run(at({ tab: "tasks", screen: "list", page: 2 }), e);
    expect(s0.view.page).toBe(1);
    expect(followUps(s0, e)).toEqual([{ type: "list_sessions", page: 1, view: "user" }]);
    // 알림 탭을 보는 중이면 작업 쪽 수로 당기지 않는다
    expect(run(at({ tab: "alerts", screen: "list", page: 3 }), user(1, 1)).view.page).toBe(3);
  });

  it("알림 쪽 수가 줄면 보던 쪽을 당기고, 훑기로 오는 그 쪽을 보인다", () => {
    const a = (page: number, pages: number, items: Session[] = []): BackendMessage => ({ type: "sessions", view: "alerts", page, pages, items });
    let s = run(at({ tab: "alerts", screen: "list", page: 3 }), a(1, 2, [session(11, { state: "waiting" })]));
    expect(s.view.page).toBe(2);
    s = run(s, a(2, 2, [session(15, { state: "waiting" })]));
    expect(s.lists.alerts?.page).toBe(2);
    // 1쪽만 남으면 1쪽을 바로 보인다
    const s1 = run(at({ tab: "alerts", screen: "list", page: 2 }), a(1, 1, [session(11, { state: "waiting" })]));
    expect(s1.view.page).toBe(1);
    expect(s1.lists.alerts?.page).toBe(1);
  });
});

describe("needsSeen", () => {
  it("끝났고 안 본 작업만 (대화 작업 빼고)", () => {
    const s = run(online(),
      { type: "session", session: session(1, { state: "done", seen: false }) },
      { type: "session", session: session(2, { state: "failed", seen: false }) },
      { type: "session", session: session(3, { state: "stopped", seen: false }) },
      { type: "session", session: session(4, { state: "done", seen: true }) },
      { type: "session", session: session(5, { state: "working", seen: false }) },
      { type: "session", session: session(6, { state: "done", seen: false, source: "chat" }) },
    );
    expect([1, 2, 3, 4, 5, 6, 7].filter((id) => needsSeen(s, id))).toEqual([1, 2, 3]);
  });
});

describe("스케줄 목록 다시 받기", () => {
  const rows = (ids: number[]): BackendMessage => ({
    type: "schedules", page: 1, pages: 1,
    items: ids.map((id) => ({ session_id: id, name: `s${id}`, label: "매일 09:00", next_run: null, state: "next" as const })),
  });
  const viewing = (): State => run({ ...online(), view: { tab: "schedules", screen: "list", page: 1 } }, rows([3]));

  it("목록에 없는 스케줄이 오면(새로 등록) 보던 쪽을 다시 받는다", () => {
    const m: BackendMessage = { type: "schedule", schedule: { ...schedule, session_id: 9 } };
    expect(followUps(run(viewing(), m), m)).toEqual([{ type: "list_schedules", page: 1 }]);
    const known: BackendMessage = { type: "schedule", schedule };
    expect(followUps(run(viewing(), known), known)).toEqual([]);
  });

  it("스케줄 작업의 도는 중 여부가 행과 다르면 다시 받는다", () => {
    const working: BackendMessage = { type: "session", session: session(3, { source: "schedule", state: "working" }) };
    expect(followUps(run(viewing(), working), working)).toEqual([{ type: "list_schedules", page: 1 }]);
    const done: BackendMessage = { type: "session", session: session(3, { source: "schedule", state: "done" }) };
    expect(followUps(run(viewing(), done), done)).toEqual([]);
  });

  it("목록에 없는 스케줄의 세션 소식(session)만으로는 다시 받지 않는다", () => {
    const m: BackendMessage = { type: "session", session: session(9, { source: "schedule", state: "working" }) };
    expect(followUps(run(viewing(), m), m)).toEqual([]);
  });

  it("스케줄 탭 목록을 보고 있지 않으면 받지 않는다", () => {
    const m: BackendMessage = { type: "schedule", schedule: { ...schedule, session_id: 9 } };
    const s = run({ ...online(), view: { tab: "tasks", screen: "list", page: 1 } }, m);
    expect(followUps(s, m)).toEqual([]);
  });
});

describe("session_deleted", () => {
  const page = (items: any[], p = 1, pages = 1) => ({ page: p, pages, items });
  const rows = (id: number) => ({ session_id: id, name: "n", label: "l", next_run: null, state: "off" as const });
  const withAll = (view: State["view"]): State => ({
    ...online(), view,
    sessions: new Map([[2, session(2)], [5, session(5)]]),
    entries: new Map([[2, [entry(1)]], [5, [entry(2, 5)]]]),
    schedules: new Map([[3, schedule]]),
    lists: { user: page([session(2), session(5)]), alerts: page([session(2)]), schedules: page([rows(3), rows(6)]) },
  });
  const gone = (id: number): BackendMessage => ({ type: "session_deleted", session_id: id });

  it("세션·대화 줄·스케줄·세 목록의 행을 모두 뺀다", () => {
    const s = run(withAll({ tab: "tasks", screen: "list", page: 1 }), gone(2), gone(3));
    expect([...s.sessions.keys()]).toEqual([5]);
    expect([...s.entries.keys()]).toEqual([5]);
    expect(s.schedules.size).toBe(0);
    expect(s.lists.user?.items.map((t) => t.id)).toEqual([5]);
    expect(s.lists.alerts?.items).toEqual([]);
    expect(s.lists.schedules?.items.map((r) => r.session_id)).toEqual([6]);
  });

  it("배지에서도 빠진다", () => {
    const s0 = run(online(), { type: "session", session: session(2, { state: "waiting" }) });
    expect(badges(s0).red).toBe(1);
    expect(badges(run(s0, gone(2))).red).toBe(0);
  });

  it("대화 세션이면 chatSessionId가 null, 다음 session으로 새 대화가 들어온다", () => {
    let s = run(online(), { type: "session", session: session(1, { source: "chat" }) });
    const other = run(s, gone(2));
    s = run(s, gone(1));
    expect(s.chatSessionId).toBeNull();
    expect(run(s, { type: "session", session: session(8, { source: "chat" }) }).chatSessionId).toBe(8);
    expect(other.chatSessionId).toBe(1);
  });

  it("보던 세션이 지워지면 그 탭 목록으로, 다른 세션이면 그대로", () => {
    const task = withAll({ tab: "tasks", screen: "task", sessionId: 2, page: 2 });
    expect(run(task, gone(2)).view).toEqual({ tab: "tasks", screen: "list", page: 2 });
    expect(run(task, gone(5)).view).toEqual(task.view);
    const sch = withAll({ tab: "schedules", screen: "editSchedule", sessionId: 3, page: 1, proposal: { a: 1 } });
    expect(run(sch, gone(3)).view).toEqual({ tab: "schedules", screen: "list", page: 1 });
    const alerts = withAll({ tab: "alerts", screen: "task", sessionId: 2, page: 1 });
    expect(run(alerts, gone(2)).view).toEqual({ tab: "alerts", screen: "list", page: 1 });
  });

  it("보는 목록이 비면 followUps가 그 쪽을 다시 받는다", () => {
    const tasks = withAll({ tab: "tasks", screen: "list", page: 2 });
    tasks.lists = { ...tasks.lists, user: page([session(2)], 2, 2) };
    expect(followUps(run(tasks, gone(2)), gone(2))).toEqual([{ type: "list_sessions", page: 2, view: "user" }]);
    const rest = withAll({ tab: "tasks", screen: "list", page: 1 });
    expect(followUps(run(rest, gone(2)), gone(2))).toEqual([]);
    const sch = withAll({ tab: "schedules", screen: "list", page: 3 });
    sch.lists = { ...sch.lists, schedules: page([rows(3)], 3, 3) };
    expect(followUps(run(sch, gone(3)), gone(3))).toEqual([{ type: "list_schedules", page: 3 }]);
    const alerts = withAll({ tab: "alerts", screen: "list", page: 2 });
    alerts.lists = { ...alerts.lists, alerts: page([session(2)], 2, 2) };
    expect(followUps(run(alerts, gone(2)), gone(2))).toEqual([{ type: "list_sessions", page: 2, view: "alerts" }]);
  });
});

describe("activity", () => {
  const act = (session_id: number, text: string, kind: "thinking" | "tool" | "writing" = "tool"): BackendMessage => ({ type: "activity", session_id, kind, text });
  const withActivity = () => apply(apply(online(), act(2, "생각하는 중", "thinking"), 1000), act(2, "파일 읽는 중"), 5000);

  it("받은 시각을 첫 activity에서 잡고, 하는 일이 바뀌어도 지킨다", () => {
    expect(withActivity().activity.get(2)).toEqual({ kind: "tool", text: "파일 읽는 중", since: 1000 });
    expect(initialState().activity.size).toBe(0);
  });

  it("세션마다 따로 센다", () => {
    const s = apply(withActivity(), act(3, "답 쓰는 중", "writing"), 9000);
    expect(s.activity.get(2)?.since).toBe(1000);
    expect(s.activity.get(3)?.since).toBe(9000);
  });

  it("result·failure·question·proposal 줄이 오면 그 세션의 줄만 지운다", () => {
    for (const kind of ["result", "failure", "question", "proposal"] as const) {
      const base = apply(withActivity(), act(3, "x"), 2000);
      const s = run(base, { type: "entry", session_id: 2, entry: { ...entry(9), kind } });
      expect(s.activity.has(2)).toBe(false);
      expect(s.activity.has(3)).toBe(true);
    }
  });

  it("progress·user·chip 줄은 지우지 않는다", () => {
    for (const kind of ["progress", "user", "chip"] as const) {
      expect(run(withActivity(), { type: "entry", session_id: 2, entry: { ...entry(9), kind } }).activity.has(2)).toBe(true);
    }
  });

  it("답한 뒤 다시 시작하면 새 시각으로 센다", () => {
    let s = run(withActivity(), { type: "entry", session_id: 2, entry: { ...entry(9), kind: "question" } });
    s = apply(s, act(2, "파일 읽는 중"), 20000);
    expect(s.activity.get(2)?.since).toBe(20000);
  });

  it("세션이 working이 아니게 되면 지우고, working이면 둔다", () => {
    expect(run(withActivity(), { type: "session", session: session(2, { state: "working" }) }).activity.has(2)).toBe(true);
    for (const state of ["waiting", "done", "failed", "stopped"] as const) {
      expect(run(withActivity(), { type: "session", session: session(2, { state }) }).activity.has(2)).toBe(false);
    }
  });

  it("session_deleted와 끊김이 지운다", () => {
    expect(run(withActivity(), { type: "session_deleted", session_id: 2 }).activity.has(2)).toBe(false);
    expect(disconnected(withActivity()).activity.size).toBe(0);
  });

  it("now를 안 주면 현재 시각을 쓴다", () => {
    const before = Date.now();
    const since = run(online(), act(2, "x")).activity.get(2)!.since;
    expect(since).toBeGreaterThanOrEqual(before);
    expect(since).toBeLessThanOrEqual(Date.now());
  });
});

describe("elapsedText", () => {
  it("60초까지는 N초, 넘으면 M분 N초", () => {
    expect(elapsedText(0)).toBe("0초");
    expect(elapsedText(999)).toBe("0초");
    expect(elapsedText(1000)).toBe("1초");
    expect(elapsedText(59999)).toBe("59초");
    expect(elapsedText(60000)).toBe("60초");
    expect(elapsedText(61000)).toBe("1분 1초");
    expect(elapsedText(125000)).toBe("2분 5초");
    expect(elapsedText(180000)).toBe("3분 0초");
    expect(elapsedText(-500)).toBe("0초");
  });
});

describe("confirmOwner", () => {
  it("설정 탭이면 'settings', 그 밖은 대화 세션 ID (탭을 바꾸면 설정 확인 상자가 닫힌다)", () => {
    expect(confirmOwner({ tab: "settings", screen: "list", page: 1 }, undefined)).toBe("settings");
    expect(confirmOwner({ tab: "alerts", screen: "list", page: 1 }, undefined)).toBeUndefined();
    expect(confirmOwner({ tab: "tasks", screen: "task", sessionId: 4, page: 1 }, 4)).toBe(4);
  });
});
