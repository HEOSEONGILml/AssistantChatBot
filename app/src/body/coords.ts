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
