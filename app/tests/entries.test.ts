import { describe, expect, it } from "vitest";
import { answerKey, chipTarget, pruneAnswered, toItems } from "../src/shared/entries";
import type { Entry } from "../src/shared/protocol";

let n = 0;
const e = (kind: Entry["kind"], text = "글", choices: string[] | null = null): Entry =>
  ({ id: ++n, session_id: 1, at: "2026-10-22T09:00:00", kind, text, choices, data: null });

describe("toItems", () => {
  it("이어진 progress를 하나로 접는다", () => {
    const items = toItems([e("user"), e("progress", "a"), e("progress", "b"), e("progress", "c")], "done");
    expect(items.map((i) => i.kind)).toEqual(["user", "progress"]);
    expect(items[1].text).toBe("진행 3단계 · c");
    expect(items[1].entries).toHaveLength(3);
  });

  it("끊긴 progress는 따로 접는다", () => {
    const items = toItems([e("progress", "a"), e("result", "끝"), e("progress", "b")], "done");
    expect(items.map((i) => i.text)).toEqual(["진행 1단계 · a", "끝", "진행 1단계 · b"]);
  });

  it("result와 edit은 agent, failure는 failure", () => {
    const items = toItems([e("result"), e("edit"), e("failure")], "failed");
    expect(items.map((i) => i.kind)).toEqual(["agent", "agent", "failure"]);
  });

  it("스피너는 working이고 마지막 묶음이 진행일 때만", () => {
    expect(toItems([e("progress")], "working")[0].spinning).toBe(true);
    expect(toItems([e("progress")], "done")[0].spinning).toBeFalsy();
    expect(toItems([e("progress"), e("result")], "working").some((i) => i.spinning)).toBe(false);
  });

  it("답할 수 있는 카드는 waiting에서 뒤에 user 줄이 없는 마지막 하나", () => {
    const items = toItems([e("question", "1", ["A"]), e("user"), e("question", "2", ["B"]), e("proposal", "3")], "waiting");
    expect(items.map((i) => i.answerable)).toEqual([false, false, false, true]);
    expect(items[2].choices).toEqual(["B"]);
  });

  it("waiting이 아니면 답할 수 없다", () => {
    expect(toItems([e("question")], "working")[0].answerable).toBe(false);
  });

  it("마지막 카드 뒤에 user 줄이 있으면 답할 수 없다", () => {
    expect(toItems([e("question"), e("user")], "waiting")[0].answerable).toBe(false);
  });

  it("run과 chip은 그대로 둔다", () => {
    expect(toItems([e("run"), e("chip")], "done").map((i) => i.kind)).toEqual(["run", "chip"]);
  });
});

describe("answerKey", () => {
  const t = (state: "waiting" | "working") => ({ id: 7, source: "user" as const, title: "t", state, seen: false, claude_session_id: null, created_at: "2026-10-22T09:00:00" });
  it("작업 상태나 마지막 줄이 바뀌면 달라진다", () => {
    const a = e("question", "q", ["예"]);
    const k = answerKey(t("waiting"), [a]);
    expect(answerKey(t("waiting"), [a])).toBe(k);
    expect(answerKey(t("working"), [a])).not.toBe(k);
    expect(answerKey(t("waiting"), [a, e("user")])).not.toBe(k);
    expect(answerKey(t("waiting"), [])).not.toBe(k);
  });
});

describe("pruneAnswered", () => {
  it("답을 기다리지 않는 작업의 열쇠를 지운다", () => {
    const keys = new Set(["7:waiting:3", "8:waiting:5", "12:waiting:1"]);
    pruneAnswered(keys, (id) => id === 8);
    expect([...keys]).toEqual(["8:waiting:5"]);
  });
});

describe("chipTarget", () => {
  it("만든 세션의 종류에 맞는 화면으로, 지금 탭 안에서 연다", () => {
    expect(chipTarget({ session_id: 7, source: "user" }, "chat"))
      .toEqual({ label: "작업", view: { tab: "chat", screen: "task", sessionId: 7, page: 1 } });
    expect(chipTarget({ session_id: 8, source: "schedule" }, "user"))
      .toEqual({ label: "스케줄", view: { tab: "tasks", screen: "schedule", sessionId: 8, page: 1 } });
  });

  it("종류가 없는 옛 칩은 작업으로, 세션 ID가 없으면 열지 않는다", () => {
    expect(chipTarget({ session_id: 3 }, "schedule")?.view.screen).toBe("task");
    expect(chipTarget({ source: "user" }, "chat")).toBeNull();
    expect(chipTarget(null, "chat")).toBeNull();
  });
});
