import { describe, expect, it } from "vitest";
import { clampDog, contains, DOG, initialDog, isDrag, layout, type Rect } from "../src/shared/placement";

const WORK: Rect = { x: 0, y: 0, width: 1920, height: 1032 }; // 1920x1080, 작업 표시줄 48
const LEFT_MONITOR: Rect = { x: -1920, y: -200, width: 1920, height: 1040 }; // 원점이 음수인 모니터
const PANEL = { width: 340, height: 300 };

const inside = (outer: Rect, r: Rect) =>
  r.x >= outer.x && r.y >= outer.y && r.x + r.width <= outer.x + outer.width && r.y + r.height <= outer.y + outer.height;

describe("initialDog", () => {
  it("처음 자리는 작업 영역 오른쪽 아래, 오른쪽 20px 띄움", () => {
    expect(initialDog(WORK)).toEqual({ x: 1920 - 20 - 96, y: 1032 - 72 });
    expect(initialDog(LEFT_MONITOR)).toEqual({ x: -20 - 96, y: 840 - 72 });
  });
});

describe("layout", () => {
  it("패널이 닫히면 창은 강아지 크기 그대로, 강아지는 창 왼쪽 위", () => {
    expect(layout(WORK, { x: 500, y: 400 }, null)).toEqual({
      window: { x: 500, y: 400, width: 96, height: 72 }, dog: { x: 0, y: 0 }, panel: null, tail: null,
    });
  });

  it("위에 들어가면 위: 오른쪽 끝을 강아지에 맞추고 12px 띄움, 꼬리는 강아지 가운데", () => {
    const dog = initialDog(WORK); // (1804, 960)
    expect(layout(WORK, dog, PANEL)).toEqual({
      window: { x: 1560, y: 648, width: 340, height: 384 },
      dog: { x: 244, y: 312 },
      panel: { x: 0, y: 0 },
      tail: 1852 - 1560 - 7,
    });
  });

  it("위 모양에서 왼쪽으로 넘치면 작업 영역 안으로 당기고 꼬리는 강아지를 따라간다", () => {
    const l = layout(WORK, { x: 0, y: 960 }, PANEL);
    expect(l.window).toEqual({ x: 0, y: 648, width: 340, height: 384 });
    expect(l.dog).toEqual({ x: 0, y: 312 });
    expect(l.tail).toBe(48 - 7);
  });

  it("위가 딱 패널 높이 + 12면 위", () => {
    expect(layout(WORK, { x: 800, y: 312 }, PANEL).tail).not.toBeNull();
    expect(layout(WORK, { x: 800, y: 311 }, PANEL).tail).toBeNull();
  });

  it("위에 안 들어가면 오른쪽 옆: 12px 간격, 위쪽 끝을 강아지에 맞춤, 꼬리 없음 (21번)", () => {
    const work = { x: 0, y: 0, width: 880, height: 592 }; // 21번 아트보드 880x640 − 작업 표시줄 48
    const l = layout(work, { x: 44, y: 96 }, PANEL);
    expect(l.window).toEqual({ x: 44, y: 96, width: 96 + 12 + 340, height: 300 });
    expect(l.dog).toEqual({ x: 0, y: 0 });
    expect(l.panel).toEqual({ x: 108, y: 0 });
    expect(l.tail).toBeNull();
  });

  it("오른쪽에 안 들어가면 왼쪽 옆", () => {
    const l = layout(WORK, { x: 1824, y: 0 }, PANEL);
    expect(l.window).toEqual({ x: 1824 - 12 - 340, y: 0, width: 340 + 12 + 96, height: 300 });
    expect(l.panel).toEqual({ x: 0, y: 0 });
    expect(l.dog).toEqual({ x: 352, y: 0 });
    expect(l.tail).toBeNull();
  });

  it("옆 모양에서 아래로 넘치면 작업 영역 안으로 끌어올린다", () => {
    const l = layout(WORK, { x: 0, y: 400 }, { width: 340, height: 700 });
    expect(l.window).toEqual({ x: 0, y: 332, width: 448, height: 700 });
    expect(l.dog).toEqual({ x: 0, y: 68 });
    expect(l.panel).toEqual({ x: 108, y: 0 });
  });

  // Review Focus 5: 어느 구석에서도 패널과 강아지가 작업 영역 안
  for (const [name, work] of [["주 모니터", WORK], ["원점이 음수인 모니터", LEFT_MONITOR]] as const) {
    for (const height of [120, 300, 460]) {
      it(`${name}, 패널 높이 ${height}: 네 구석과 가운데에서 모두 작업 영역 안`, () => {
        const corners = [
          { x: work.x, y: work.y },
          { x: work.x + work.width - DOG.width, y: work.y },
          { x: work.x, y: work.y + work.height - DOG.height },
          { x: work.x + work.width - DOG.width, y: work.y + work.height - DOG.height },
          { x: work.x + 900, y: work.y + 500 },
        ];
        for (const d of corners) {
          const l = layout(work, d, { width: 340, height });
          const w = l.window;
          const panel = { x: w.x + l.panel!.x, y: w.y + l.panel!.y, width: 340, height };
          const dog = { x: w.x + l.dog.x, y: w.y + l.dog.y, width: DOG.width, height: DOG.height };
          expect(dog).toMatchObject(d); // 강아지는 움직이지 않는다
          expect(inside(work, panel)).toBe(true);
          expect(inside(work, dog)).toBe(true);
          expect(inside(w, panel) && inside(w, dog)).toBe(true);
          // 패널과 강아지가 겹치지 않는다
          const overlap = panel.x < dog.x + dog.width && dog.x < panel.x + panel.width
            && panel.y < dog.y + dog.height && dog.y < panel.y + panel.height;
          expect(overlap).toBe(false);
        }
      });
    }
  }
});

