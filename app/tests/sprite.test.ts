import { test, expect } from "vitest";
import { frameAt, type Manifest } from "../src/body/sprite";

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
