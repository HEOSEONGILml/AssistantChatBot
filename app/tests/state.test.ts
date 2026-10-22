import { describe, expect, it } from "vitest";
import type { BackendMessage, Entry, Schedule, Task } from "../src/shared/protocol";
import { alertRows, apply, badges, disconnected, firstWaiting, followUps, initialState, pendingQuestion, pose, refreshRequests, rowNote, tooltip, type State } from "../src/shared/state";

const task = (id: number, o: Partial<Task> = {}): Task => ({
  id, source: "user", title: `작업 ${id}`, state: "done", seen: true, session_id: null, created_at: "2026-10-22T09:00:00", ...o,
});
const entry = (id: number, task_id = 2): Entry => ({ id, task_id, at: "2026-10-22T09:00:00", kind: "progress", text: `줄 ${id}`, choices: null, data: null });
const schedule: Schedule = {
  task_id: 3, name: "주간 보고", rule: { repeat: "daily", time: "09:00" }, instruction: "정리", label: "매일 09:00",
  enabled: false, next_run: null, last_run_at: null, last_result: null,
};
const run = (s: State, ...ms: BackendMessage[]) => ms.reduce(apply, s);
const online = () => run(initialState(), { type: "status", logged_in: true });

describe("apply", () => {
  it("connects and sets chatTaskId from status and the chat task", () => {
    const s = run(initialState(), { type: "status", logged_in: true }, { type: "task", task: task(1, { source: "chat", title: "대화" }) });
    expect(s.connected).toBe(true);
    expect(s.loggedIn).toBe(true);
    expect(s.chatTaskId).toBe(1);
    expect(s.tasks.get(1)?.title).toBe("대화");
  });

  it("does not mutate the previous state", () => {
    const s0 = online();
    const s1 = apply(s0, { type: "task", task: task(2) });
    expect(s0.tasks.size).toBe(0);
    expect(s1.tasks.size).toBe(1);
  });

  it("test_entries_merge_without_duplicates", () => {
    let s = run(online(), { type: "entry", task_id: 2, entry: entry(2) });
    s = run(s, { type: "task_detail", task: task(2), entries: [entry(1), entry(2)], schedule: null });
    s = run(s, { type: "entry", task_id: 2, entry: entry(2) }, { type: "entry", task_id: 2, entry: entry(3) });
    expect(s.entries.get(2)!.map((e) => e.id)).toEqual([1, 2, 3]);
  });

  it("applies the tasks list into lists and known tasks", () => {
    const s = run(online(), { type: "tasks", view: "alerts", page: 1, pages: 3, items: [task(4, { state: "waiting" })] });
    expect(s.lists.alerts).toEqual({ page: 1, pages: 3, items: [task(4, { state: "waiting" })] });
    expect(s.tasks.get(4)?.state).toBe("waiting");
    const s2 = run(s, { type: "tasks", view: "user", page: 2, pages: 2, items: [task(5)] });
    expect(s2.lists.user?.page).toBe(2);
    expect(s2.lists.alerts?.items[0].id).toBe(4);
  });

  it("a task message updates the task inside loaded lists", () => {
    let s = run(online(), { type: "tasks", view: "user", page: 1, pages: 1, items: [task(4, { state: "working" })] });
    s = run(s, { type: "task", task: task(4, { state: "done", seen: false }) });
    expect(s.lists.user?.items[0].state).toBe("done");
  });

  it("task_detail stores its schedule", () => {
    const s = run(online(), { type: "task_detail", task: task(3, { source: "schedule" }), entries: [], schedule });
    expect(s.schedules.get(3)).toEqual(schedule);
    expect(s.entries.get(3)).toEqual([]);
  });

  it("applies schedules, schedule, settings and usage", () => {
    let s = run(online(), { type: "schedules", page: 1, pages: 1, items: [{ task_id: 3, name: "주간 보고", label: "매일 09:00", next_run: "x", state: "next" }] });
    expect(s.lists.schedules?.items[0].state).toBe("next");
    s = run(s, { type: "schedule", schedule });
    expect(s.schedules.get(3)).toEqual(schedule);
    expect(s.lists.schedules?.items[0]).toEqual({ task_id: 3, name: "주간 보고", label: "매일 09:00", next_run: null, state: "off" });
    s = run(s, { type: "settings", permission_mode: "plan", recording: false });
    expect(s.settings).toEqual({ permissionMode: "plan", recording: false });
    const limits = [{ type: "five_hour", utilization: 0.5, resets_at: null, received_at: "2026-10-22T09:00:00" }];
    s = run(s, { type: "usage", limits });
    expect(s.limits).toEqual(limits);
  });
});

describe("badges", () => {
  it("counts waiting, unseen failed, unseen done", () => {
    const s = run(online(),
      { type: "task", task: task(1, { state: "waiting" }) },
      { type: "task", task: task(2, { state: "failed", seen: false }) },
      { type: "task", task: task(3, { state: "failed", seen: true }) },
      { type: "task", task: task(4, { state: "done", seen: false }) },
      { type: "task", task: task(5, { state: "done", seen: false }) },
      { type: "task", task: task(6, { state: "stopped", seen: false }) },
    );
    expect(badges(s)).toEqual({ red: 1, yellow: 1, green: 2 });
  });

  it("test_chat_task_excluded_from_badges", () => {
    const s = run(online(),
      { type: "task", task: task(1, { source: "chat", state: "waiting" }) },
      { type: "task", task: task(1, { source: "chat", state: "done", seen: false }) },
    );
    expect(badges(s)).toEqual({ red: 0, yellow: 0, green: 0 });
  });
});

