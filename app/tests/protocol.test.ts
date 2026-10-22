import { describe, expect, it } from "vitest";
import { outgoing, parseBackendMessage, PROTOCOL_VERSION } from "../src/shared/protocol";

const msg = (o: object) => JSON.stringify({ v: 7, ...o });

const session = { id: 2, source: "user", title: "회의 자료", state: "working", seen: false, claude_session_id: null, created_at: "2026-10-22T09:00:00" };
const entry = { id: 5, session_id: 2, at: "2026-10-22T09:00:01", kind: "question", text: "어느 폴더?", choices: ["A", "B"], data: null };
const rule = { repeat: "weekly", time: "09:00", weekday: 2 };
const schedule = {
  session_id: 3, name: "주간 보고", rule, instruction: "보고서 정리", label: "매주 수 09:00", enabled: true,
  next_run: "2026-10-28T09:00:00", last_run_at: null, last_result: null,
};

describe("parseBackendMessage", () => {
  it("version is 7", () => { expect(PROTOCOL_VERSION).toBe(7); });

  it("reads the 9 message types", () => {
    const cases: object[] = [
      { type: "status", logged_in: true },
      { type: "session", session },
      { type: "entry", session_id: 2, entry },
      { type: "sessions", view: "alerts", page: 1, pages: 2, items: [session] },
      { type: "session_detail", session, entries: [entry], schedule: null },
      { type: "session_detail", session: { ...session, id: 3, source: "schedule" }, entries: [], schedule },
      { type: "schedules", page: 1, pages: 1, items: [{ session_id: 3, name: "주간 보고", label: "매주 수 09:00", next_run: null, state: "off" }] },
      { type: "schedule", schedule },
      { type: "settings", permission_mode: "acceptEdits", recording: false },
      { type: "usage", limits: [{ type: "five_hour", utilization: 0.4, resets_at: 1761100000, received_at: "2026-10-22T09:00:00" }] },
    ];
    for (const c of cases) expect(parseBackendMessage(msg(c))).toEqual(c);
  });

  it("reads chip entry data and usage with empty values", () => {
    const chip = { ...entry, kind: "chip", choices: null, data: { session_id: 7 } };
    expect(parseBackendMessage(msg({ type: "entry", session_id: 2, entry: chip }))).toEqual({ type: "entry", session_id: 2, entry: chip });
    const lim = { type: "seven_day", utilization: null, resets_at: null, received_at: "2026-10-22T09:00:00" };
    expect(parseBackendMessage(msg({ type: "usage", limits: [lim] }))).toEqual({ type: "usage", limits: [lim] });
  });

  it("rejects version 5", () => {
    expect(parseBackendMessage(JSON.stringify({ v: 5, type: "status", logged_in: true }))).toBeNull();
    expect(parseBackendMessage(JSON.stringify({ type: "status", logged_in: true }))).toBeNull();
  });

  it("rejects unknown types and wrong shapes", () => {
    expect(parseBackendMessage("{oops")).toBeNull();
    expect(parseBackendMessage(42)).toBeNull();
    expect(parseBackendMessage(msg({ type: "reaction" }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "status", logged_in: 1 }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "session", session: { ...session, state: "sleeping" } }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "session", session: { ...session, id: "2" } }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "session", session: { ...session, id: true } }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "entry", session_id: 2, entry: { ...entry, kind: "poem" } }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "entry", session_id: 2, entry: { ...entry, choices: [1] } }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "sessions", view: "all", page: 1, pages: 1, items: [] }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "sessions", view: "user", page: 1, pages: 1, items: [{}] }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "schedule", schedule: { ...schedule, enabled: "yes" } }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "schedules", page: 1, pages: 1, items: [{ session_id: 3, name: "x", label: "y", next_run: null, state: "on" }] }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "settings", permission_mode: "yolo", recording: true }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "usage", limits: [{ utilization: 1 }] }))).toBeNull();
  });
});

describe("outgoing", () => {
  it("adds v:7", () => {
    expect(JSON.parse(outgoing({ type: "say", session_id: 1, text: "안녕" }))).toEqual({ v: 7, type: "say", session_id: 1, text: "안녕" });
    expect(JSON.parse(outgoing({ type: "get_settings" }))).toEqual({ v: 7, type: "get_settings" });
  });
});
