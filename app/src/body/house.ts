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

// 말풍선 아이콘 (14×12). 누르면 입력창을 열고 닫는다.
const CHAT_PIXELS = [
  "..KKKKKKKKKK..",
  ".KWWWWWWWWWWK.",
  "KWWWWWWWWWWWWK",
  "KWWKKWWKKWWKWK",
  "KWWKKWWKKWWKWK",
  "KWWWWWWWWWWWWK",
  "KWWWWWWWWWWWWK",
  ".KWWWWWWWWWWK.",
  "..KKKWWKKKKK..",
  "....KWK.......",
  "....KK........",
  "....K.........",
];
const CHAT_COLORS: Record<string, string> = { K: "#222222", W: "#fffdf5" };

export const CHAT_PX = { width: 14, height: 12 };

export function drawChatIcon(ctx: CanvasRenderingContext2D, x: number, y: number, scale: number, active: boolean) {
  CHAT_PIXELS.forEach((row, r) =>
    [...row].forEach((ch, c) => {
      if (ch === ".") return;
      ctx.fillStyle = ch === "W" && active ? "#ffe08a" : CHAT_COLORS[ch];
      ctx.fillRect(x + c * scale, y + r * scale, scale, scale);
    }),
  );
}