describe("clampDog", () => {
  it("작업 영역 밖으로 나간 강아지를 안으로 당긴다", () => {
    expect(clampDog(WORK, { x: -30, y: -5 })).toEqual({ x: 0, y: 0 });
    expect(clampDog(WORK, { x: 1900, y: 1020 })).toEqual({ x: 1824, y: 960 });
    expect(clampDog(WORK, { x: 700, y: 300 })).toEqual({ x: 700, y: 300 });
  });
  it("원점이 음수인 모니터", () => {
    expect(clampDog(LEFT_MONITOR, { x: -2000, y: -300 })).toEqual({ x: -1920, y: -200 });
    expect(clampDog(LEFT_MONITOR, { x: 10, y: 900 })).toEqual({ x: -96, y: 840 - 72 });
  });
});

// Review Focus 6: 조금 흔들린 클릭은 누르기
describe("isDrag", () => {
  it("4px까지는 누르기", () => {
    expect(isDrag(0, 0)).toBe(false);
    expect(isDrag(4, 0)).toBe(false);
    expect(isDrag(0, -4)).toBe(false);
    expect(isDrag(2, 3)).toBe(false);
  });
  it("4px을 넘으면 끌기", () => {
    expect(isDrag(5, 0)).toBe(true);
    expect(isDrag(-4, 1)).toBe(true);
    expect(isDrag(3, 3)).toBe(true);
  });
});

describe("contains", () => {
  it("왼쪽·위 끝은 안, 오른쪽·아래 끝은 밖", () => {
    expect(contains(LEFT_MONITOR, { x: -1920, y: -200 })).toBe(true);
    expect(contains(LEFT_MONITOR, { x: 0, y: 0 })).toBe(false);
    expect(contains(LEFT_MONITOR, { x: -1, y: 839 })).toBe(true);
    expect(contains(LEFT_MONITOR, { x: -1, y: 840 })).toBe(false);
  });
});
