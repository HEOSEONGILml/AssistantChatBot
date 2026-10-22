import { describe, expect, it } from "vitest";
import { nextDelay, RETRY_MIN_MS, RETRY_MAX_MS, noRetry } from "../src/shared/backoff";

describe("nextDelay", () => {
  it("2초에서 시작해 두 배씩 늘고 30초에서 멈춘다", () => {
    const seq: number[] = [];
    let d = RETRY_MIN_MS;
    for (let i = 0; i < 6; i++) { seq.push(d); d = nextDelay(d); }
    expect(seq).toEqual([2000, 4000, 8000, 16000, 30000, 30000]);
    expect(RETRY_MAX_MS).toBe(30000);
  });
});

describe("noRetry", () => {
  it("백엔드가 일부러 닫은 코드(4001~4003)는 다시 띄우지 않는다", () => {
    expect([4001, 4002, 4003].every(noRetry)).toBe(true);
    expect([1000, 1006, 4000, 4004].some(noRetry)).toBe(false);
  });
});
