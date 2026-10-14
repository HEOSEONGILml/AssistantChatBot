export type Animation = { row: number; col?: number; frames: number; fps: number; loop: boolean };
export type Manifest = {
  image: string; frameWidth: number; frameHeight: number; scale: number; facing?: "left" | "right";
  animations: Record<string, Animation>;
};

export const DOG_ACTIONS = ["walk", "run", "idle_stand", "idle_sit", "idle_lay", "sleep", "beg", "bark"] as const;
export type DogAction = (typeof DOG_ACTIONS)[number];

export function frameAt(m: Manifest, anim: string, elapsedMs: number) {
  const a = m.animations[anim] ?? m.animations["walk"];
  const raw = Math.floor((elapsedMs / 1000) * a.fps);
  const i = a.loop ? raw % a.frames : Math.min(raw, a.frames - 1);
  return { sx: ((a.col ?? 0) + i) * m.frameWidth, sy: a.row * m.frameHeight, sw: m.frameWidth, sh: m.frameHeight };
}
