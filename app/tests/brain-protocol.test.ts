import { describe, expect, it } from "vitest";
import { ACTION_TO_DOG, outgoing, parseBrainMessage, statusText } from "../src/shared/brain-protocol";
import { DOG_ACTIONS } from "../src/body/sprite";

const msg = (o: object) => JSON.stringify({ v: 2, ...o });
const weights = { rest: 0.6, sleep: 0.02, roam: 0.4, approach: 0.18, play: 0.06, explore: 0.2 };

describe("parseBrainMessage", () => {
  it("reads a full reaction", () => {
    expect(parseBrainMessage(msg({ type: "reaction", reaction: "joy", action: "bark", utterance: "멍!" })))
      .toEqual({ type: "reaction", reaction: "joy", action: "bark", utterance: "멍!" });
  });
  it("drops unknown vocabulary but keeps the rest", () => {
    expect(parseBrainMessage(msg({ type: "reaction", reaction: "hungry", action: "dance", utterance: "멍" })))
      .toEqual({ type: "reaction", utterance: "멍" });
  });
  it("reads status", () => {
    expect(parseBrainMessage(msg({ type: "status", ai: "bad_key" }))).toEqual({ type: "status", ai: "bad_key" });
  });
  it("reads movement", () => {
    expect(parseBrainMessage(msg({ type: "movement", weights, run: 0.2, idle_scale: 1.3 })))
      .toEqual({ type: "movement", movement: { weights, run: 0.2, idleScale: 1.3 } });
  });
  it("rejects broken movement", () => {
    expect(parseBrainMessage(msg({ type: "movement", weights: { ...weights, play: -1 }, run: 0.2, idle_scale: 1 }))).toBeNull();
    expect(parseBrainMessage(msg({ type: "movement", weights: { rest: 1 }, run: 0.2, idle_scale: 1 }))).toBeNull();
    expect(parseBrainMessage(msg({ type: "movement", weights, run: 2, idle_scale: 1 }))).toBeNull();
    expect(parseBrainMessage(msg({ type: "movement", weights, run: 0.2, idle_scale: 0 }))).toBeNull();
  });
  it("rejects bad input and old versions", () => {
    expect(parseBrainMessage("{oops")).toBeNull();
    expect(parseBrainMessage(JSON.stringify({ v: 1, type: "status", ai: "ok" }))).toBeNull();
    expect(parseBrainMessage(msg({ type: "dance" }))).toBeNull();
    expect(parseBrainMessage(msg({ type: "status", ai: "maybe" }))).toBeNull();
    expect(parseBrainMessage(42)).toBeNull();
  });
});

describe("outgoing", () => {
  it("adds the protocol version", () => {
    expect(JSON.parse(outgoing({ type: "event", kind: "poke", context: {} }))).toEqual({ v: 2, type: "event", kind: "poke", context: {} });
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
