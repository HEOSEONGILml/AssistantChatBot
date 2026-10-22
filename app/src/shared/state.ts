// 화면 상태: 백엔드 메시지를 쌓아 두고, 강아지 자세·배지·툴팁·다시 붙을 때 보낼 요청을 계산한다.
import type { BackendMessage, Entry, Limit, Outgoing, Page, PermissionMode, Schedule, ScheduleRow, Task } from "./protocol";

export type Tab = "alerts" | "chat" | "tasks" | "schedules" | "usage" | "settings";
export type Screen = "list" | "task" | "newTask" | "newSchedule" | "schedule" | "editSchedule";
// proposal: [고치기]로 지시서 수정 화면을 열 때 채울 등록 확인의 `data`
export type View = { tab: Tab; screen: Screen; taskId?: number; page: number; proposal?: Record<string, unknown> };
export type Pose = "sleep" | "beg" | "walk" | "lay" | "stand" | "sit";

export type State = {
  connected: boolean;
  loggedIn: boolean | null; // null: 아직 모름
  chatTaskId: number | null;
  tasks: Map<number, Task>; // 배지 계산의 재료: `task`·`tasks`·`task_detail`로 알게 된 작업 전부
  entries: Map<number, Entry[]>; // 작업 ID → 대화 줄 (id 순)
  schedules: Map<number, Schedule>;
  lists: { user?: Page<Task>; alerts?: Page<Task>; schedules?: Page<ScheduleRow> };
  settings: { permissionMode: PermissionMode; recording: boolean } | null;
  limits: Limit[];
  panelOpen: boolean;
  view: View;
};

export function initialState(): State {
  return {
    connected: false, loggedIn: null, chatTaskId: null,
    tasks: new Map(), entries: new Map(), schedules: new Map(), lists: {},
    settings: null, limits: [], panelOpen: false,
    view: { tab: "alerts", screen: "list", page: 1 },
  };
}

// 같은 id의 줄은 한 번만, id 순으로 합친다
function mergeEntries(old: Entry[] | undefined, add: Entry[]): Entry[] {
  const byId = new Map((old ?? []).map((e) => [e.id, e]));
  for (const e of add) byId.set(e.id, e);
  return [...byId.values()].sort((a, b) => a.id - b.id);
}

function withTasks(s: State, ts: Task[]): Pick<State, "tasks" | "chatTaskId" | "lists"> {
  const tasks = new Map(s.tasks);
  let chatTaskId = s.chatTaskId;
  for (const t of ts) {
    tasks.set(t.id, t);
    if (t.source === "chat") chatTaskId = t.id;
  }
  // 이미 받은 목록 안의 작업도 새 값으로 바꾼다
  const fresh = (p?: Page<Task>) => p && { ...p, items: p.items.map((t) => tasks.get(t.id) ?? t) };
  return { tasks, chatTaskId, lists: { ...s.lists, user: fresh(s.lists.user), alerts: fresh(s.lists.alerts) } };
}

const isAlert = (t: Task) => t.source !== "chat"
  && (t.state === "waiting" || ((t.state === "failed" || t.state === "done") && !t.seen));

function withoutAlerts(tasks: Map<number, Task>, keep: Task[]): Map<number, Task> {
  const ids = new Set(keep.map((t) => t.id));
  return new Map([...tasks].filter(([id, t]) => ids.has(id) || !isAlert(t)));
}

// 끊겼을 때: 백엔드에서 받은 것은 모두 버린다. 보던 화면·패널·로그인 여부만 남긴다
export function disconnected(s: State): State {
  return { ...initialState(), view: s.view, panelOpen: s.panelOpen, loggedIn: s.loggedIn };
}

