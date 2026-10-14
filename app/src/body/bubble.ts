// 잠정값: 한 문장을 읽는 데 2~3초. 평가 단계(서브 프로젝트 3)에서 다시 정한다.
export const SEEN_MS = 3000;
// 잠정값: 뒤늦게 볼 수 있도록 길게(vision "한참 더 남는다"). 10분.
export const KEEP_AFTER_SEEN_MS = 10 * 60 * 1000;

export type Bubble = { text: string; visibleMs: number; seenAt: number | null } | null;

export function showBubble(text: string): Bubble {
  return { text, visibleMs: 0, seenAt: null };
}

export function tickBubble(b: Bubble, now: number, dtMs: number, unobstructed: boolean): { bubble: Bubble; justSeen: boolean } {
  if (!b) return { bubble: null, justSeen: false };
  if (b.seenAt !== null) {
    return { bubble: now - b.seenAt >= KEEP_AFTER_SEEN_MS ? null : b, justSeen: false };
  }
  const visibleMs = unobstructed ? b.visibleMs + dtMs : b.visibleMs;
  if (visibleMs >= SEEN_MS) return { bubble: { ...b, visibleMs, seenAt: now }, justSeen: true };
  return { bubble: { ...b, visibleMs }, justSeen: false };
}
