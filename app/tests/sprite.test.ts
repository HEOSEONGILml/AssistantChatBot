import { describe, test, expect } from "vitest";
import { frameAt, sheetImage, type Manifest } from "../src/body/sprite";

const m: Manifest = {
  image: "sheet.png", frameWidth: 64, frameHeight: 48, scale: 2,
  animations: {
    walk: { row: 1, frames: 4, fps: 10, loop: true },
    bark: { row: 3, frames: 3, fps: 10, loop: false },
    yap: { row: 0, col: 6, frames: 2, fps: 10, loop: true },
  },
};

test("첫 프레임", () => expect(frameAt(m, "walk", 0)).toEqual({ sx: 0, sy: 48, sw: 64, sh: 48 }));
test("fps에 따라 넘어간다", () => expect(frameAt(m, "walk", 250).sx).toBe(128)); // 2.5프레임 → 2
test("loop면 처음으로 돌아간다", () => expect(frameAt(m, "walk", 450).sx).toBe(0)); // 4.5 → 4 % 4 = 0
test("loop가 아니면 마지막 프레임에 멈춘다", () => expect(frameAt(m, "bark", 1000).sx).toBe(128));
test("없는 동작은 walk로 대체", () => expect(frameAt(m, "dance", 0).sy).toBe(48));
test("시작 칸(col)부터 센다", () => {
  expect(frameAt(m, "yap", 0).sx).toBe(6 * 64);
  expect(frameAt(m, "yap", 150).sx).toBe(7 * 64);
  expect(frameAt(m, "yap", 250).sx).toBe(6 * 64);
});

import { opaqueTop } from "../src/body/sprite";

// 4×4 시트 RGBA. 프레임은 2×2 네 칸. 알파만 의미 있다
function sheetAlpha(opaque: [number, number][]) {
  const a = new Uint8ClampedArray(4 * 4 * 4);
  for (const [x, y] of opaque) a[(y * 4 + x) * 4 + 3] = 255;
  return a;
}

test("프레임 안에서 처음으로 그림이 있는 줄을 찾는다", () => {
  const a = sheetAlpha([[3, 1], [2, 3]]); // 오른쪽 위 칸의 둘째 줄, 오른쪽 아래 칸의 둘째 줄
  expect(opaqueTop(a, 4, { sx: 2, sy: 0, sw: 2, sh: 2 })).toBe(1);
  expect(opaqueTop(a, 4, { sx: 2, sy: 2, sw: 2, sh: 2 })).toBe(1);
});
test("다른 칸의 픽셀은 보지 않는다", () => {
  const a = sheetAlpha([[0, 1]]); // 왼쪽 위 칸에만 그림
  expect(opaqueTop(a, 4, { sx: 2, sy: 0, sw: 2, sh: 2 })).toBe(2); // 빈 칸이면 높이(sh)
});

describe("기분별 시트", () => {
  const m = { image: "/base.png", frameWidth: 64, frameHeight: 48, scale: 1.5, animations: {}, moods: { happy: "/happy.png" } };
  test("기분 시트가 있으면 그 시트, 없으면 원본", () => {
    expect(sheetImage(m, "happy")).toBe("/happy.png");
    expect(sheetImage(m, "sad")).toBe("/base.png");
    expect(sheetImage(m, "calm")).toBe("/base.png");
    expect(sheetImage({ ...m, moods: undefined }, "happy")).toBe("/base.png");
  });
});
