// 강아지·패널 자리 계산(순수, 논리 px). 규칙은 docs/design/2026-10-21-output-ui/digest.md 2절과 설계 변경 계획의 "정한 값"(패널 자리·꼬리·끌기).
export type Point = { x: number; y: number };
export type Size = { width: number; height: number };
export type Rect = Point & Size;

export const DOG: Size = { width: 96, height: 72 }; // 프레임 64x48의 1.5배
const RIGHT_GAP = 20; // 처음 자리: 강아지 오른쪽 끝 = 작업 영역 오른쪽 − 20px
const PANEL_GAP = 12; // 패널과 강아지 사이
const TAIL_HALF = 7; // 꼬리(14x14)의 반
const DRAG_MIN = 4; // 이만큼 넘게 움직여야 끌기

export type Layout = {
  window: Rect; // 화면 좌표
  dog: Point; // 창 안
  panel: Point | null; // 창 안. 패널이 닫혔으면 null
  tail: number | null; // 패널 안 꼬리 왼쪽 끝. 위 모양일 때만
};

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(v, hi));

export function contains(r: Rect, p: Point): boolean {
  return p.x >= r.x && p.y >= r.y && p.x < r.x + r.width && p.y < r.y + r.height;
}

export function initialDog(work: Rect): Point {
  return { x: work.x + work.width - RIGHT_GAP - DOG.width, y: work.y + work.height - DOG.height };
}

export function clampDog(work: Rect, dog: Point): Point {
  return {
    x: clamp(dog.x, work.x, work.x + work.width - DOG.width),
    y: clamp(dog.y, work.y, work.y + work.height - DOG.height),
  };
}

export function isDrag(dx: number, dy: number): boolean {
  return Math.hypot(dx, dy) > DRAG_MIN;
}

// 패널은 강아지 위에 들어가면 위(오른쪽 끝을 강아지에 맞춤, 꼬리 있음),
// 아니면 옆(오른쪽 먼저, 위쪽 끝을 강아지에 맞춤, 꼬리 없음). 어느 쪽이든 작업 영역 안으로 당긴다
export function layout(work: Rect, dog: Point, panel: Size | null): Layout {
  if (!panel) return { window: { ...dog, ...DOG }, dog: { x: 0, y: 0 }, panel: null, tail: null };
  const above = dog.y - work.y >= panel.height + PANEL_GAP;
  let p: Point;
  if (above) {
    p = { x: dog.x + DOG.width - panel.width, y: dog.y - PANEL_GAP - panel.height };
  } else {
    const right = dog.x + DOG.width + PANEL_GAP;
    const x = right + panel.width <= work.x + work.width ? right : dog.x - PANEL_GAP - panel.width;
    p = { x, y: dog.y };
  }
  p = { x: clamp(p.x, work.x, work.x + work.width - panel.width), y: clamp(p.y, work.y, work.y + work.height - panel.height) };
  const x = Math.min(p.x, dog.x);
  const y = Math.min(p.y, dog.y);
  const window = {
    x, y,
    width: Math.max(p.x + panel.width, dog.x + DOG.width) - x,
    height: Math.max(p.y + panel.height, dog.y + DOG.height) - y,
  };
  return {
    window,
    dog: { x: dog.x - x, y: dog.y - y },
    panel: { x: p.x - x, y: p.y - y },
    tail: above ? dog.x + DOG.width / 2 - p.x - TAIL_HALF : null,
  };
}
