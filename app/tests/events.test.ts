import { describe, expect, test } from "vitest";
import { feedTyping, impactOf, newTyping, quietDue, tickTyping, QUIET_AWAY_MS, QUIET_PRESENT_MS } from "../src/body/events";

describe("타이핑 판정", () => {
  test("멈춘 지 0.6초가 지나면 한 번 낸다", () => {
    let s = feedTyping(newTyping(), "안녕", 0).state;
    expect(tickTyping(s, 500).fire).toBe(false);
    const r = tickTyping(s, 600);
    expect(r.fire).toBe(true);
    s = r.state;
    expect(tickTyping(s, 2000).fire).toBe(false); // 같은 글로 다시 내지 않는다
  });
  test("지난번 낸 글보다 10자 넘게 바뀌면 바로 낸다", () => {
    const r = feedTyping(newTyping(), "오늘 회의가 너무 길", 0);
    expect(r.fire).toBe(true);
    expect(feedTyping(r.state, "오늘 회의가 너무 길어", 50).fire).toBe(false);
  });
  test("다 지우면 내지 않는다", () => {
    let s = feedTyping(newTyping(), "abc", 0).state;
    s = feedTyping(s, "", 100).state;
    expect(tickTyping(s, 5000).fire).toBe(false);
  });
});

describe("조용함", () => {
  test("자리에 있으면 10분, 비웠으면 30분", () => {
    expect(quietDue(0, QUIET_PRESENT_MS - 1, true)).toBe(false);
    expect(quietDue(0, QUIET_PRESENT_MS, true)).toBe(true);
    expect(quietDue(0, QUIET_PRESENT_MS, false)).toBe(false);
    expect(quietDue(0, QUIET_AWAY_MS, false)).toBe(true);
  });
});

describe("충격", () => {
  test("2000px/초면 1, 넘으면 1로 자르고 소수 둘째 자리", () => {
    expect(impactOf(1000)).toBe(0.5);
    expect(impactOf(5000)).toBe(1);
    expect(impactOf(333)).toBe(0.17);
  });
});