describe("pose", () => {
  const with_ = (...ts: Task[]) => run(online(), ...ts.map((t) => ({ type: "task", task: t }) as BackendMessage));
  it("logged out sleeps", () => {
    expect(pose(run(with_(task(1, { state: "waiting" })), { type: "status", logged_in: false }))).toBe("sleep");
  });
  it("red begs", () => {
    expect(pose(with_(task(1, { state: "waiting" }), task(2, { state: "working" })))).toBe("beg");
  });
  it("working walks", () => {
    expect(pose(with_(task(1, { state: "working" }), task(2, { state: "failed", seen: false })))).toBe("walk");
  });
  it("yellow lays", () => {
    expect(pose(with_(task(1, { state: "failed", seen: false }), task(2, { state: "done", seen: false })))).toBe("lay");
  });
  it("green stands", () => {
    expect(pose(with_(task(1, { state: "done", seen: false })))).toBe("stand");
  });
  it("otherwise sits, also when the chat task works or when disconnected", () => {
    expect(pose(with_(task(1, { state: "done" }), task(2, { source: "chat", state: "working" })))).toBe("sit");
    expect(pose({ ...with_(task(1, { state: "waiting" })), connected: false })).toBe("sit");
    expect(pose(initialState())).toBe("sit");
  });
});

describe("tooltip", () => {
  it("working, logged out, default", () => {
    const working = run(online(), { type: "task", task: task(1, { state: "working" }) }, { type: "task", task: task(2, { state: "working" }) });
    expect(tooltip(working)).toBe("일하는 중 · 작업 2개");
    expect(tooltip(run(working, { type: "status", logged_in: false }))).toBe("눌러서 로그인하기");
    expect(tooltip(online())).toBe("눌러서 일 맡기기");
  });
});

describe("refreshRequests", () => {
  const alerts1 = { type: "list_tasks", page: 1, view: "alerts" };
  const user1 = { type: "list_tasks", page: 1, view: "user" };
  const at = (view: State["view"], s = online()): State => ({ ...s, view });

  it("test_reconnect_requests_current_view", () => {
    expect(refreshRequests(at({ tab: "tasks", screen: "list", page: 2 }))).toEqual([alerts1, user1, { type: "list_tasks", page: 2, view: "user" }]);
    expect(refreshRequests(at({ tab: "tasks", screen: "list", page: 1 }))).toEqual([alerts1, user1]);
    expect(refreshRequests(at({ tab: "tasks", screen: "task", taskId: 9, page: 1 }))).toEqual([alerts1, user1, { type: "get_task", task_id: 9 }]);
    expect(refreshRequests(at({ tab: "settings", screen: "list", page: 1 }))).toEqual([alerts1, user1, { type: "get_settings" }]);
    expect(refreshRequests(at({ tab: "usage", screen: "list", page: 1 }))).toEqual([alerts1, user1, { type: "get_usage" }]);
    expect(refreshRequests(at({ tab: "schedules", screen: "list", page: 1 }))).toEqual([alerts1, user1, { type: "list_schedules", page: 1 }]);
    expect(refreshRequests(at({ tab: "schedules", screen: "schedule", taskId: 3, page: 1 }))).toEqual([alerts1, user1, { type: "get_task", task_id: 3 }]);
    expect(refreshRequests(at({ tab: "tasks", screen: "newTask", page: 1 }))).toEqual([alerts1, user1]);
  });

  it("alerts tab relies on the badge sweep for later pages", () => {
    expect(refreshRequests(at({ tab: "alerts", screen: "list", page: 1 }))).toEqual([alerts1, user1]);
    expect(refreshRequests(at({ tab: "alerts", screen: "list", page: 2 }))).toEqual([alerts1, user1]);
  });

  it("chat tab opens the chat task once known", () => {
    expect(refreshRequests(at({ tab: "chat", screen: "list", page: 1 }))).toEqual([alerts1, user1]);
    const s = run(online(), { type: "task", task: task(1, { source: "chat" }) });
    expect(refreshRequests(at({ tab: "chat", screen: "list", page: 1 }, s))).toEqual([alerts1, user1, { type: "get_task", task_id: 1 }]);
  });
});

