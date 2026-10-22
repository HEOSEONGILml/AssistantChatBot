// 화면 상태: 백엔드 메시지를 쌓아 두고, 강아지 자세·배지·툴팁·다시 붙을 때 보낼 요청을 계산한다.
import type { ActivityKind, BackendMessage, Entry, Limit, Outgoing, Page, PermissionMode, Schedule, ScheduleRow, Session } from "./protocol";

export type Tab = "alerts" | "chat" | "tasks" | "schedules" | "usage" | "settings";
export type Screen = "list" | "task" | "newTask" | "newSchedule" | "schedule" | "editSchedule";
// proposal: [고치기]로 지시서 수정 화면을 열 때 채울 등록 확인의 `data`
export type View = { tab: Tab; screen: Screen; sessionId?: number; page: number; proposal?: Record<string, unknown> };
export type Pose = "sleep" | "beg" | "walk" | "lay" | "stand" | "sit";

// 돌고 있는 세션이 지금 하는 일. since: 이번 대답의 첫 activity를 받은 시각(ms), 하는 일이 바뀌어도 그대로
export type Activity = { kind: ActivityKind; text: string; since: number };

export type State = {
  connected: boolean;
  loggedIn: boolean | null; // null: 아직 모름
  loggingIn: boolean; // [로그인]을 눌러 status를 기다리는 중
  chatSessionId: number | null;
  sessions: Map<number, Session>; // 배지 계산의 재료: `session`·`sessions`·`session_detail`로 알게 된 세션 전부
  entries: Map<number, Entry[]>; // 세션 ID → 대화 줄 (id 순)
  schedules: Map<number, Schedule>;
  activity: Map<number, Activity>; // 세션 ID → 지금 하는 일 (준비 중 줄)
  lists: { user?: Page<Session>; alerts?: Page<Session>; schedules?: Page<ScheduleRow> };
  settings: { permissionMode: PermissionMode; recording: boolean; jevKeySet: boolean } | null;
  nudge: boolean; // 먼저 말 걸기 배지가 떠 있음
  limits: Limit[];
  panelOpen: boolean;
  view: View;
};

export function initialState(): State {
  return {
    connected: false, loggedIn: null, loggingIn: false, chatSessionId: null,
    sessions: new Map(), entries: new Map(), schedules: new Map(), activity: new Map(), lists: {},
    settings: null, nudge: false, limits: [], panelOpen: false,
    view: { tab: "alerts", screen: "list", page: 1 },
  };
}

// 같은 id의 줄은 한 번만, id 순으로 합친다
function mergeEntries(old: Entry[] | undefined, add: Entry[]): Entry[] {
  const byId = new Map((old ?? []).map((e) => [e.id, e]));
  for (const e of add) byId.set(e.id, e);
  return [...byId.values()].sort((a, b) => a.id - b.id);
}

function withSessions(s: State, ts: Session[]): Pick<State, "sessions" | "chatSessionId" | "lists"> {
  const sessions = new Map(s.sessions);
  let chatSessionId = s.chatSessionId;
  for (const t of ts) {
    sessions.set(t.id, t);
    if (t.source === "chat") chatSessionId = t.id;
  }
  // 이미 받은 목록 안의 세션도 새 값으로 바꾼다
  const fresh = (p?: Page<Session>) => p && { ...p, items: p.items.map((t) => sessions.get(t.id) ?? t) };
  return { sessions, chatSessionId, lists: { ...s.lists, user: fresh(s.lists.user), alerts: fresh(s.lists.alerts) } };
}

const isAlert = (t: Session) => t.source !== "chat"
  && (t.state === "waiting" || ((t.state === "failed" || t.state === "done") && !t.seen));

function withoutAlerts(sessions: Map<number, Session>, keep: Session[]): Map<number, Session> {
  const ids = new Set(keep.map((t) => t.id));
  return new Map([...sessions].filter(([id, t]) => ids.has(id) || !isAlert(t)));
}

// 끊겼을 때: 백엔드에서 받은 것은 모두 버린다. 보던 화면·패널·로그인 여부만 남긴다
export function disconnected(s: State): State {
  return { ...initialState(), view: s.view, panelOpen: s.panelOpen, loggedIn: s.loggedIn };
}

