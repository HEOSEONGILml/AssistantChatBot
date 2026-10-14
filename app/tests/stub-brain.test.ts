import { test, expect } from "vitest";
import { stubReact } from "../src/body/stub-brain";

test("보내면 짖고 말한다", () => expect(stubReact({ kind: "sent", text: "안녕" })).toMatchObject({ action: "bark" }));
test("타이핑 중이면 앉아서 듣는다", () => expect(stubReact({ kind: "typing", text: "안" })).toEqual({ action: "idle_sit" }));
test("그 밖에는 반응 없음", () => expect(stubReact({ kind: "bubble_seen" })).toBeNull());