describe("badge sweep", () => {
  const alerts = (page: number, items: Task[]): BackendMessage => ({ type: "tasks", view: "alerts", page, pages: 3, items });

  it("followUps asks for the next alerts page until the last", () => {
    const s = online();
    expect(followUps(s, alerts(1, []))).toEqual([{ type: "list_tasks", page: 2, view: "alerts" }]);
    expect(followUps(s, alerts(2, []))).toEqual([{ type: "list_tasks", page: 3, view: "alerts" }]);
    expect(followUps(s, alerts(3, []))).toEqual([]);
    expect(followUps(s, { type: "tasks", view: "user", page: 1, pages: 3, items: [] })).toEqual([]);
    expect(followUps(s, { type: "status", logged_in: true })).toEqual([]);
  });

  it("counts every alerts page and drops stale alerts when the sweep restarts", () => {
    const w = (id: number) => task(id, { state: "waiting" });
    let s = run(online(),
      { type: "task", task: task(1, { source: "chat", state: "waiting" }) },
      { type: "task", task: task(20, { state: "working" }) },
      { type: "task", task: task(21, { state: "done", seen: true }) },
      alerts(1, [w(11), w(12), w(13), w(14)]), alerts(2, [w(15), w(16), w(17), w(18)]), alerts(3, [w(19)]),
    );
    expect(badges(s).red).toBe(9);
    expect(s.lists.alerts?.page).toBe(1); // 훑기 쪽이 보이는 1쪽을 덮지 않는다
    // 다시 훑기: 12·19는 답을 받아 알림에서 빠졌다
    s = run(s, alerts(1, [w(11), w(13), w(14), w(15)]));
    expect(badges(s).red).toBe(4);
    s = run(s, alerts(2, [w(16), w(17), w(18)]));
    expect(badges(s).red).toBe(7);
    expect([...s.tasks.keys()]).toEqual(expect.arrayContaining([1, 20, 21])); // 알림 대상이 아닌 작업은 남는다
  });

  it("shows the alerts page being viewed", () => {
    const s = { ...online(), view: { tab: "alerts", screen: "list", page: 2 } } as State;
    const s2 = run(s, alerts(1, [task(11, { state: "waiting" })]), alerts(2, [task(15, { state: "waiting" })]), alerts(3, []));
    expect(s2.lists.alerts?.page).toBe(2);
  });
});

describe("disconnected", () => {
  it("keeps view, panel and login, forgets backend data", () => {
    let s = run(online(),
      { type: "task", task: task(1, { state: "working" }) },
      { type: "entry", task_id: 1, entry: entry(1, 1) },
      { type: "schedule", schedule },
      { type: "tasks", view: "user", page: 1, pages: 1, items: [task(1, { state: "working" })] },
    );
    s = { ...s, panelOpen: true, view: { tab: "tasks", screen: "task", taskId: 1, page: 1 } };
    expect(tooltip(s)).toBe("일하는 중 · 작업 1개");
    const d = disconnected(s);
    expect(d).toEqual({ ...initialState(), panelOpen: true, loggedIn: true, view: s.view });
    expect(d.connected).toBe(false);
    expect(tooltip(d)).toBe("눌러서 일 맡기기");
    expect(pose(d)).toBe("sit");
  });
});

describe("알림 카드와 행 부가 글", () => {
  const q = (id: number, task_id: number, text: string, kind: Entry["kind"] = "question"): Entry =>
    ({ id, task_id, at: "2026-10-22T09:12:00", kind, text, choices: kind === "question" ? ["결제", "취소"] : null, data: null });
  const alerts = (...items: Task[]) => run(online(), { type: "tasks", view: "alerts", page: 1, pages: 1, items });

  it("firstWaiting picks the first waiting task of the shown alerts page", () => {
    const s = alerts(task(1, { state: "failed", seen: false }), task(2, { state: "waiting" }), task(3, { state: "waiting" }));
    expect(firstWaiting(s)?.id).toBe(2);
    expect(alertRows(s).map((t) => t.id)).toEqual([1, 3]);
    expect(firstWaiting(alerts(task(1, { state: "done", seen: false })))).toBeUndefined();
    expect(firstWaiting(initialState())).toBeUndefined();
    expect(alertRows(initialState())).toEqual([]);
  });

  it("pendingQuestion is the last question after the last user line", () => {
    let s = run(online(), { type: "task_detail", task: task(2, { state: "waiting" }), entries: [q(1, 2, "누구?"), q(2, 2, "민지", "user"), q(3, 2, "결제할까요?")], schedule: null });
    expect(pendingQuestion(s, 2)?.text).toBe("결제할까요?");
    s = run(s, { type: "entry", task_id: 2, entry: q(4, 2, "결제", "user") });
    expect(pendingQuestion(s, 2)).toBeUndefined();
    expect(pendingQuestion(s, 9)).toBeUndefined();
  });

  it("rowNote shows the cached question or the state text", () => {
    const s = run(online(), { type: "entry", task_id: 2, entry: q(1, 2, "결제할까요?") });
    expect(rowNote(s, task(2, { state: "waiting" }))).toBe("결제할까요?");
    expect(rowNote(s, task(5, { state: "waiting" }))).toBe("답을 기다려요");
    expect(rowNote(s, task(5, { state: "working" }))).toBe("일하는 중");
    expect(rowNote(s, task(5, { state: "done" }))).toBe("다 했어요");
    expect(rowNote(s, task(5, { state: "failed" }))).toBe("못 했어요");
    expect(rowNote(s, task(5, { state: "stopped" }))).toBe("멈췄어요");
  });
});
