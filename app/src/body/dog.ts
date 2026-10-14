import type { DogAction } from "./sprite";

// 평소 움직임(자율 행동). mochi-llm-pet의 방식을 참고했다: 화면 어디로든(2차원) 다니되 대부분 가만히 있고,
// 가끔 가까운 곳으로 걸어가 멈추며, 커서를 바라보고, 사용자가 오래 자리를 비우면 잔다.
// 두뇌(Jev)가 행동을 고르면 playAction이 우선한다.

export type DogMode = "idle" | "walk_to" | "action" | "to_house" | "in_house" | "from_house";
// x, y는 강아지 그림의 왼쪽 위 (CSS px)
export type Dog = {
  x: number; y: number; dir: 1 | -1; mode: DogMode;
  pose: DogAction; until: number;                          // idle: 자세와 끝나는 시각
  targetX: number; targetY: number; running: boolean;      // walk_to: 목표와 달리기 여부
  action: DogAction; actionEnd: number;    // action: Jev·반응이 고른 동작
  houseSince: number | null;
};
// width·height: 다닐 수 있는 영역(작업 영역) 크기. houseX·houseY: 집 앞에 선 강아지의 왼쪽 위
export type World = { width: number; height: number; dogWidth: number; dogHeight: number; houseX: number; houseY: number; walkSpeed: number; runSpeed: number };
// 강아지가 느끼는 바깥 상황. rand는 테스트에서 바꿔 끼운다.
export type Senses = { cursor: { x: number; y: number } | null; userIdleMs: number; rand: () => number };

// 잠정값들 (서브 프로젝트 3에서 사용자 체감으로 조정)
export const SLEEP_IDLE_MS = 3 * 60 * 1000;   // mochi와 같이 3분 무입력이면 잔다
const IDLE_CHANCE = 0.6;                      // 다음 행동이 "가만히 있기"일 확률
const IDLE_MIN_MS = 3000, IDLE_MAX_MS = 10000;
const PAUSE_MIN_MS = 1500, PAUSE_MAX_MS = 4000; // 걸어간 뒤 잠깐 멈추는 시간
const WALK_MIN_PX = 80, WALK_MAX_PX = 400;
const RUN_CHANCE = 0.2;
const LOOK_RADIUS = 300;                      // 이 안에 커서가 있으면 바라본다
const APPROACH_RADIUS = 450;                   // 이 안에 커서가 있으면 가끔 다가간다
const APPROACH_CHANCE = 0.3;
const APPROACH_STOP_PX = 60;                  // 커서 바로 앞이 아니라 조금 떨어져 멈춘다
const HOUSE_DASH = 1.8;                       // 집으로 갈 때는 평소 달리기보다 빠르게 뛰어 들어간다 (사용자 요청)
const EXIT_DISTANCE = 80;                     // 집에서 나와 걷는 거리

export function newDog(x: number, y: number): Dog {
  return { x, y, dir: 1, mode: "idle", pose: "idle_stand", until: 0, targetX: x, targetY: y, running: false, action: "idle_stand", actionEnd: 0, houseSince: null };
}

const between = (r: number, min: number, max: number) => min + r * (max - min);
const center = (d: Dog, w: World) => ({ x: d.x + w.dogWidth / 2, y: d.y + w.dogHeight / 2 });
const clamp = (v: number, max: number) => Math.min(Math.max(v, 0), max);
const clampX = (x: number, w: World) => clamp(x, w.width - w.dogWidth);
const clampY = (y: number, w: World) => clamp(y, w.height - w.dogHeight);
const cursorDistance = (d: Dog, w: World, s: Senses) => {
  if (!s.cursor) return Infinity;
  const c = center(d, w);
  return Math.hypot(s.cursor.x - c.x, s.cursor.y - c.y);
};

function pickPose(r: number): DogAction {
  if (r < 0.5) return "idle_stand";
  if (r < 0.85) return "idle_sit";
  return "idle_lay";
}

