import { describe, expect, it } from "vitest";
import { outgoing, parseBrainMessage } from "../src/shared/brain-protocol";

const msg = (o: object) => JSON.stringify({ v: 5, ...o });

describe("parseBrainMessage", () => {
  it("reads status", () => {
    expect(parseBrainMessage(msg({ type: "status", ai: "ok" }))).toEqual({ type: "status", ai: "ok" });
  });
  it("rejects bad input and old versions", () => {
    expect(parseBrainMessage("{oops")).toBeNull();
    expect(parseBrainMessage(JSON.stringify({ v: 4, type: "status", ai: "ok" }))).toBeNull();
    expect(parseBrainMessage(msg({ type: "reaction" }))).toBeNull();
    expect(parseBrainMessage(msg({ type: "status", ai: "maybe" }))).toBeNull();
    expect(parseBrainMessage(42)).toBeNull();
  });
});

describe("outgoing", () => {
  it("adds the protocol version", () => {
    expect(JSON.parse(outgoing({ type: "message", text: "안녕" }))).toEqual({ v: 5, type: "message", text: "안녕" });
  });
});
