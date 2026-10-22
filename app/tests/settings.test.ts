import { describe, expect, it } from "vitest";
import { PERMISSION_MODES } from "../src/shared/settings";

describe("PERMISSION_MODES", () => {
  it("프로토콜의 권한 모드 5개를 문서 순서대로", () => {
    expect(PERMISSION_MODES.map((m) => m.value)).toEqual(["default", "acceptEdits", "plan", "auto", "bypassPermissions"]);
    expect(PERMISSION_MODES.map((m) => m.title)).toEqual(["매번 묻기", "수정은 바로", "계획만", "자동", "묻지 않음"]);
  });
  it("묻지 않음만 경고 표시", () => {
    expect(PERMISSION_MODES.filter((m) => m.warn).map((m) => m.value)).toEqual(["bypassPermissions"]);
  });
});
