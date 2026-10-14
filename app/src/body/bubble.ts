// 잠정값: 한 문장을 읽는 데 2~3초. 평가 단계(서브 프로젝트 3)에서 다시 정한다.
export const SEEN_MS = 3000;
// 잠정값: "봤다" 판정 후 최소 5초, 글자당 0.15초 더 남긴다 (2026-10-14 사용자 요청: 보고 있으면 사라져야 함).
const KEEP_MIN_MS = 5000;
const KEEP_PER_CHAR_MS = 150;

export type Bubble = { text: string; visibleMs: number; seenAt: number | null } | null;

export function keepAfterSeenMs(text: string): number {
  return Math.max(KEEP_MIN_MS, [...text].length * KEEP_PER_CHAR_MS);
}

export function showBubble(text: string): Bubble {
  return { text, visibleMs: 0, seenAt: null };
}

// userActive: 사용자가 PC를 쓰고 있는지(최근 입력이 있는지). 자리를 비운 동안은 "봤다" 시간을 세지 않는다.
export function tickBubble(b: Bubble, now: number, dtMs: number, userActive: boolean): { bubble: Bubble; justSeen: boolean } {
  if (!b) return { bubble: null, justSeen: false };
  if (b.seenAt !== null) {
    return { bubble: now - b.seenAt >= keepAfterSeenMs(b.text) ? null : b, justSeen: false };
  }
  const visibleMs = userActive ? b.visibleMs + dtMs : b.visibleMs;
  if (visibleMs >= SEEN_MS) return { bubble: { ...b, visibleMs, seenAt: now }, justSeen: true };
  return { bubble: { ...b, visibleMs }, justSeen: false };
}
