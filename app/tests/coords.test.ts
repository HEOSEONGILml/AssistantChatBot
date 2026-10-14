import { describe, test, expect } from "vitest";
import { physToCss, cssBoxToPhys, boxContains } from "../src/body/coords";

describe("physToCss", () => {
  test("배율 1, 원점 0", () => expect(physToCss({ x: 100, y: 50 }, { x: 0, y: 0 }, 1)).toEqual({ x: 100, y: 50 }));
  test("배율 1.25", () => expect(physToCss({ x: 125, y: 250 }, { x: 0, y: 0 }, 1.25)).toEqual({ x: 100, y: 200 }));
  test("배율 1.5, 창 원점이 (0,0)이 아님", () =>
    expect(physToCss({ x: 1650, y: 300 }, { x: 1500, y: 0 }, 1.5)).toEqual({ x: 100, y: 200 }));
});

describe("cssBoxToPhys", () => {
  test("배율 1.5로 키우고 원점을 더한다", () =>
    expect(cssBoxToPhys({ left: 10, top: 20, width: 40, height: 30 }, { x: 100, y: 0 }, 1.5))
      .toEqual({ left: 115, top: 30, right: 175, bottom: 75 }));
});

describe("boxContains", () => {
  const b = { left: 10, top: 10, width: 10, height: 10 };
  test("안쪽과 왼쪽 위 경계", () => { expect(boxContains(b, { x: 10, y: 10 })).toBe(true); expect(boxContains(b, { x: 19.9, y: 19.9 })).toBe(true); });
  test("오른쪽 아래 경계는 밖", () => expect(boxContains(b, { x: 20, y: 15 })).toBe(false));
});

import { placeAbove } from "../src/body/coords";

describe("placeAbove", () => {
  test("기준 영역 오른쪽 끝에 맞추고 위로 gap만큼 띄운다", () =>
    expect(placeAbove({ left: 1800, top: 1000, right: 1872, bottom: 1042 }, { width: 380, height: 56 }, 8))
      .toEqual({ x: 1492, y: 936 }));
  test("화면 왼쪽·위쪽 밖으로 나가지 않는다", () =>
    expect(placeAbove({ left: 10, top: 20, right: 100, bottom: 60 }, { width: 380, height: 56 }, 8))
      .toEqual({ x: 0, y: 0 }));
});
