import type { Entry, Session } from "./protocol";
import type { Tab, View } from "./state";

export type Item = {
  kind: "user" | "agent" | "failure" | "progress" | "question" | "proposal" | "run" | "chip" | "nudge";
  entries: Entry[];
  text: string;
  choices?: string[];
  data?: unknown;
  spinning?: boolean;
  // 질문·등록 확인·먼저 말 걸기 카드가 아직 답을 기다리는지 (버튼을 보일지)
  answerable: boolean;
};

const kindOf = (k: Entry["kind"]): Item["kind"] => (k === "result" || k === "edit" ? "agent" : k);

// 대화 탭(chat) 세션은 진행을 그리지 않는다 (설계 18번에 진행 칩이 없다)
// statusShown: 준비 중 줄이 보이는 중. 그동안 진행 칩의 스피너는 그리지 않는다(돌고 있다는 표시가 둘이 되지 않게)
export function toItems(entries: Entry[], sessionState: Session["state"], source: Session["source"] = "user", statusShown = false): Item[] {
  const items: Item[] = [];
  for (const en of entries) {
    if (source === "chat" && en.kind === "progress") continue;
    const last = items[items.length - 1];
    if (en.kind === "progress" && last?.kind === "progress") {
      last.entries.push(en);
      last.text = `진행 ${last.entries.length}단계 · ${en.text}`;
      continue;
    }
    const item: Item = { kind: kindOf(en.kind), entries: [en], text: en.text, answerable: false };
    if (en.kind === "progress") item.text = `진행 1단계 · ${en.text}`;
    if (en.choices) item.choices = en.choices;
    if (en.data) item.data = en.data;
    items.push(item);
  }
  const tail = items[items.length - 1];
  if (tail?.kind === "progress" && sessionState === "working" && !statusShown) tail.spinning = true;

  if (sessionState === "waiting") {
    for (let i = items.length - 1; i >= 0; i--) {
      const k = items[i].kind;
      // [도와줘]·[괜찮아]는 nudge의 답이지 질문의 답이 아니다 (백엔드는 기다리는 질문에 넣지 않는다)
      if (k === "user" && items[i - 1]?.kind === "nudge") { i--; continue; }
      if (k === "user") break;
      if (k === "question" || k === "proposal") { items[i].answerable = true; break; }
    }
  }
  // 먼저 말 걸기: 세션 상태와 상관없이, 마지막 nudge 줄 뒤에 user 줄이 없을 때 (backend는 `nudge_answer`로 받는다)
  for (let i = items.length - 1; i >= 0; i--) {
    const k = items[i].kind;
    if (k === "user") break;
    if (k === "nudge") { items[i].answerable = true; break; }
  }
  return items;
}

// 선택지 버튼을 한 번 누른 뒤 막아 둘 때 쓰는 열쇠: 세션 상태나 마지막 줄이 바뀌면 달라진다
export const answerKey = (t: Session, entries: Entry[]): string =>
  `${t.id}:${t.state}:${entries[entries.length - 1]?.id ?? 0}`;

// 선택지를 눌러 답을 보낸 세션 상태(answerKey). 세션·줄이 바뀌기 전에는 버튼을 막아 두 번 답하지 않게 한다.
// 창마다 하나(주 창·큰 창). 끊기면 비우고, 답을 기다리지 않는 세션의 열쇠는 지운다
export const answered = new Set<string>();

export function pruneAnswered(keys: Set<string>, isWaiting: (sessionId: number) => boolean): void {
  for (const k of keys) if (!isWaiting(Number(k.split(":")[0]))) keys.delete(k);
}

// 세션 종류마다 그 세션이 사는 탭
export const TAB_OF: Record<Session["source"], Tab> = { user: "tasks", schedule: "schedules", chat: "chat" };

// 세션 칩: create_session으로 만든 세션. 지금 탭 안에서 그 종류의 화면으로 연다. 종류가 없는 옛 칩은 작업이다
export function chipTarget(data: unknown, current: Session["source"]): { label: string; view: View } | null {
  const d = (data ?? {}) as { session_id?: unknown; source?: unknown };
  if (typeof d.session_id !== "number") return null;
  const schedule = d.source === "schedule";
  return {
    label: schedule ? "스케줄" : "작업",
    view: { tab: TAB_OF[current], screen: schedule ? "schedule" : "task", sessionId: d.session_id, page: 1 },
  };
}
