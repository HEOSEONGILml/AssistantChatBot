export type Animation = { row: number; col?: number; frames: number; fps: number; loop: boolean };
export type Manifest = {
  image: string; frameWidth: number; frameHeight: number; scale: number; facing?: "left" | "right";
  animations: Record<string, Animation>;
  moods?: Record<string, string>; // 기분 id → 그 기분 얼굴을 덧그린 시트 (기분별 그림 스펙)
};

export const DOG_ACTIONS = ["walk", "run", "idle_stand", "idle_sit", "idle_lay", "sleep", "beg", "bark"] as const;
export type DogAction = (typeof DOG_ACTIONS)[number];

// 기분별 시트가 있으면 그 시트, 없으면 원본 시트
export const sheetImage = (m: Manifest, mood: string): string => m.moods?.[mood] ?? m.image;

export function frameAt(m: Manifest, anim: string, elapsedMs: number) {
  const a = m.animations[anim] ?? m.animations["walk"];
  const raw = Math.floor((elapsedMs / 1000) * a.fps);
  const i = a.loop ? raw % a.frames : Math.min(raw, a.frames - 1);
  return { sx: ((a.col ?? 0) + i) * m.frameWidth, sy: a.row * m.frameHeight, sw: m.frameWidth, sh: m.frameHeight };
}

// 프레임 안에서 처음으로 그림(불투명 픽셀)이 나오는 줄. 시트의 칸 위쪽 빈 공간을 건너뛰어
// 말풍선을 강아지 머리 바로 위에 붙이는 데 쓴다. 빈 칸이면 칸 높이를 돌려준다.
export function opaqueTop(alpha: Uint8ClampedArray, sheetWidth: number, f: { sx: number; sy: number; sw: number; sh: number }): number {
  for (let y = 0; y < f.sh; y++) {
    for (let x = 0; x < f.sw; x++) {
      if (alpha[((f.sy + y) * sheetWidth + f.sx + x) * 4 + 3] > 0) return y;
    }
  }
  return f.sh;
}
