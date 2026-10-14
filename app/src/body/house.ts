// 강아지 집 픽셀 그림 (16×14). 한 글자 = 한 픽셀, "."은 투명
const PIXELS = [
  "......RRRR......",
  ".....RRRRRR.....",
  "....RRRRRRRR....",
  "...RRRRRRRRRR...",
  "..RRRRRRRRRRRR..",
  ".RRRRRRRRRRRRRR.",
  "RRRRRRRRRRRRRRRR",
  ".WWWWWWWWWWWWWW.",
  ".WWWWWDDDDWWWWW.",
  ".WWWWDDDDDDWWWW.",
  ".WWWWDDDDDDWWWW.",
  ".WWWWDDDDDDWWWW.",
  ".WWWWDDDDDDWWWW.",
  ".BBBBBBBBBBBBBB.",
];
const COLORS: Record<string, string> = { R: "#b5452f", W: "#e8c48a", D: "#3b2a20", B: "#7a5230" };

export const HOUSE_PX = { width: 16, height: 14 };

export function drawHouse(ctx: CanvasRenderingContext2D, x: number, y: number, scale: number) {
  PIXELS.forEach((row, r) =>
    [...row].forEach((ch, c) => {
      if (ch === ".") return;
      ctx.fillStyle = COLORS[ch];
      ctx.fillRect(x + c * scale, y + r * scale, scale, scale);
    }),
  );
}
