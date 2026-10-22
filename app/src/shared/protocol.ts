// 백엔드 프로토콜 v7 (docs/backend-protocol.md). 메시지 이름·필드는 그 문서와 같다.
export const PROTOCOL_VERSION = 7;

const SOURCES = ["user", "schedule", "chat"] as const;
const SESSION_STATES = ["working", "waiting", "done", "failed", "stopped"] as const;
const KINDS = ["user", "progress", "question", "result", "failure", "proposal", "run", "edit", "chip"] as const;
const REPEATS = ["daily", "weekdays", "weekly", "monthly"] as const;
const RESULTS = ["done", "failed", "stopped"] as const;
const ROW_STATES = ["running", "next", "off"] as const;
const VIEWS = ["user", "alerts"] as const;
const ACTIVITY_KINDS = ["thinking", "tool", "writing"] as const;
const MODES = ["default", "acceptEdits", "plan", "auto", "bypassPermissions"] as const;

export type SessionState = (typeof SESSION_STATES)[number];
export type PermissionMode = (typeof MODES)[number];
export type ActivityKind = (typeof ACTIVITY_KINDS)[number];
export type ListView = (typeof VIEWS)[number];

export type Session = {
  id: number; source: (typeof SOURCES)[number]; title: string; state: SessionState;
  seen: boolean; claude_session_id: string | null; created_at: string;
};
export type Entry = {
  id: number; session_id: number; at: string; kind: (typeof KINDS)[number]; text: string;
  choices: string[] | null; data: Record<string, unknown> | null;
};
export type Rule = { repeat: (typeof REPEATS)[number]; time: string; weekday?: number; day?: number };
export type Schedule = {
  session_id: number; name: string; rule: Rule; instruction: string; label: string; enabled: boolean;
  next_run: string | null; last_run_at: string | null; last_result: (typeof RESULTS)[number] | null;
};
export type ScheduleRow = { session_id: number; name: string; label: string; next_run: string | null; state: (typeof ROW_STATES)[number] };
// 사용량 한도 하나. 종류 이름과 값의 모양은 아직 실제로 확인하지 않았다 (프로토콜 문서)
export type Limit = { type: string; utilization: number | null; resets_at: number | string | null; received_at: string };
export type Page<T> = { page: number; pages: number; items: T[] };

export type BackendMessage =
  | { type: "status"; logged_in: boolean }
  | { type: "session"; session: Session }
  | { type: "entry"; session_id: number; entry: Entry }
  | ({ type: "sessions"; view: ListView } & Page<Session>)
  | { type: "session_detail"; session: Session; entries: Entry[]; schedule: Schedule | null }
  | ({ type: "schedules" } & Page<ScheduleRow>)
  | { type: "schedule"; schedule: Schedule }
  | { type: "settings"; permission_mode: PermissionMode; recording: boolean }
  | { type: "usage"; limits: Limit[] }
  | { type: "session_deleted"; session_id: number }
  | { type: "activity"; session_id: number; kind: ActivityKind; text: string };

type ScheduleFields = { name: string; rule: Rule; instruction: string };
export type Outgoing =
  | { type: "hello"; token: string }
  | { type: "login" }
  | { type: "logout" }
  | { type: "request"; text: string }
  | ({ type: "add_schedule" } & ScheduleFields)
  | { type: "say"; session_id: number; text: string }
  | { type: "stop"; session_id: number }
  | { type: "seen"; session_id: number }
  | { type: "list_sessions"; page: number; view: ListView }
  | { type: "get_session"; session_id: number }
  | { type: "delete_session"; session_id: number }
  | { type: "list_schedules"; page: number }
  | ({ type: "set_schedule"; session_id: number } & ScheduleFields)
  | { type: "set_schedule_enabled"; session_id: number; enabled: boolean }
  | { type: "get_settings" }
  | { type: "set_permission_mode"; mode: PermissionMode }
  | { type: "set_recording"; enabled: boolean }
  | { type: "get_usage" };