export function decide(d: Dog, w: World, now: number, s: Senses): Dog {
  const r = s.rand();
  if (cursorDistance(d, w, s) < APPROACH_RADIUS && r < APPROACH_CHANCE) {
    // 커서 바로 앞이 아니라 APPROACH_STOP_PX 떨어진 곳에서 멈춘다
    const c = center(d, w);
    const dx = s.cursor!.x - c.x, dy = s.cursor!.y - c.y;
    const len = Math.hypot(dx, dy) || 1;
    const stopX = s.cursor!.x - (dx / len) * APPROACH_STOP_PX;
    const stopY = s.cursor!.y - (dy / len) * APPROACH_STOP_PX;
    return { ...d, mode: "walk_to", targetX: clampX(stopX - w.dogWidth / 2, w), targetY: clampY(stopY - w.dogHeight / 2, w), running: false };
  }
  if (r < IDLE_CHANCE) {
    return { ...d, mode: "idle", pose: pickPose(s.rand()), until: now + between(s.rand(), IDLE_MIN_MS, IDLE_MAX_MS) };
  }
  const angle = s.rand() * 2 * Math.PI; // 화면 좌표: 0=오른쪽, π/2=아래
  const dist = between(s.rand(), WALK_MIN_PX, WALK_MAX_PX);
  return {
    ...d, mode: "walk_to",
    targetX: clampX(d.x + Math.cos(angle) * dist, w),
    targetY: clampY(d.y + Math.sin(angle) * dist, w),
    running: s.rand() < RUN_CHANCE,
  };
}

function walkToward(d: Dog, tx: number, ty: number, speed: number, dtMs: number): Dog {
  const dx = tx - d.x, dy = ty - d.y;
  const dist = Math.hypot(dx, dy);
  const stepPx = (speed * dtMs) / 1000;
  if (dist <= stepPx) return { ...d, x: tx, y: ty, dir: dx !== 0 ? (dx > 0 ? 1 : -1) : d.dir };
  // 가로 성분이 어느 정도 있을 때만 방향을 바꾼다 (거의 수직 이동이면 그대로)
  const dir: 1 | -1 = Math.abs(dx) / dist > 0.3 ? (dx > 0 ? 1 : -1) : d.dir;
  return { ...d, x: d.x + (dx / dist) * stepPx, y: d.y + (dy / dist) * stepPx, dir };
}

const arrived = (d: Dog, tx: number, ty: number) => d.x === tx && d.y === ty;

export function step(d: Dog, w: World, now: number, dtMs: number, s: Senses): Dog {
  const autonomous = d.mode === "idle" || d.mode === "walk_to";
  if (autonomous && s.userIdleMs >= SLEEP_IDLE_MS) {
    return { ...d, mode: "idle", pose: "sleep", until: now + IDLE_MAX_MS };
  }
  switch (d.mode) {
    case "idle": {
      if (d.pose === "sleep") return decide(d, w, now, s); // 사용자가 돌아왔다
      let n = d;
      if (cursorDistance(d, w, s) < LOOK_RADIUS) {
        n = { ...n, dir: s.cursor!.x >= center(d, w).x ? 1 : -1 };
      }
      return now >= n.until ? decide(n, w, now, s) : n;
    }
    case "walk_to": {
      const n = walkToward(d, d.targetX, d.targetY, d.running ? w.runSpeed : w.walkSpeed, dtMs);
      if (!arrived(n, d.targetX, d.targetY)) return n;
      return { ...n, mode: "idle", pose: "idle_stand", until: now + between(s.rand(), PAUSE_MIN_MS, PAUSE_MAX_MS) };
    }
    case "action":
      return now >= d.actionEnd ? { ...d, mode: "idle", pose: "idle_stand", until: now + PAUSE_MIN_MS } : d;
    case "to_house": {
      const n = walkToward(d, w.houseX, w.houseY, w.runSpeed * HOUSE_DASH, dtMs);
      return arrived(n, w.houseX, w.houseY) ? { ...n, mode: "in_house", houseSince: now } : n;
    }
    case "in_house":
      return d;
    case "from_house": {
      const target = w.houseX - EXIT_DISTANCE;
      const n = walkToward(d, target, w.houseY, w.walkSpeed, dtMs);
      return arrived(n, target, w.houseY) ? { ...n, mode: "idle", pose: "idle_stand", until: now + PAUSE_MIN_MS } : n;
    }
  }
}

export function playAction(d: Dog, a: DogAction, now: number, durationMs: number): Dog {
  if (d.mode === "to_house" || d.mode === "in_house" || d.mode === "from_house") return d;
  return { ...d, mode: "action", action: a, actionEnd: now + durationMs };
}

export function toggleHouse(d: Dog, now: number): Dog {
  switch (d.mode) {
    case "idle":
    case "walk_to":
    case "action":
    case "from_house":
      return { ...d, mode: "to_house" };
    case "to_house":
      return { ...d, mode: "idle", pose: "idle_stand", until: now + PAUSE_MIN_MS };
    case "in_house":
      return { ...d, mode: "from_house", houseSince: null };
  }
}

export function currentAnimation(d: Dog): DogAction {
  switch (d.mode) {
    case "idle": return d.pose;
    case "walk_to": return d.running ? "run" : "walk";
    case "action": return d.action;
    case "in_house": return "sleep";
    case "to_house": return "run";
    default: return "walk";
  }
}
