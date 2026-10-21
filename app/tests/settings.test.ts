import { test, expect } from "vitest";
import { withDefaults, DEFAULT_SETTINGS } from "../src/shared/settings";

test("저장된 값이 없으면 기본값", () => expect(withDefaults(null)).toEqual(DEFAULT_SETTINGS));
test("저장된 단축키를 쓴다", () => expect(withDefaults({ inputShortcut: "Ctrl+Alt+K" })).toEqual({ inputShortcut: "Ctrl+Alt+K" }));
test("예전 설정 값은 버린다", () =>
  expect(withDefaults({ rest: true, houseShortcut: "Ctrl+H" } as never)).toEqual(DEFAULT_SETTINGS));