// 메시지를 받은 뒤 이어서 보낼 요청: 알림 목록에 뒤쪽이 있으면 다음 쪽 (배지 훑기)
// 작업 탭에서 보던 쪽이 없어져 마지막 쪽으로 당겼으면 그 쪽
// 스케줄 탭 목록을 보는 중에 목록과 어긋난 스케줄 소식이 오면 그 쪽을 다시 받는다
// (새로 등록한 스케줄은 1쪽 맨 위, 도는 중 여부는 세션 상태로 바뀐다)
export function followUps(s: State, m: BackendMessage): Outgoing[] {
  if (m.type === "schedule" || (m.type === "session" && m.session.source === "schedule")) {
    const v = s.view, list = s.lists.schedules;
    if (!list || v.tab !== "schedules" || v.screen !== "list") return [];
    const id = m.type === "schedule" ? m.schedule.session_id : m.session.id;
    const row = list.items.find((r) => r.session_id === id);
    const stale = row ? m.type === "session" && (row.state === "running") !== (m.session.state === "working" || m.session.state === "waiting")
      : m.type === "schedule" && list.page === 1; // 목록에 없는 행은 `schedule` 소식일 때만 다시 받는다
    return stale ? [{ type: "list_schedules", page: list.page }] : [];
  }
  if (m.type === "session_deleted") {
    // 지운 뒤 보는 목록이 비었으면 그 쪽을 다시 받는다 (쪽 수가 줄었으면 sessions·schedules 처리가 마지막 쪽으로 당긴다)
    const v = s.view;
    if (v.screen !== "list") return [];
    const { user, alerts, schedules } = s.lists;
    if (v.tab === "tasks" && user && user.items.length === 0) return [{ type: "list_sessions", page: user.page, view: "user" }];
    if (v.tab === "alerts" && alerts && alerts.items.length === 0) return [{ type: "list_sessions", page: alerts.page, view: "alerts" }];
    if (v.tab === "schedules" && schedules && schedules.items.length === 0) return [{ type: "list_schedules", page: schedules.page }];
    return [];
  }
  if (m.type !== "sessions") return [];
  if (m.view === "alerts" && m.pages > m.page) return [{ type: "list_sessions", page: m.page + 1, view: "alerts" }];
  const last = Math.max(m.pages, 1);
  if (m.view === "user" && s.view.tab === "tasks" && m.page > last && s.view.page === last) return [{ type: "list_sessions", page: last, view: "user" }];
  return [];
}

function without<K, V>(map: Map<K, V>, key: K): Map<K, V> {
  if (!map.has(key)) return map;
  const next = new Map(map);
  next.delete(key);
  return next;
}

// 준비 중 줄이 사라지는 줄: 결과·실패·질문·등록 확인
const ENDS_ACTIVITY = new Set<Entry["kind"]>(["result", "failure", "question", "proposal"]);

// 지운 세션을 모든 곳에서 뺀다. 보던 화면이 그 세션이면 그 탭 목록으로 보낸다
function deleteSession(s: State, id: number): State {
  const page = <T>(p: Page<T> | undefined, keep: (x: T) => boolean) => p && { ...p, items: p.items.filter(keep) };
  const v = s.view;
  const view: View = v.sessionId === id ? { tab: v.tab, screen: "list", page: v.page } : v;
  return {
    ...s, view,
    sessions: without(s.sessions, id), entries: without(s.entries, id), schedules: without(s.schedules, id),
    activity: without(s.activity, id),
    chatSessionId: s.chatSessionId === id ? null : s.chatSessionId,
    lists: {
      user: page(s.lists.user, (t) => t.id !== id), alerts: page(s.lists.alerts, (t) => t.id !== id),
      schedules: page(s.lists.schedules, (r) => r.session_id !== id),
    },
  };
}

