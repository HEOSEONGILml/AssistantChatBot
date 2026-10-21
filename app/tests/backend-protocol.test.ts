import { describe, expect, it } from "vitest";
import { outgoing, parseBackendMessage } from "../src/shared/backend-protocol";

const msg = (o: object) => JSON.stringify({ v: 5, ...o });

describe("parseBackendMessage", () => {
  it("reads status", () => {
    expect(parseBackendMessage(msg({ type: "status", ai: "ok" }))).toEqual({ type: "status", ai: "ok" });
  });
  it("rejects bad input and old versions", () => {
    expect(parseBackendMessage("{oops")).toBeNull();
    expect(parseBackendMessage(JSON.stringify({ v: 4, type: "status", ai: "ok" }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "reaction" }))).toBeNull();
    expect(parseBackendMessage(msg({ type: "status", ai: "maybe" }))).toBeNull();
    expect(parseBackendMessage(42)).toBeNull();
  });
});

describe("outgoing", () => {
  it("adds the protocol version", () => {
    expect(JSON.parse(outgoing({ type: "message", text: "안녕" }))).toEqual({ v: 5, type: "message", text: "안녕" });
  });
});
