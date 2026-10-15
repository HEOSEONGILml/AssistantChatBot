// 화면이 이벤트를 낼 시점을 정하는 순수 로직 (두뇌 스펙 v2 3절, 프로토콜 v2). 값은 잠정값이다.
export const TYPING_PAUSE_MS = 600;           // 연속 타이핑 키 간격은 대개 0.5초 안쪽 (v1 두뇌 값을 화면으로 옮김)
export const TYPING_CHARS = 10;               // 한국어 두세 어절
export const QUIET_PRESENT_MS = 10 * 60_000;  // 먼저 말 걸기 목표 30분 ÷ 말할 확률 약 1/3
export const QUIET_AWAY_MS = 30 * 60_000;     // 자리를 비우면 덜 자주
export const IMPACT_REF = 2000;               // 이 속도(px/초)로 부딪히면 충격 1

export type Typing = { text: string; changedAt: number; sentText: string; pending: boolean };

export const newTyping = (): Typing => ({ text: "", changedAt: 0, sentText: "", pending: false });

// 글이 바뀔 때: 지난번 낸 글보다 많이 바뀌었으면 바로 낸다
export function feedTyping(s: Typing, text: string, now: number): { state: Typing; fire: boolean } {
  const next = { ...s, text, changedAt: now, pending: true };
  if (text.trim() && Math.abs(text.length - s.sentText.length) >= TYPING_CHARS) {
    return { state: { ...next, sentText: text, pending: false }, fire: true };
  }
  return { state: next, fire: false };
}

// 주기적으로: 타이핑이 멈춘 지 충분히 지났으면 낸다. 다 지웠으면 내지 않는다
export function tickTyping(s: Typing, now: number): { state: Typing; fire: boolean } {
  if (!s.pending) return { state: s, fire: false };
  if (!s.text.trim()) return { state: { ...s, pending: false }, fire: false };
  if (now - s.changedAt >= TYPING_PAUSE_MS) return { state: { ...s, sentText: s.text, pending: false }, fire: true };
  return { state: s, fire: false };
}

export function quietDue(lastEventAt: number, now: number, userActive: boolean): boolean {
  return now - lastEventAt >= (userActive ? QUIET_PRESENT_MS : QUIET_AWAY_MS);
}

// 프로토콜은 0~1로 정규화한 충격을 받는다 (정규화는 화면이 정한다)
export function impactOf(maxSpeed: number): number {
  return Math.round(Math.min(1, Math.max(0, maxSpeed) / IMPACT_REF) * 100) / 100;
}