// 메시지를 받은 뒤 이어서 보낼 요청: 알림 목록에 뒤쪽이 있으면 다음 쪽 (배지 훑기)
// 작업 탭에서 보던 쪽이 없어져 마지막 쪽으로 당겼으면 그 쪽
export function followUps(s: State, m: BackendMessage): Outgoing[] {
  if (m.type !== "tasks") return [];
  if (m.view === "alerts" && m.pages > m.page) return [{ type: "list_tasks", page: m.page + 1, view: "alerts" }];
  const last = Math.max(m.pages, 1);
  if (m.view === "user" && s.view.tab === "tasks" && m.page > last && s.view.page === last) return [{ type: "list_tasks", page: last, view: "user" }];
  return [];
}

export function apply(s: State, m: BackendMessage): State {
  switch (m.type) {
    case "status":
      return { ...s, connected: true, loggedIn: m.logged_in };
    case "task":
      return { ...s, ...withTasks(s, [m.task]) };
    case "entry":
      return { ...s, entries: new Map(s.entries).set(m.task_id, mergeEntries(s.entries.get(m.task_id), [m.entry])) };
    case "tasks": {
      // 배지 훑기: 알림 1쪽이 오면 알림 대상 작업을 지우고 1쪽부터 다시 채운다(뒤쪽은 followUps로 이어 받는다).
      // 그래야 끊긴 사이 알림에서 빠진 작업이 배지에 남지 않는다
      const base = m.view === "alerts" && m.page === 1 ? { ...s, tasks: withoutAlerts(s.tasks, m.items) } : s;
      const next = withTasks(base, m.items);
      // 이 목록을 보이는 탭에서 보던 쪽이 쪽 수보다 크면 마지막 쪽으로 당긴다
      const own = m.view === "alerts" ? "alerts" : "tasks";
      const last = Math.max(m.pages, 1);
      const view = s.view.tab === own && s.view.page > last ? { ...s.view, page: last } : s.view;
      // 훑기·최근 작업 요청으로 온 쪽이 보고 있는 쪽을 덮지 않게, 보고 있는 쪽(그 탭이 아니면 1쪽)만 목록에 둔다
      const shown = m.page === (view.tab === own ? view.page : 1);
      const lists = shown ? { ...next.lists, [m.view]: { page: m.page, pages: m.pages, items: m.items } } : next.lists;
      return { ...s, ...next, lists, view };
    }
    case "task_detail": {
      const entries = new Map(s.entries).set(m.task.id, mergeEntries(s.entries.get(m.task.id), m.entries));
      const schedules = m.schedule ? new Map(s.schedules).set(m.task.id, m.schedule) : s.schedules;
      return { ...s, ...withTasks(s, [m.task]), entries, schedules };
    }
    case "schedules":
      return { ...s, lists: { ...s.lists, schedules: { page: m.page, pages: m.pages, items: m.items } } };
    case "schedule": {
      const sc = m.schedule;
      const rows = s.lists.schedules;
      // 목록 줄도 고친다. 도는 중이면 그대로 두고, 아니면 켜짐·꺼짐을 따른다
      const row = (r: ScheduleRow): ScheduleRow => r.task_id !== sc.task_id ? r : {
        ...r, name: sc.name, label: sc.label, next_run: sc.next_run,
        state: r.state === "running" ? "running" : sc.enabled ? "next" : "off",
      };
      return {
        ...s,
        schedules: new Map(s.schedules).set(sc.task_id, sc),
        lists: rows ? { ...s.lists, schedules: { ...rows, items: rows.items.map(row) } } : s.lists,
      };
    }
    case "settings":
      return { ...s, settings: { permissionMode: m.permission_mode, recording: m.recording } };
    case "usage":
      return { ...s, limits: m.limits };
  }
}

// 대화 작업(source: "chat")은 목록·알림·배지에 넣지 않는다 (프로토콜 문서)
const listed = (s: State) => [...s.tasks.values()].filter((t) => t.source !== "chat");
const workingCount = (s: State) => listed(s).filter((t) => t.state === "working").length;

