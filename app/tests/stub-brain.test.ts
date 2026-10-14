import { test, expect } from "vitest";
import { stubReact } from "../src/body/stub-brain";

// 임시 두뇌는 동작을 정하지 않는다. 동작은 Jev가 판단한다 (기획). 보냈을 때 안내만 한다.
test("보내면 동작 없이 안내 말풍선만", () => {
  const r = stubReact({ kind: "sent", text: "안녕" });
  expect(r?.action).toBeUndefined();
  expect(r?.utterance).toContain("두뇌");
});
test("타이핑 중에는 아무 반응도 정하지 않는다", () => expect(stubReact({ kind: "typing", text: "안" })).toBeNull());
test("그 밖에는 반응 없음", () => expect(stubReact({ kind: "bubble_seen" })).toBeNull());
