import { test, expect } from "vitest";
import { newPetting, feedPetting, type Petting } from "../src/body/petting";

// 커서 x 좌표를 시간 순서대로 넣는다 (강아지 위에 있을 때)
function run(xs: [number, number][], over = true) {
  let s: Petting = newPetting();
  let petted = 0;
  for (const [x, t] of xs) { const r = feedPetting(s, x, t, over); s = r.state; if (r.petted) petted++; }
  return petted;
}

test("좌우로 여러 번 문지르면 쓰다듬기", () =>
  expect(run([[100, 0], [120, 100], [100, 200], [120, 300], [100, 400]])).toBe(1));
test("한 방향으로만 지나가면 쓰다듬기가 아니다", () =>
  expect(run([[100, 0], [120, 100], [140, 200], [160, 300], [180, 400]])).toBe(0));
test("아주 작은 떨림은 세지 않는다", () =>
  expect(run([[100, 0], [102, 100], [100, 200], [102, 300], [100, 400]])).toBe(0));
test("천천히 문지르면(시간 창 밖) 쓰다듬기가 아니다", () =>
  expect(run([[100, 0], [120, 1000], [100, 2000], [120, 3000], [100, 4000]])).toBe(0));
test("강아지 밖이면 세지 않는다", () =>
  expect(run([[100, 0], [120, 100], [100, 200], [120, 300], [100, 400]], false)).toBe(0));
test("한 번 쓰다듬은 뒤 잠깐은 다시 세지 않는다", () =>
  expect(run([[100, 0], [120, 100], [100, 200], [120, 300], [100, 400], [120, 500], [100, 600], [120, 700]])).toBe(1));

test("쓰다듬은 시간(초)을 함께 알려 준다", () => {
  let s: Petting = newPetting();
  let seconds = 0;
  for (const [x, t] of [[100, 0], [120, 100], [100, 200], [120, 300], [100, 400]] as [number, number][]) {
    const r = feedPetting(s, x, t, true);
    s = r.state;
    if (r.petted) seconds = r.seconds;
  }
  expect(seconds).toBeCloseTo(0.2, 5);
});
