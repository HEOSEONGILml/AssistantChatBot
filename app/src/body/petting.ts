// 쓰다듬기 판정: 강아지 위에서 커서를 좌우로 여러 번 문지르면 쓰다듬기다 (mochi-llm-pet 참고).
// 잠정값들은 사용자 체감으로 조정한다.
const MIN_STROKE_PX = 6;      // 이보다 작은 움직임은 손떨림으로 보고 세지 않는다
const WINDOW_MS = 1500;       // 이 시간 안에
const REVERSALS = 3;          // 방향을 이만큼 바꾸면 쓰다듬기
const COOLDOWN_MS = 3000;     // 한 번 쓰다듬은 뒤 이 시간 동안은 다시 세지 않는다

export type Petting = { lastX: number | null; lastDir: 0 | 1 | -1; reversals: number[]; cooldownUntil: number };

export function newPetting(): Petting {
  return { lastX: null, lastDir: 0, reversals: [], cooldownUntil: 0 };
}

export function feedPetting(s: Petting, x: number, now: number, overDog: boolean): { state: Petting; petted: boolean } {
  if (!overDog) return { state: { ...newPetting(), cooldownUntil: s.cooldownUntil }, petted: false };
  if (s.lastX === null) return { state: { ...s, lastX: x }, petted: false };
  const dx = x - s.lastX;
  if (Math.abs(dx) < MIN_STROKE_PX) return { state: s, petted: false };
  const dir: 1 | -1 = dx > 0 ? 1 : -1;
  let reversals = s.reversals.filter((t) => now - t <= WINDOW_MS);
  if (s.lastDir !== 0 && dir !== s.lastDir && now >= s.cooldownUntil) reversals = [...reversals, now];
  if (reversals.length >= REVERSALS) {
    return { state: { lastX: x, lastDir: dir, reversals: [], cooldownUntil: now + COOLDOWN_MS }, petted: true };
  }
  return { state: { ...s, lastX: x, lastDir: dir, reversals }, petted: false };
}
