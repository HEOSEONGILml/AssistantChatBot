import type { Entry, Task } from "./protocol";

export type Item = {
  kind: "user" | "agent" | "failure" | "progress" | "question" | "proposal" | "run" | "chip";
  entries: Entry[];
  text: string;
  choices?: string[];
  data?: unknown;
  spinning?: boolean;
  // 질문·등록 확인 카드가 아직 답을 기다리는지 (버튼을 보일지)
  answerable: boolean;
};

const kindOf = (k: Entry["kind"]): Item["kind"] => (k === "result" || k === "edit" ? "agent" : k);

export function toItems(entries: Entry[], taskState: Task["state"]): Item[] {
  const items: Item[] = [];
  for (const en of entries) {
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
  if (tail?.kind === "progress" && taskState === "working") tail.spinning = true;

  if (taskState === "waiting") {
    for (let i = items.length - 1; i >= 0; i--) {
      const k = items[i].kind;
      if (k === "user") break;
      if (k === "question" || k === "proposal") { items[i].answerable = true; break; }
    }
  }
  return items;
}

// 선택지 버튼을 한 번 누른 뒤 막아 둘 때 쓰는 열쇠: 작업 상태나 마지막 줄이 바뀌면 달라진다
export const answerKey = (t: Task, entries: Entry[]): string =>
  `${t.id}:${t.state}:${entries[entries.length - 1]?.id ?? 0}`;

// 선택지를 눌러 답을 보낸 작업 상태(answerKey). 작업·줄이 바뀌기 전에는 버튼을 막아 두 번 답하지 않게 한다.
// 창마다 하나(주 창·상세 창). 끊기면 비우고, 답을 기다리지 않는 작업의 열쇠는 지운다
export const answered = new Set<string>();

export function pruneAnswered(keys: Set<string>, isWaiting: (taskId: number) => boolean): void {
  for (const k of keys) if (!isWaiting(Number(k.split(":")[0]))) keys.delete(k);
}
