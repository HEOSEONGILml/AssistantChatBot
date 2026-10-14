export type Point = { x: number; y: number };
export type Box = { left: number; top: number; width: number; height: number };

export function physToCss(p: Point, windowOrigin: Point, scale: number): Point {
  return { x: (p.x - windowOrigin.x) / scale, y: (p.y - windowOrigin.y) / scale };
}

export function cssBoxToPhys(b: Box, windowOrigin: Point, scale: number) {
  return {
    left: Math.round(windowOrigin.x + b.left * scale),
    top: Math.round(windowOrigin.y + b.top * scale),
    right: Math.round(windowOrigin.x + (b.left + b.width) * scale),
    bottom: Math.round(windowOrigin.y + (b.top + b.height) * scale),
  };
}

export function boxContains(b: Box, p: Point): boolean {
  return p.x >= b.left && p.x < b.left + b.width && p.y >= b.top && p.y < b.top + b.height;
}

// 기준 영역(물리 좌표) 위에 창을 놓을 위치. 오른쪽 끝을 맞추고 화면 밖으로 나가지 않게 한다.
export function placeAbove(
  anchor: { left: number; top: number; right: number; bottom: number },
  size: { width: number; height: number },
  gap: number,
): Point {
  return { x: Math.max(0, anchor.right - size.width), y: Math.max(0, anchor.top - size.height - gap) };
}