export function badges(s: State): { red: number; yellow: number; green: number } {
  const ts = listed(s);
  return {
    red: ts.filter((t) => t.state === "waiting").length,
    yellow: ts.filter((t) => t.state === "failed" && !t.seen).length,
    green: ts.filter((t) => t.state === "done" && !t.seen).length,
  };
}

export function pose(s: State): Pose {
  if (!s.connected) return "sit";
  if (s.loggedIn === false) return "sleep";
  const b = badges(s);
  if (b.red > 0) return "beg";
  if (workingCount(s) > 0) return "walk";
  if (b.yellow > 0) return "lay";
  if (b.green > 0) return "stand";
  return "sit";
}

export function tooltip(s: State): string {
  if (s.loggedIn === false) return "눌러서 로그인하기";
  const n = workingCount(s);
  return n > 0 ? `일하는 중 · 작업 ${n}개` : "눌러서 일 맡기기";
}

// 다시 붙었을 때·화면을 열 때 보낼 요청. 늘 알림 1쪽(배지 훑기의 시작, 뒤쪽은 followUps)과
// 작업 1쪽(최근 작업: 일하는 중인 작업은 대개 최근이라 강아지 자세에 필요)을 보낸다
export function refreshRequests(s: State): Outgoing[] {
  const out: Outgoing[] = [{ type: "list_tasks", page: 1, view: "alerts" }, { type: "list_tasks", page: 1, view: "user" }];
  const v = s.view;
  if (v.screen === "task" || v.screen === "schedule" || v.screen === "editSchedule") {
    if (v.taskId !== undefined) out.push({ type: "get_task", task_id: v.taskId });
    return out;
  }
  if (v.screen !== "list") return out;
  switch (v.tab) {
    case "alerts": break; // 보고 있는 쪽은 배지 훑기가 받아 온다
    case "tasks": if (v.page !== 1) out.push({ type: "list_tasks", page: v.page, view: "user" }); break;
    case "schedules": out.push({ type: "list_schedules", page: v.page }); break;
    case "chat": if (s.chatTaskId !== null) out.push({ type: "get_task", task_id: s.chatTaskId }); break;
    case "settings": out.push({ type: "get_settings" }); break;
    case "usage": out.push({ type: "get_usage" }); break;
  }
  return out;
}

// 알림 탭: 보고 있는 쪽의 첫 `waiting` 작업만 질문 카드로 보인다. 나머지는 행
export const firstWaiting = (s: State): Task | undefined => s.lists.alerts?.items.find((t) => t.state === "waiting");

export function alertRows(s: State): Task[] {
  const card = firstWaiting(s);
  return (s.lists.alerts?.items ?? []).filter((t) => t !== card);
}

// 아직 답하지 않은 질문: 마지막 사용자 줄 뒤의 마지막 `question` 줄 (캐시에 있을 때만)
export function pendingQuestion(s: State, taskId: number): Entry | undefined {
  const es = s.entries.get(taskId) ?? [];
  for (let i = es.length - 1; i >= 0; i--) {
    if (es[i].kind === "user") return undefined;
    if (es[i].kind === "question") return es[i];
  }
  return undefined;
}

export const STATE_TEXT: Record<Task["state"], string> = {
  working: "일하는 중", waiting: "답을 기다려요", done: "다 했어요", failed: "못 했어요", stopped: "멈췄어요",
};

// 목록 행의 부가 글: 질문을 기다리면 그 질문 글(캐시에 있으면), 아니면 상태 글
export function rowNote(s: State, t: Task): string {
  return (t.state === "waiting" && pendingQuestion(s, t.id)?.text) || STATE_TEXT[t.state];
}

// 열어 본 것으로 알릴 작업: 끝났고 아직 안 봤다 (대화 작업은 알림에 없으니 뺀다)
export function needsSeen(s: State, taskId: number): boolean {
  const t = s.tasks.get(taskId);
  return !!t && t.source !== "chat" && !t.seen && (t.state === "done" || t.state === "failed" || t.state === "stopped");
}
