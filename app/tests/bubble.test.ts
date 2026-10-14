import { test, expect } from "vitest";
import { showBubble, tickBubble, SEEN_MS, KEEP_AFTER_SEEN_MS } from "../src/body/bubble";

test("가려진 시간은 누적하지 않는다", () => {
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

test("봤다 판정 후 KEEP_AFTER_SEEN_MS가 지나면 사라진다", () => {
  const seen = tickBubble(showBubble("멍"), 1000, SEEN_MS, true).bubble;
  expect(tickBubble(seen, 1000 + KEEP_AFTER_SEEN_MS - 1, 16, true).bubble).not.toBeNull();
  expect(tickBubble(seen, 1000 + KEEP_AFTER_SEEN_MS, 16, true).bubble).toBeNull();
});

test("말풍선이 없으면 그대로 null", () => expect(tickBubble(null, 0, 16, true)).toEqual({ bubble: null, justSeen: false }));