// --- 모양 검사 ---
type O = Record<string, unknown>;
const isObj = (x: unknown): x is O => typeof x === "object" && x !== null && !Array.isArray(x);
const isInt = (x: unknown): x is number => Number.isInteger(x);
const isStr = (x: unknown): x is string => typeof x === "string";
const isBool = (x: unknown): x is boolean => typeof x === "boolean";
const orNull = <T>(f: (x: unknown) => x is T) => (x: unknown): x is T | null => x === null || f(x);
const oneOf = <T extends string>(xs: readonly T[]) => (x: unknown): x is T => xs.includes(x as T);
const listOf = <T>(f: (x: unknown) => boolean) => (x: unknown): x is T[] => Array.isArray(x) && x.every(f);

const isSession = (x: unknown): x is Session => isObj(x) && isInt(x.id) && oneOf(SOURCES)(x.source) && isStr(x.title)
  && oneOf(SESSION_STATES)(x.state) && isBool(x.seen) && orNull(isStr)(x.claude_session_id) && isStr(x.created_at);
const isEntry = (x: unknown): x is Entry => isObj(x) && isInt(x.id) && isInt(x.session_id) && isStr(x.at)
  && oneOf(KINDS)(x.kind) && isStr(x.text) && orNull(listOf<string>(isStr))(x.choices) && orNull(isObj)(x.data);
const isRule = (x: unknown): x is Rule => isObj(x) && oneOf(REPEATS)(x.repeat) && isStr(x.time)
  && (x.weekday === undefined || isInt(x.weekday)) && (x.day === undefined || isInt(x.day));
const isSchedule = (x: unknown): x is Schedule => isObj(x) && isInt(x.session_id) && isStr(x.name) && isRule(x.rule)
  && isStr(x.instruction) && isStr(x.label) && isBool(x.enabled) && orNull(isStr)(x.next_run)
  && orNull(isStr)(x.last_run_at) && orNull(oneOf(RESULTS))(x.last_result);
const isRow = (x: unknown): x is ScheduleRow => isObj(x) && isInt(x.session_id) && isStr(x.name) && isStr(x.label)
  && orNull(isStr)(x.next_run) && oneOf(ROW_STATES)(x.state);
const isNum = (x: unknown): x is number => typeof x === "number";
const isLimit = (x: unknown): x is Limit => isObj(x) && isStr(x.type) && orNull(isNum)(x.utilization)
  && (x.resets_at === null || isNum(x.resets_at) || isStr(x.resets_at)) && isStr(x.received_at);
const isPage = (o: O, item: (x: unknown) => boolean) => isInt(o.page) && isInt(o.pages) && listOf(item)(o.items);

function valid(o: O): boolean {
  switch (o.type) {
    case "status": return isBool(o.logged_in);
    case "session": return isSession(o.session);
    case "entry": return isInt(o.session_id) && isEntry(o.entry);
    case "sessions": return oneOf(VIEWS)(o.view) && isPage(o, isSession);
    case "session_detail": return isSession(o.session) && listOf(isEntry)(o.entries) && orNull(isSchedule)(o.schedule);
    case "schedules": return isPage(o, isRow);
    case "schedule": return isSchedule(o.schedule);
    case "settings": return oneOf(MODES)(o.permission_mode) && isBool(o.recording);
    case "usage": return listOf(isLimit)(o.limits);
    case "session_deleted": return isInt(o.session_id);
    case "activity": return isInt(o.session_id) && oneOf(ACTIVITY_KINDS)(o.kind) && isStr(o.text);
    default: return false;
  }
}

// 버전이 7이 아니거나 모양이 틀리면 null. 돌려주는 값에는 `v`를 빼고 담는다
export function parseBackendMessage(raw: unknown): BackendMessage | null {
  let m: unknown;
  try { m = typeof raw === "string" ? JSON.parse(raw) : null; } catch { return null; }
  if (!isObj(m) || m.v !== PROTOCOL_VERSION || !valid(m)) return null;
  const { v: _v, ...rest } = m;
  return rest as BackendMessage;
}

export function outgoing(msg: Outgoing): string {
  return JSON.stringify({ v: PROTOCOL_VERSION, ...msg });
}
