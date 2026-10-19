// 웹에서 "사용자가 입력 없이 지낸 시간". PC 앱은 OS 입력을 보지만 웹은 이 페이지 안 입력과 탭 숨김만 안다.
// 탭이 숨겨지면 바로 자리를 비운 것으로 본다 (웹 프로토타입 스펙 3절)
export const AWAY_MS = 60_000; // PC 앱의 USER_ACTIVE_IDLE_MS와 같다

export type Presence = { lastInput: number; hiddenSince: number | null };

export const newPresence = (now: number): Presence => ({ lastInput: now, hiddenSince: null });
export const noteInput = (p: Presence, now: number): Presence => ({ ...p, lastInput: now });
export const setHidden = (p: Presence, hidden: boolean, now: number): Presence =>
  ({ ...p, hiddenSince: hidden ? (p.hiddenSince ?? now) : null });

export function idleMs(p: Presence, now: number): number {
  const sinceInput = now - p.lastInput;
  return p.hiddenSince === null ? sinceInput : Math.max(sinceInput, AWAY_MS + (now - p.hiddenSince));
}
