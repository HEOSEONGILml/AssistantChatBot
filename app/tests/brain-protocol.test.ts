import { describe, expect, it } from "vitest";
import { ACTION_TO_DOG, outgoing, parseBrainMessage, statusText } from "../src/shared/brain-protocol";
import { DOG_ACTIONS } from "../src/body/sprite";

const msg = (o: object) => JSON.stringify({ v: 3, ...o });
const weights = { rest: 0.6, sleep: 0.02, roam: 0.4, approach: 0.18, play: 0.06, explore: 0.2 };

describe("parseBrainMessage", () => {
  it("reads a full reaction", () => {
    expect(parseBrainMessage(msg({ type: "reaction", reaction: "excited", action: "bark", utterance: "멍!" })))
      .toEqual({ type: "reaction", reaction: "excited", action: "bark", utterance: "멍!" });
  });
  it("drops unknown vocabulary but keeps the rest", () => {
    expect(parseBrainMessage(msg({ type: "reaction", reaction: "hungry", action: "dance", utterance: "멍" })))
      .toEqual({ type: "reaction", utterance: "멍" });
  });
  it("reads status", () => {
    expect(parseBrainMessage(msg({ type: "status", ai: "bad_key" }))).toEqual({ type: "status", ai: "bad_key" });
  });
  it("reads movement", () => {
    expect(parseBrainMessage(msg({ type: "movement", weights, mood: "sad", run: 0.2, idle_scale: 1.3 })))
      .toEqual({ type: "movement", movement: { weights, run: 0.2, idleScale: 1.3 }, mood: "sad" });
    expect(parseBrainMessage(msg({ type: "movement", weights, mood: "weird", run: 0.2, idle_scale: 1 })))
      .toEqual({ type: "movement", movement: { weights, run: 0.2, idleScale: 1 }, mood: "calm" });
  });
  it("rejects broken movement", () => {
    expect(parseBrainMessage(msg({ type: "movement", weights: { ...weights, play: -1 }, run: 0.2, idle_scale: 1 }))).toBeNull();
    expect(parseBrainMessage(msg({ type: "movement", weights: { rest: 1 }, run: 0.2, idle_scale: 1 }))).toBeNull();
    expect(parseBrainMessage(msg({ type: "movement", weights, run: 2, idle_scale: 1 }))).toBeNull();
    expect(parseBrainMessage(msg({ type: "movement", weights, run: 0.2, idle_scale: 0 }))).toBeNull();
  });
  it("rejects bad input and old versions", () => {
    expect(parseBrainMessage("{oops")).toBeNull();
    expect(parseBrainMessage(JSON.stringify({ v: 2, type: "status", ai: "ok" }))).toBeNull();
    expect(parseBrainMessage(msg({ type: "dance" }))).toBeNull();
    expect(parseBrainMessage(msg({ type: "status", ai: "maybe" }))).toBeNull();
    expect(parseBrainMessage(42)).toBeNull();
  });
});

describe("outgoing", () => {
  it("adds the protocol version", () => {
    expect(JSON.parse(outgoing({ type: "event", kind: "poke", context: {} }))).toEqual({ v: 3, type: "event", kind: "poke", context: {} });
  });
});

describe("ACTION_TO_DOG", () => {
  it("maps every brain action to a body animation", () => {
    expect(Object.keys(ACTION_TO_DOG).sort()).toEqual(["bark", "beg", "lie_down", "sit", "sleep", "stand"]);
    for (const a of Object.values(ACTION_TO_DOG)) expect(DOG_ACTIONS).toContain(a);
  });
});

describe("statusText", () => {
  it("tells the user what to do", () => {
    expect(statusText("ok")).toBeNull();
    expect(statusText(null)).toBeNull();
    expect(statusText("no_keys")).toContain("키를 넣어");
    expect(statusText("bad_key")).toContain("키를 확인");
  });
});

describe("state·log 조회", () => {
  const state = { dog: { personality: { baseline: { 분노: 0.1 }, sensitivity: { 분노: 0.5 }, whim: 0.5, temperament: { 분노: 0.1 } }, mood: { 분노: 0.2 }, intimacy: 0.3, habit: { poke: 0 } }, talkativeness: 0.4, movement: { weights: {}, run: 0.2, idle_scale: 1 } };
  it("reads state", () => {
    expect(parseBrainMessage(msg({ type: "state", ...state }))).toEqual({ type: "state", state });
  });
  it("reads log", () => {
    const log = { judgements: [{ ts: 1, events: [{ 종류: "찌르기" }] }], events: ["방금 · 찌르기"], brain_log: ["줄"] };
    expect(parseBrainMessage(msg({ type: "log", ...log }))).toEqual({ type: "log", log });
  });
  it("rejects malformed state and log", () => {
    expect(parseBrainMessage(msg({ type: "state", talkativeness: 1 }))).toBeNull();
    expect(parseBrainMessage(msg({ type: "log", judgements: "x", events: [], brain_log: [] }))).toBeNull();
  });
  it("sends get_state and get_log", () => {
    expect(JSON.parse(outgoing({ type: "get_state" }))).toEqual({ v: 3, type: "get_state" });
    expect(JSON.parse(outgoing({ type: "get_log" }))).toEqual({ v: 3, type: "get_log" });
  });
});

describe("반응 어휘 v3", () => {
  it("기분 8개의 반응을 모두 읽는다", () => {
    for (const r of ["bored", "sleepy", "excited", "sad", "annoyed", "curious", "surprised", "scared", "happy"])
      expect(parseBrainMessage(msg({ type: "reaction", reaction: r }))).toEqual({ type: "reaction", reaction: r });
  });
});
