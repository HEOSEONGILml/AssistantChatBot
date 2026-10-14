import { test, expect } from "vitest";
import { showBubble, tickBubble, keepAfterSeenMs, SEEN_MS } from "../src/body/bubble";

test("사용자가 자리를 비운 동안은 노출 시간을 세지 않는다", () => {
  const r = tickBubble(showBubble("멍"), 1000, SEEN_MS, false);
  expect(r.bubble!.visibleMs).toBe(0);
  expect(r.justSeen).toBe(false);
});

test("노출 시간이 SEEN_MS에 닿으면 한 번만 justSeen", () => {
  let r = tickBubble(showBubble("멍"), 1000, SEEN_MS, true);
  expect(r.justSeen).toBe(true);
  expect(r.bubble!.seenAt).toBe(1000);
  r = tickBubble(r.bubble, 2000, 1000, true);
  expect(r.justSeen).toBe(false);
});

test("짧은 글은 봤다 판정 5초 뒤 사라진다", () => {
  const seen = tickBubble(showBubble("멍"), 1000, SEEN_MS, true).bubble;
  expect(tickBubble(seen, 1000 + 4999, 16, true).bubble).not.toBeNull();
  expect(tickBubble(seen, 1000 + 5000, 16, true).bubble).toBeNull();
});

test("긴 글은 글자 수만큼 더 오래 남는다", () => {
  expect(keepAfterSeenMs("멍")).toBe(5000);
  expect(keepAfterSeenMs("가".repeat(100))).toBe(15000);
});

test("봤다 판정 뒤에는 자리를 비워도 정해진 시간에 사라진다", () => {
  const seen = tickBubble(showBubble("멍"), 1000, SEEN_MS, true).bubble;
  expect(tickBubble(seen, 1000 + 5000, 16, false).bubble).toBeNull();
});

test("말풍선이 없으면 그대로 null", () => expect(tickBubble(null, 0, 16, true)).toEqual({ bubble: null, justSeen: false }));
