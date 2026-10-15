import { test, expect } from "vitest";
import { withDefaults, DEFAULT_SETTINGS } from "../src/shared/settings";

test("저장된 값이 없으면 기본값", () => expect(withDefaults(null)).toEqual(DEFAULT_SETTINGS));
test("저장된 값이 일부면 나머지는 기본값", () =>
  expect(withDefaults({ hideHouseWhenInside: true })).toEqual({ ...DEFAULT_SETTINGS, hideHouseWhenInside: true }));

import { shortcutFallback } from "../src/shared/settings";

test("등록 실패 시 이전 단축키로 되돌리고 나머지 설정은 유지한다", () => {
  const prev = { ...DEFAULT_SETTINGS, inputShortcut: "Ctrl+Alt+K" };
  const attempted = { ...DEFAULT_SETTINGS, inputShortcut: "Alt+Tab", hideHouseWhenInside: true };
  expect(shortcutFallback(attempted, prev)).toEqual({ ...attempted, inputShortcut: "Ctrl+Alt+K", houseShortcut: prev.houseShortcut });
});

test("이전 단축키가 없으면(앱 시작 시) 기본 단축키로 되돌린다", () => {
  const attempted = { ...DEFAULT_SETTINGS, houseShortcut: "Alt+Tab" };
  expect(shortcutFallback(attempted, null)).toEqual({ ...attempted, houseShortcut: DEFAULT_SETTINGS.houseShortcut });
});

test("예전 움직임 정도 설정은 쉬기 켜기/끄기로 옮긴다", () => {
  expect(withDefaults({ activity: "rest" } as never).rest).toBe(true);
  expect(withDefaults({ activity: "lively" } as never).rest).toBe(false);
  expect("activity" in withDefaults({ activity: "calm" } as never)).toBe(false);
});

test("입력창 항상 표시 설정은 없어졌다 (입력창은 직접 닫기 전까지 열려 있다)", () => {
  expect("inputAlwaysVisible" in withDefaults({ inputAlwaysVisible: true } as never)).toBe(false);
});
