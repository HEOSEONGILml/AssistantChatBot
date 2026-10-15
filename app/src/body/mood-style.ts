// 기분과 반응을 그림 변형으로 보여 주는 임시 표현 (기분 8개 스펙 6절).
// 평소 모습은 두드러진 기분(movement.mood)으로, 반응은 머리 위 아이콘과 짧은 톡 튐으로 보인다.
// 나중에 기분별 그림이 생기면 그 그림으로 바꾼다.
export type MoodId = "calm" | "bored" | "sleepy" | "excited" | "sad" | "annoyed" | "curious" | "surprised" | "scared" | "happy";
export type ReactionId = Exclude<MoodId, "calm">;
export const MOOD_IDS: readonly MoodId[] = ["calm", "bored", "sleepy", "excited", "sad", "annoyed", "curious", "surprised", "scared", "happy"];

// speed: 애니메이션 속도 배율, offsetY: 아래로 처지는 px, tint: 덧칠 색, jitter: 떨림 px, tilt: 기울기(라디안), bounce: 걸을 때 튀는 px
export type MoodStyle = { speed: number; offsetY: number; tint: string | null; jitter: number; tilt: number; bounce: number };

const CALM: MoodStyle = { speed: 1, offsetY: 0, tint: null, jitter: 0, tilt: 0, bounce: 0 };
const STYLES: Record<MoodId, MoodStyle> = {
  calm: CALM,
  excited: { ...CALM, speed: 1.5, bounce: 3 },
  sad: { ...CALM, speed: 0.7, offsetY: 2, tint: "rgba(40,40,80,0.25)" },
  annoyed: { ...CALM, tint: "rgba(220,40,40,0.25)", jitter: 0.6 },
  sleepy: { ...CALM, speed: 0.6, tint: "rgba(40,40,60,0.2)" },
  bored: { ...CALM, speed: 0.8 },
  curious: { ...CALM, tilt: 0.08 },
  surprised: { ...CALM, speed: 1.2 },
  scared: { ...CALM, offsetY: 1, jitter: 1.2, tint: "rgba(60,90,200,0.2)" },
  happy: { ...CALM, speed: 1.15, bounce: 1.5, tint: "rgba(255,170,120,0.15)" },
};

export const moodStyle = (m: MoodId): MoodStyle => STYLES[m] ?? CALM;

export const REACTION_MS = 1500; // 반응 아이콘을 보여 주는 시간 (잠정값)
export const EMOTES: Record<ReactionId, string> = {
  excited: "🎵", annoyed: "💢", curious: "❓", surprised: "❗", sad: "💧", sleepy: "💤", bored: "💭", scared: "😨", happy: "💕",
};

// 반응이 오는 순간 몸이 한 번 톡 튄다. 놀람·신남은 크게
const HOP_PX: Record<ReactionId, number> = { surprised: 14, excited: 12, scared: 8, annoyed: 6, happy: 6, curious: 5, sad: 2, sleepy: 2, bored: 2 };
const HOP_MS = 300;

export function reactionHop(r: ReactionId, elapsedMs: number): number {
  if (elapsedMs <= 0 || elapsedMs >= HOP_MS) return 0;
  return HOP_PX[r] * Math.sin((Math.PI * elapsedMs) / HOP_MS);
}
