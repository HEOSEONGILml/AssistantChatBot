import { describe, expect, it } from "vitest";
import { ACTION_TO_DOG, outgoing, parseBrainMessage, statusText } from "../src/shared/brain-protocol";
import { DOG_ACTIONS } from "../src/body/sprite";

const msg = (o: object) => JSON.stringify({ v: 1, ...o });

describe("parseBrainMessage", () => {
  it("reads a full reaction", () => {
    expect(parseBrainMessage(msg({ type: "reaction", emotion: "excited", action: "bark", utterance: "멍!" })))
      .toEqual({ type: "reaction", emotion: "excited", action: "bark", utterance: "멍!" });
  });
  it("drops unknown vocabulary but keeps the rest", () => {
    expect(parseBrainMessage(msg({ type: "reaction", emotion: "hungry", action: "dance", utterance: "멍" })))
      .toEqual({ type: "reaction", utterance: "멍" });
  });
  it("drops a non-string utterance", () => {
    expect(parseBrainMessage(msg({ type: "reaction", utterance: 3 }))).toEqual({ type: "reaction" });
  });
  it("reads status", () => {
    expect(parseBrainMessage(msg({ type: "status", ai: "bad_key" }))).toEqual({ type: "status", ai: "bad_key" });
  });
  it("rejects bad input", () => {
    expect(parseBrainMessage("{oops")).toBeNull();
    expect(parseBrainMessage(JSON.stringify({ v: 2, type: "status", ai: "ok" }))).toBeNull();
    expect(parseBrainMessage(msg({ type: "dance" }))).toBeNull();
    expect(parseBrainMessage(msg({ type: "status", ai: "maybe" }))).toBeNull();
    expect(parseBrainMessage(42)).toBeNull();
  });
});

describe("outgoing", () => {
  it("adds the protocol version", () => {
    expect(JSON.parse(outgoing({ type: "clear_history" }))).toEqual({ v: 1, type: "clear_history" });
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
