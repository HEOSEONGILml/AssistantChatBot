import { test, expect } from "vitest";
import { withDefaults, DEFAULT_SETTINGS } from "../src/shared/settings";

test("저장된 값이 없으면 기본값", () => expect(withDefaults(null)).toEqual(DEFAULT_SETTINGS));
test("저장된 값이 일부면 나머지는 기본값", () =>
  expect(withDefaults({ inputAlwaysVisible: true })).toEqual({ ...DEFAULT_SETTINGS, inputAlwaysVisible: true }));