// now: activity의 since로 잡을 현재 시각(ms). 테스트에서 시계를 넣는다
export function apply(s: State, m: BackendMessage, now: number = Date.now()): State {
  switch (m.type) {
    case "status":
      return { ...s, connected: true, loggedIn: m.logged_in, loggingIn: false };
    case "session": {
      const activity = m.session.state === "working" ? s.activity : without(s.activity, m.session.id);
      return { ...s, ...withSessions(s, [m.session]), activity };
    }
    case "entry":
      return {
        ...s, entries: new Map(s.entries).set(m.session_id, mergeEntries(s.entries.get(m.session_id), [m.entry])),
        activity: ENDS_ACTIVITY.has(m.entry.kind) ? without(s.activity, m.session_id) : s.activity,
      };
    case "session_deleted":
      return deleteSession(s, m.session_id);
    case "activity": {
      const since = s.activity.get(m.session_id)?.since ?? now;
      return { ...s, activity: new Map(s.activity).set(m.session_id, { kind: m.kind, text: m.text, since }) };
    }
    case "sessions": {
      // 배지 훑기: 알림 1쪽이 오면 알림 대상 세션을 지우고 1쪽부터 다시 채운다(뒤쪽은 followUps로 이어 받는다).
      // 그래야 끊긴 사이 알림에서 빠진 세션이 배지에 남지 않는다
      const base = m.view === "alerts" && m.page === 1 ? { ...s, sessions: withoutAlerts(s.sessions, m.items) } : s;
      const next = withSessions(base, m.items);
      // 이 목록을 보이는 탭에서 보던 쪽이 쪽 수보다 크면 마지막 쪽으로 당긴다
      const own = m.view === "alerts" ? "alerts" : "tasks";
      const last = Math.max(m.pages, 1);
      const view = s.view.tab === own && s.view.page > last ? { ...s.view, page: last } : s.view;
      // 훑기·최근 작업 요청으로 온 쪽이 보고 있는 쪽을 덮지 않게, 보고 있는 쪽(그 탭이 아니면 1쪽)만 목록에 둔다
      const shown = m.page === (view.tab === own ? view.page : 1);
      const lists = shown ? { ...next.lists, [m.view]: { page: m.page, pages: m.pages, items: m.items } } : next.lists;
      return { ...s, ...next, lists, view };
    }
    case "session_detail": {
      const entries = new Map(s.entries).set(m.session.id, mergeEntries(s.entries.get(m.session.id), m.entries));
      const schedules = m.schedule ? new Map(s.schedules).set(m.session.id, m.schedule) : s.schedules;
      return { ...s, ...withSessions(s, [m.session]), entries, schedules };
    }
    case "schedules":
      return { ...s, lists: { ...s.lists, schedules: { page: m.page, pages: m.pages, items: m.items } } };
    case "schedule": {
      const sc = m.schedule;
      const rows = s.lists.schedules;
      // 목록 줄도 고친다. 도는 중이면 그대로 두고, 아니면 켜짐·꺼짐을 따른다
      const row = (r: ScheduleRow): ScheduleRow => r.session_id !== sc.session_id ? r : {
        ...r, name: sc.name, label: sc.label, next_run: sc.next_run,
        state: r.state === "running" ? "running" : sc.enabled ? "next" : "off",
      };
      return {
        ...s,
        schedules: new Map(s.schedules).set(sc.session_id, sc),
        lists: rows ? { ...s.lists, schedules: { ...rows, items: rows.items.map(row) } } : s.lists,
      };
    }
    case "settings":
      return { ...s, settings: { permissionMode: m.permission_mode, recording: m.recording, jevKeySet: m.jev_key_set } };
    case "nudge":
      return { ...s, nudge: m.active };
    case "usage":
      return { ...s, limits: m.limits };
  }
}

// 걸린 시간 글: 60초까지는 `<N>초`, 넘으면 `<M>분 <N>초`
export function elapsedText(ms: number): string {
  const sec = Math.max(0, Math.floor(ms / 1000));
  return sec > 60 ? `${Math.floor(sec / 60)}분 ${sec % 60}초` : `${sec}초`;
}

// 대화 세션(source: "chat")은 목록·알림·배지에 넣지 않는다 (프로토콜 문서)
const listed = (s: State) => [...s.sessions.values()].filter((t) => t.source !== "chat");
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
// 작업 1쪽(최근 작업: 일하는 중인 세션은 대개 최근이라 강아지 자세에 필요)을 보낸다
export function refreshRequests(s: State): Outgoing[] {
  const out: Outgoing[] = [{ type: "list_sessions", page: 1, view: "alerts" }, { type: "list_sessions", page: 1, view: "user" }];
  const v = s.view;
  if (v.screen === "task" || v.screen === "schedule" || v.screen === "editSchedule") {
    if (v.sessionId !== undefined) out.push({ type: "get_session", session_id: v.sessionId });
    return out;
  }
  if (v.screen !== "list") return out;
  switch (v.tab) {
    case "alerts": break; // 보고 있는 쪽은 배지 훑기가 받아 온다
    case "tasks": if (v.page !== 1) out.push({ type: "list_sessions", page: v.page, view: "user" }); break;
    case "schedules": out.push({ type: "list_schedules", page: v.page }); break;
    case "chat": if (s.chatSessionId !== null) out.push({ type: "get_session", session_id: s.chatSessionId }); break;
    case "settings": out.push({ type: "get_settings" }); break;
    case "usage": out.push({ type: "get_usage" }); break;
  }
  return out;
}

// --- 큰 창 (12): 패널과 따로 화면을 갖는다. 주 창이 큰 창 몫의 State를 하나 더 들고 같은 메시지를 apply한다 ---
// 알림·작업·스케줄 탭은 두 칸이다: 대화·양식을 열어도 왼쪽에 그 탭 목록이 늘 보인다
export const TWO_COLUMN = new Set<Tab>(["alerts", "tasks", "schedules"]);

