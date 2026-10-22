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

  it("reads the message types", () => {
    const cases: object[] = [
      { type: "status", logged_in: true },
      { type: "session", session },
      { type: "entry", session_id: 2, entry },
      { type: "sessions", view: "alerts", page: 1, pages: 2, items: [session] },
      { type: "session_detail", session, entries: [entry], schedule: null },
      { type: "session_detail", session: { ...session, id: 3, source: "schedule" }, entries: [], schedule },
      { type: "schedules", page: 1, pages: 1, items: [{ session_id: 3, name: "주간 보고", label: "매주 수 09:00", next_run: null, state: "off" }] },
      { type: "schedule", schedule },
      { type: "settings", permission_mode: "acceptEdits", recording: false, recording_dir: "/home/x/.screenpipe", recording_bytes: 1536, jev_key_set: true },
      { type: "nudge", active: true },
      { type: "usage", limits: [{ type: "five_hour", utilization: 0.4, resets_at: 1761100000, received_at: "2026-10-22T09:00:00" }] },
      { type: "session_deleted", session_id: 2 },
      { type: "activity", session_id: 2, kind: "tool", text: "파일 읽는 중" },
    ];
    for (const c of cases) expect(parseBackendMessage(msg(c))).toEqual(c);
  });

  it("reads chip entry data and usage with empty values", () => {
    const chip = { ...entry, kind: "chip", choices: null, data: { session_id: 7 } };
    expect(parseBackendMessage(msg({ type: "entry", session_id: 2, entry: chip }))).toEqual({ type: "entry", session_id: 2, entry: chip });
    const lim = { type: "seven_day", utilization: null, resets_at: null, received_at: "2026-10-22T09:00:00" };
    expect(parseBackendMessage(msg({ type: "usage", limits: [lim] }))).toEqual({ type: "usage", limits: [lim] });
  });

  it("reads a nudge entry", () => {
    const nudge = { ...entry, kind: "nudge", text: "도움이 필요해?", choices: ["도와줘", "괜찮아"], data: { app: "EXCEL.EXE", window: "보고서" } };
    expect(parseBackendMessage(msg({ type: "entry", session_id: 2, entry: nudge }))).toEqual({ type: "entry", session_id: 2, entry: nudge });
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
    expect(parseBackendMessage(msg({ type: "settings", permission_mode: "yolo", recording: true, recording_dir: "d", recording_bytes: 0, jev_key_set: false }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "settings", permission_mode: "plan", recording: true }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "settings", permission_mode: "plan", recording: true, jev_key_set: false }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "settings", permission_mode: "plan", recording: true, recording_dir: "d", recording_bytes: "1", jev_key_set: false }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "nudge", active: "yes" }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "nudge" }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "usage", limits: [{ utilization: 1 }] }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "session_deleted", session_id: "2" }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "session_deleted" }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "activity", session_id: 2, kind: "dance", text: "x" }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "activity", session_id: 2, kind: "tool" }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "activity", kind: "tool", text: "x" }))).toBeNull();
  });
});

describe("outgoing", () => {
  it("adds v:7", () => {
    expect(JSON.parse(outgoing({ type: "say", session_id: 1, text: "안녕" }))).toEqual({ v: 7, type: "say", session_id: 1, text: "안녕" });
    expect(JSON.parse(outgoing({ type: "delete_session", session_id: 4 }))).toEqual({ v: 7, type: "delete_session", session_id: 4 });
    expect(JSON.parse(outgoing({ type: "get_settings" }))).toEqual({ v: 7, type: "get_settings" });
    expect(JSON.parse(outgoing({ type: "clear_recording" }))).toEqual({ v: 7, type: "clear_recording" });
    expect(JSON.parse(outgoing({ type: "nudge_open" }))).toEqual({ v: 7, type: "nudge_open" });
    expect(JSON.parse(outgoing({ type: "nudge_answer", help: false }))).toEqual({ v: 7, type: "nudge_answer", help: false });
    expect(JSON.parse(outgoing({ type: "set_jev_key", key: "k" }))).toEqual({ v: 7, type: "set_jev_key", key: "k" });
  });
});
