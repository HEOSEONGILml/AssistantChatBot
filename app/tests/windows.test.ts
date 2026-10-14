import { test, expect } from "vitest";
import { exposeTopEdges } from "../src/body/windows";
import type { Win } from "../src/body/dog";

const win = (id: number, left: number, top: number, width: number, height: number): Win =>
  ({ id, left, top, width, height, active: false });

test("위에 아무 창도 없으면 윗변 전체가 보인다", () => {
  const [a] = exposeTopEdges([win(1, 100, 200, 400, 300)]);
  expect(a.span).toEqual({ left: 100, right: 500 });
});

test("위 창에 완전히 가려진 윗변은 보이지 않는다", () => {
  const [, b] = exposeTopEdges([win(1, 0, 0, 1000, 800), win(2, 100, 200, 400, 300)]);
  expect(b.span).toBeNull();
});

test("일부만 가려지면 가장 넓게 보이는 구간을 고른다", () => {
  // 위 창이 윗변의 왼쪽 100~250을 가린다 → 보이는 구간 250~500
  const [, b] = exposeTopEdges([win(1, 50, 150, 200, 200), win(2, 100, 200, 400, 300)]);
  expect(b.span).toEqual({ left: 250, right: 500 });
});

test("위 창이 윗변 높이에 걸치지 않으면 가리지 않는다", () => {
  const [, b] = exposeTopEdges([win(1, 0, 300, 1000, 200), win(2, 100, 200, 400, 300)]);
  expect(b.span).toEqual({ left: 100, right: 500 });
});