// 왼쪽 목록이 보이는 상태: 두 칸 탭이면 같은 탭·쪽의 목록 화면으로 본다
function withListView(s: State): State {
  const v = s.view;
  return TWO_COLUMN.has(v.tab) && v.screen !== "list" ? { ...s, view: { tab: v.tab, screen: "list", page: v.page } } : s;
}

const unique = (xs: Outgoing[]): Outgoing[] => {
  const seen = new Set<string>();
  return xs.filter((x) => { const k = JSON.stringify(x); return !seen.has(k) && !!seen.add(k); });
};

// 큰 창 화면에 필요한 요청: 오른쪽(대화·양식)과 왼쪽 목록
export const bigRequests = (s: State): Outgoing[] => unique([...refreshRequests(s), ...refreshRequests(withListView(s))]);
// 큰 창 화면에서 메시지를 받은 뒤 이어서 보낼 요청: 왼쪽 목록이 보이는 것으로 계산한다
export const bigFollowUps = (s: State, m: BackendMessage): Outgoing[] => followUps(withListView(s), m);
// 주 창이 패널 요청과 큰 창 요청을 함께 보낼 때 같은 요청을 한 번만
export const mergeRequests = (...lists: Outgoing[][]): Outgoing[] => unique(lists.flat());

// 큰 창에 넘기는 상태. Tauri 이벤트는 JSON이라 Map은 [키, 값] 배열로 바꾼다
type MapKeys = "sessions" | "entries" | "schedules" | "activity";
export type Snapshot = Omit<State, MapKeys> & {
  sessions: [number, Session][]; entries: [number, Entry[]][]; schedules: [number, Schedule][]; activity: [number, Activity][];
};

export function toSnapshot(s: State): Snapshot {
  return { ...s, sessions: [...s.sessions], entries: [...s.entries], schedules: [...s.schedules], activity: [...s.activity] };
}

// prev: 큰 창이 지난번에 되살린 상태. 값이 같은 세션·대화 줄은 그 객체를 다시 써서
// 대화 화면이 참조 비교로 다시 그리지 않게 한다(다른 세션 소식에 선택·포커스가 풀리지 않게)
export function fromSnapshot(x: Snapshot, prev?: State): State {
  const keep = <V>(old: Map<number, V> | undefined, pairs: [number, V][]): Map<number, V> => new Map(pairs.map(([k, v]) => {
    const o = old?.get(k);
    return [k, o !== undefined && JSON.stringify(o) === JSON.stringify(v) ? o : v];
  }));
  return {
    ...x, sessions: keep(prev?.sessions, x.sessions), entries: keep(prev?.entries, x.entries),
    schedules: new Map(x.schedules), activity: new Map(x.activity),
  };
}

// 알림 탭: 보고 있는 쪽의 첫 `waiting` 세션만 질문 카드로 보인다. 나머지는 행
export const firstWaiting = (s: State): Session | undefined => s.lists.alerts?.items.find((t) => t.state === "waiting");

export function alertRows(s: State): Session[] {
  const card = firstWaiting(s);
  return (s.lists.alerts?.items ?? []).filter((t) => t !== card);
}

// 아직 답하지 않은 질문: 마지막 사용자 줄 뒤의 마지막 `question` 줄 (캐시에 있을 때만)
export function pendingQuestion(s: State, sessionId: number): Entry | undefined {
  const es = s.entries.get(sessionId) ?? [];
  for (let i = es.length - 1; i >= 0; i--) {
    if (es[i].kind === "user") return undefined;
    if (es[i].kind === "question") return es[i];
  }
  return undefined;
}

export const STATE_TEXT: Record<Session["state"], string> = {
  working: "일하는 중", waiting: "답을 기다려요", done: "다 했어요", failed: "못 했어요", stopped: "멈췄어요",
};

// 목록 행의 부가 글: 질문을 기다리면 그 질문 글(캐시에 있으면), 아니면 상태 글
export function rowNote(s: State, t: Session): string {
  return (t.state === "waiting" && pendingQuestion(s, t.id)?.text) || STATE_TEXT[t.state];
}

// 열어 본 것으로 알릴 세션: 끝났고 아직 안 봤다 (대화 세션은 알림에 없으니 뺀다)
export function needsSeen(s: State, sessionId: number): boolean {
  const t = s.sessions.get(sessionId);
  return !!t && t.source !== "chat" && !t.seen && (t.state === "done" || t.state === "failed" || t.state === "stopped");
}
