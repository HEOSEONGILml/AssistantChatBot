import type { DogAction } from "./sprite";

// 강아지 상태 기계. 화면과 Tauri를 모르는 순수 로직이다.
// 평소 움직임(자율 행동)은 mochi-llm-pet을 참고했다: 화면 어디로든(2차원) 다니되 대부분 가만히 있고,
// 가끔 걷거나 뛰고, 커서를 바라보거나 따라가거나 사냥하고, 창 위에 올라앉거나 창을 구경한다.
// 사용자가 오래 자리를 비우면 잔다. 두뇌(Jev)가 행동을 고르면 playAction이 우선한다.

export type DogMode =
  | "idle" | "walk_to" | "action"
  | "follow" | "hunt" | "pounce"                 // 커서 따라가기·사냥
  | "perch_to" | "perched" | "watch_to" | "watching" // 창 위에 앉기·창 구경
  | "to_house" | "in_house" | "from_house"
  | "held" | "thrown";

// x, y는 강아지 그림의 왼쪽 위 (CSS px, 다닐 수 있는 영역 기준)
export type Dog = {
  x: number; y: number; dir: 1 | -1; mode: DogMode;
  pose: DogAction; until: number;                          // 대기·구경·앉기·따라가기: 자세와 끝나는 시각
  targetX: number; targetY: number; running: boolean;      // walk_to: 목표와 달리기 여부
  action: DogAction; actionEnd: number;                    // action: Jev·반응이 고른 동작
  houseSince: number | null;
  vx: number; vy: number;                                  // thrown: 속도 (CSS px/초)
  impact: number; bounces: number; thrownAt: number;       // thrown: 가장 세게 부딪힌 속도, 부딪힌 횟수, 던진 시각
  targetWin: number | null; perchFx: number;               // perch·watch: 대상 창과 윗변 위치 비율
  pounceStart: number; fromX: number; fromY: number;       // pounce: 점프 시작 시각과 출발점
  hop: number;                                             // 점프 높이 (그림만 위로 띄운다)
  clickSeenAt: number;                                     // 마지막으로 반응을 검토한 클릭 시각 (같은 클릭에 두 번 반응하지 않게)
  nap: boolean;                                            // 기분(졸림)이 고른 낮잠: 사용자가 있어도 정해진 시간까지 잔다
};

// width·height: 다닐 수 있는 영역(작업 영역) 크기. houseX·houseY: 집 앞에 선 강아지의 왼쪽 위
export type World = { width: number; height: number; dogWidth: number; dogHeight: number; houseX: number; houseY: number; walkSpeed: number; runSpeed: number };
// 창: 위치·크기와 사용 중인지만 안다 (제목·내용은 모른다). 좌표는 다닐 수 있는 영역 기준
// span: 윗변 중 다른 창에 가려지지 않고 보이는 가장 넓은 구간 (exposeTopEdges가 채운다. 없으면 윗변 전체)
export type Win = { id: number; left: number; top: number; width: number; height: number; active: boolean; span?: { left: number; right: number } | null };
// 평소 움직임 경향: 두뇌가 성격·기분으로 계산해 보낸다 (프로토콜 v2 movement). 두뇌가 없으면 기본 경향
export const MOVES = ["rest", "sleep", "roam", "approach", "play", "explore"] as const;
export type Move = (typeof MOVES)[number];
export type Movement = { weights: Record<Move, number>; run: number; idleScale: number };
// 기본 경향은 예전 "보통" 프로필과 같은 값이다 (두뇌 tuning.MOVE_BASE와 같게 유지)
export const DEFAULT_MOVEMENT: Movement = { weights: { rest: 0.6, sleep: 0.08, roam: 0.4, approach: 0.18, play: 0.06, explore: 0.2 }, run: 0.2, idleScale: 1 };
// 강아지가 느끼는 바깥 상황. rand는 테스트에서 바꿔 끼운다.
// rest: 설정의 쉬기(켜면 그 자리에서 잔다). movement: 두뇌가 보낸 평소 움직임 경향 (vision 2026-10-15)
// click: 가장 최근 마우스 클릭 위치와 지난 시간 (다른 창에서 난 클릭 포함)
export type Senses = { cursor: { x: number; y: number } | null; userIdleMs: number; windows: Win[]; rest: boolean; movement: Movement; click: { x: number; y: number; ageMs: number } | null; rand: () => number };
export type Behavior = "approach" | "follow" | "hunt" | "perch" | "watch" | "idle" | "sleep" | "walk";

// 잠정값들 (사용자 체감으로 조정)
export const SLEEP_IDLE_MS = 3 * 60 * 1000;   // mochi와 같이 3분 무입력이면 잔다
const IDLE_MAX_MS = 10000;                     // 잠든 뒤 다시 확인하는 간격
const PAUSE_MIN_MS = 1500, PAUSE_MAX_MS = 4000; // 걸어간 뒤 잠깐 멈추는 시간
const WALK_MIN_PX = 80, WALK_MAX_PX = 400;
const LOOK_RADIUS = 300;                      // 이 안에 커서가 있으면 바라본다
const CURSOR_RADIUS = 450;                    // 이 안에 커서가 있으면 커서 관련 행동이 후보가 된다
const APPROACH_STOP_PX = 60;                  // 커서 바로 앞이 아니라 조금 떨어져 멈춘다
// 대기 시간 (예전 "보통" 프로필). 두뇌가 보낸 경향의 idleScale을 곱한다
const POSE_IDLE_MIN_MS = 3000, POSE_IDLE_MAX_MS = 10000;
// 쉬기·낮잠 시간
const REST_IDLE_MIN_MS = 8000, REST_IDLE_MAX_MS = 20000;

// 다음 행동 가중치: 두뇌의 움직임 경향(범주)을 이 화면의 구체 행동으로 나눈다 (두뇌 스펙 v2 6.5절).
// 쉬기는 이동하는 행동을 모두 뺀다 (vision)
function behaviorWeights(s: Senses): Record<Behavior, number> {
  if (s.rest) return { approach: 0, follow: 0, hunt: 0, perch: 0, watch: 0, idle: 1, sleep: 0, walk: 0 };
  const m = s.movement.weights;
  return { approach: (m.approach * 2) / 3, follow: m.approach / 3, hunt: m.play, perch: m.explore / 2, watch: m.explore / 2, idle: m.rest, sleep: m.sleep, walk: m.roam };
}
// 근처 클릭: 최근 이 거리·시간 안에 클릭이 있으면 커서 관련 행동 가중치를 높이고, 대기 중이면 바로 반응할 수 있다 (사용자 제안)
const CLICK_RADIUS = 450, CLICK_RECENT_MS = 3000, CLICK_BOOST = 4, CLICK_REACT_CHANCE = 0.5;
const FOLLOW_MIN_MS = 5000, FOLLOW_MAX_MS = 10000;
const FOLLOW_GAP_PX = 70;                     // 커서와 이만큼 떨어져 따라간다
const HUNT_MS = 6000;                         // 이 시간 안에 못 잡으면 그만둔다
const POUNCE_RADIUS = 140;                    // 커서가 이만큼 가까우면 점프한다
const POUNCE_MS = 450, POUNCE_HEIGHT = 60;
const PERCH_MIN_MS = 8000, PERCH_MAX_MS = 20000;
const WATCH_MIN_MS = 6000, WATCH_MAX_MS = 12000;
const WATCH_GAP_PX = 10;                      // 창 옆에 이만큼 떨어져 앉는다
const ACTIVE_WINDOW_CHANCE = 0.6;             // 대상 창으로 사용 중인 창을 고를 확률
const HOUSE_DASH = 1.8;                       // 집으로 갈 때는 평소 달리기보다 빠르게 뛰어 들어간다 (사용자 요청)
const EXIT_DISTANCE = 80;                     // 집에서 나와 걷는 거리
const POKE_MS = 900;                          // 찔렸을 때 짖는 시간
const GRAVITY = 2400;                         // 던졌을 때 중력 (CSS px/초²)
const BOUNCE = 0.4;                           // 화면 끝에 부딪힐 때 남는 속도 비율
const THROW_MIN_SPEED = 600;                  // 이보다 느리게 놓으면 던지기가 아니라 그 자리에 내려놓기 (사용자 요청)
const FLOOR_BOUNCE_SPEED = 400;               // 바닥에 이보다 빠르게 떨어지면 튕긴다
const FLOOR_BOUNCE = 0.35, FLOOR_FRICTION = 0.6;

export function newDog(x: number, y: number): Dog {
  return {
    x, y, dir: 1, mode: "idle", pose: "idle_stand", until: 0, targetX: x, targetY: y, running: false,
    action: "idle_stand", actionEnd: 0, houseSince: null, vx: 0, vy: 0, impact: 0, bounces: 0, thrownAt: 0,
    targetWin: null, perchFx: 0.5, pounceStart: 0, fromX: x, fromY: y, hop: 0, clickSeenAt: -1, nap: false,
  };
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
// 커서가 강아지 몸 위에 있다: 쓰다듬는 중일 수 있으니 커서에 반응하는 움직임(고개 돌리기·따라가기·사냥)을 하지 않는다
const cursorOver = (d: Dog, w: World, s: Senses) =>
  !!s.cursor && s.cursor.x >= d.x && s.cursor.x <= d.x + w.dogWidth && s.cursor.y >= d.y && s.cursor.y <= d.y + w.dogHeight;
const clickNear = (d: Dog, w: World, s: Senses) => {
  if (!s.click || s.click.ageMs > CLICK_RECENT_MS) return false;
  const c = center(d, w);
  return Math.hypot(s.click.x - c.x, s.click.y - c.y) < CLICK_RADIUS;
};
const findWin = (s: Senses, id: number | null) => s.windows.find((x) => x.id === id) ?? null;
// 강아지가 올라앉거나 구경할 수 있는 창: 강아지보다 넓고, 윗변이 영역 안에 있는 창
const spanOf = (x: Win) => (x.span === undefined ? { left: x.left, right: x.left + x.width } : x.span);
const eligibleWindows = (w: World, s: Senses) => s.windows.filter((x) => {
  const sp = spanOf(x);
  return sp !== null && sp.right - sp.left > w.dogWidth * 1.5 && x.top >= w.dogHeight;
});

function pickPose(r: number): DogAction {
  if (r < 0.5) return "idle_stand";
  if (r < 0.85) return "idle_sit";
  return "idle_lay";
}

// 다음 행동 고르기 (가중치 표). r은 0~1 난수
export function pickBehavior(d: Dog, w: World, s: Senses, r: number): Behavior {
  const cursorNear = cursorDistance(d, w, s) < CURSOR_RADIUS && !cursorOver(d, w, s);
  const hasWin = eligibleWindows(w, s).length > 0;
  const base = behaviorWeights(s);
  const boost = clickNear(d, w, s) ? CLICK_BOOST : 1;
  const weights = { ...base, approach: base.approach * boost, follow: base.follow * boost, hunt: base.hunt * boost };
  const options = (Object.keys(weights) as Behavior[]).filter((b) => weights[b] > 0 &&
    (b === "approach" || b === "follow" || b === "hunt" ? cursorNear : b === "perch" || b === "watch" ? hasWin : true));
  const total = options.reduce((sum, b) => sum + weights[b], 0);
  let acc = 0;
  for (const b of options) { acc += weights[b]; if (r * total < acc) return b; }
  return options[options.length - 1];
}

function pickWindow(w: World, s: Senses): Win {
  const list = eligibleWindows(w, s);
  const active = list.find((x) => x.active);
  if (active && s.rand() < ACTIVE_WINDOW_CHANCE) return active;
  return list[Math.min(list.length - 1, Math.floor(s.rand() * list.length))];
}

// 창 윗변 위에 앉는 지점 (강아지 왼쪽 위)
// 윗변 중 보이는 구간 안에 앉는다
const perchPoint = (win: Win, fx: number, w: World) => {
  const sp = spanOf(win) ?? { left: win.left, right: win.left + win.width };
  return { x: clampX(sp.left + fx * (sp.right - sp.left) - w.dogWidth / 2, w), y: clampY(win.top - w.dogHeight, w) };
};
// 창 옆 아래쪽에서 창을 구경하는 지점
function watchPoint(d: Dog, win: Win, w: World) {
  const winCenter = win.left + win.width / 2;
  const x = winCenter >= center(d, w).x ? win.left - w.dogWidth - WATCH_GAP_PX : win.left + win.width + WATCH_GAP_PX;
  return { x: clampX(x, w), y: clampY(win.top + win.height - w.dogHeight, w) };
}

const idleFor = (d: Dog, now: number, ms: number, pose: DogAction = "idle_stand"): Dog =>
  ({ ...d, mode: "idle", pose, until: now + ms, targetWin: null, hop: 0, nap: false });

export function decide(d: Dog, w: World, now: number, s: Senses): Dog {
  const b = pickBehavior(d, w, s, s.rand());
  switch (b) {
    case "approach": {
      // 커서 바로 앞이 아니라 APPROACH_STOP_PX 떨어진 곳에서 멈춘다
      const c = center(d, w);
      const dx = s.cursor!.x - c.x, dy = s.cursor!.y - c.y;
      const len = Math.hypot(dx, dy) || 1;
      const stopX = s.cursor!.x - (dx / len) * APPROACH_STOP_PX;
      const stopY = s.cursor!.y - (dy / len) * APPROACH_STOP_PX;
      return { ...d, mode: "walk_to", targetX: clampX(stopX - w.dogWidth / 2, w), targetY: clampY(stopY - w.dogHeight / 2, w), running: false };
    }
    case "follow":
      return { ...d, mode: "follow", until: now + between(s.rand(), FOLLOW_MIN_MS, FOLLOW_MAX_MS) };
    case "hunt":
      return { ...d, mode: "hunt", until: now + HUNT_MS };
    case "perch": {
      const win = pickWindow(w, s);
      return { ...d, mode: "perch_to", targetWin: win.id, perchFx: between(s.rand(), 0.2, 0.8) };
    }
    case "watch":
      return { ...d, mode: "watch_to", targetWin: pickWindow(w, s).id };
    case "idle": {
      // 쉬기에서는 자세를 고르지 않고 그 자리에 엎드려 잔다 (vision)
      const pose = s.rest ? "sleep" : pickPose(s.rand());
      const [min, max] = s.rest ? [REST_IDLE_MIN_MS, REST_IDLE_MAX_MS] : [POSE_IDLE_MIN_MS, POSE_IDLE_MAX_MS];
      return { ...d, mode: "idle", pose, nap: false, until: now + between(s.rand(), min, max) * (s.rest ? 1 : s.movement.idleScale) };
    }
    case "sleep":
      // 낮잠: 두뇌의 경향(졸림)이 고른 잠. 사용자가 있어도 정해진 시간까지 잔다
      return { ...d, mode: "idle", pose: "sleep", nap: true, until: now + between(s.rand(), REST_IDLE_MIN_MS, REST_IDLE_MAX_MS) * s.movement.idleScale };
    case "walk": {
      const angle = s.rand() * 2 * Math.PI; // 화면 좌표: 0=오른쪽, π/2=아래
      const dist = between(s.rand(), WALK_MIN_PX, WALK_MAX_PX);
      return {
        ...d, mode: "walk_to",
        targetX: clampX(d.x + Math.cos(angle) * dist, w),
        targetY: clampY(d.y + Math.sin(angle) * dist, w),
        running: s.rand() < s.movement.run,
      };
    }
  }
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
// 스스로 움직이는 중인 상태: 사용자가 오래 자리를 비우면 그 자리에서 잔다
const AUTONOMOUS: DogMode[] = ["idle", "walk_to", "follow", "hunt", "watch_to", "watching"];

export function step(d: Dog, w: World, now: number, dtMs: number, s: Senses): Dog {
  if (AUTONOMOUS.includes(d.mode) && s.userIdleMs >= SLEEP_IDLE_MS) {
    return idleFor(d, now, IDLE_MAX_MS, "sleep");
  }
  switch (d.mode) {
    case "idle": {
      // 자리 비움으로 잠들었다가 사용자가 돌아왔으면 깬다. 쉬기에서는 깨지 않는다
      if (d.pose === "sleep" && !s.rest && !d.nap) return decide(d, w, now, s);
      let n = d;
      if (cursorDistance(d, w, s) < LOOK_RADIUS && !cursorOver(d, w, s)) n = { ...n, dir: s.cursor!.x >= center(d, w).x ? 1 : -1 };
      // 근처에서 새 클릭이 나면 대기를 끊고 바로 다음 행동을 고를 수 있다 (쉬기 제외)
      const clickAt = s.click ? now - s.click.ageMs : -1;
      if (!s.rest && clickNear(d, w, s) && clickAt > n.clickSeenAt) {
        n = { ...n, clickSeenAt: clickAt };
        if (s.rand() < CLICK_REACT_CHANCE) return decide(n, w, now, s);
      }
      return now >= n.until ? decide(n, w, now, s) : n;
    }
    case "walk_to": {
      const n = walkToward(d, d.targetX, d.targetY, d.running ? w.runSpeed : w.walkSpeed, dtMs);
      return arrived(n, d.targetX, d.targetY) ? idleFor(n, now, between(s.rand(), PAUSE_MIN_MS, PAUSE_MAX_MS)) : n;
    }
    case "action":
      return now >= d.actionEnd ? idleFor(d, now, PAUSE_MIN_MS) : d;

    case "follow": {
      if (!s.cursor || now >= d.until || cursorOver(d, w, s)) return idleFor(d, now, PAUSE_MIN_MS);
      const c = center(d, w);
      const dx = s.cursor.x - c.x, dy = s.cursor.y - c.y;
      const dist = Math.hypot(dx, dy);
      if (dist <= FOLLOW_GAP_PX) return { ...d, running: false, dir: dx >= 0 ? 1 : -1 }; // 충분히 가깝다
      const tx = clampX(s.cursor.x - (dx / dist) * FOLLOW_GAP_PX - w.dogWidth / 2, w);
      const ty = clampY(s.cursor.y - (dy / dist) * FOLLOW_GAP_PX - w.dogHeight / 2, w);
      const running = dist > CURSOR_RADIUS / 2;
      return { ...walkToward(d, tx, ty, running ? w.runSpeed : w.walkSpeed, dtMs), running };
    }
    case "hunt": {
      if (!s.cursor || now >= d.until) return idleFor(d, now, PAUSE_MIN_MS);
      const tx = clampX(s.cursor.x - w.dogWidth / 2, w), ty = clampY(s.cursor.y - w.dogHeight / 2, w);
      if (cursorDistance(d, w, s) < POUNCE_RADIUS) {
        return { ...d, mode: "pounce", pounceStart: now, fromX: d.x, fromY: d.y, targetX: tx, targetY: ty, dir: tx >= d.x ? 1 : -1 };
      }
      return walkToward(d, tx, ty, w.runSpeed, dtMs);
    }
    case "pounce": {
      const p = Math.min((now - d.pounceStart) / POUNCE_MS, 1);
      if (p >= 1) return { ...idleFor({ ...d, x: d.targetX, y: d.targetY }, now, PAUSE_MIN_MS), mode: "action", action: "bark", actionEnd: now + POKE_MS };
      return { ...d, x: d.fromX + (d.targetX - d.fromX) * p, y: d.fromY + (d.targetY - d.fromY) * p, hop: Math.sin(Math.PI * p) * POUNCE_HEIGHT };
    }

    case "perch_to": {
      const win = findWin(s, d.targetWin);
      if (!win) return idleFor(d, now, PAUSE_MIN_MS);
      const p = perchPoint(win, d.perchFx, w);
      const n = walkToward(d, p.x, p.y, w.walkSpeed, dtMs);
      if (!arrived(n, p.x, p.y)) return n;
      return { ...n, mode: "perched", pose: s.rand() < 0.6 ? "idle_sit" : "idle_lay", until: now + between(s.rand(), PERCH_MIN_MS, PERCH_MAX_MS) };
    }
    case "perched": {
      const win = findWin(s, d.targetWin);
      // 창이 닫히거나 최소화되면 그 자리에서 화면 아래로 떨어진다
      if (!win || spanOf(win) === null) return { ...d, mode: "thrown", vx: 0, vy: 0, targetWin: null };
      const p = perchPoint(win, d.perchFx, w); // 창을 옮기면 같이 움직인다
      const n = { ...d, x: p.x, y: p.y };
      return now >= d.until ? idleFor(n, now, PAUSE_MIN_MS) : n;
    }
    case "watch_to": {
      const win = findWin(s, d.targetWin);
      if (!win) return idleFor(d, now, PAUSE_MIN_MS);
      const p = watchPoint(d, win, w);
      const n = walkToward(d, p.x, p.y, w.walkSpeed, dtMs);
      if (!arrived(n, p.x, p.y)) return n;
      return { ...n, mode: "watching", pose: "idle_sit", until: now + between(s.rand(), WATCH_MIN_MS, WATCH_MAX_MS) };
    }
    case "watching": {
      const win = findWin(s, d.targetWin);
      if (!win || now >= d.until) return idleFor(d, now, PAUSE_MIN_MS);
      return { ...d, dir: win.left + win.width / 2 >= center(d, w).x ? 1 : -1 }; // 창 쪽을 바라본다
    }

    case "to_house": {
      const n = walkToward(d, w.houseX, w.houseY, w.runSpeed * HOUSE_DASH, dtMs);
      return arrived(n, w.houseX, w.houseY) ? { ...n, mode: "in_house", houseSince: now, hop: 0 } : n;
    }
    case "in_house":
    case "held":
      return d;
    case "from_house": {
      const target = w.houseX - EXIT_DISTANCE;
      const n = walkToward(d, target, w.houseY, w.walkSpeed, dtMs);
      return arrived(n, target, w.houseY) ? idleFor(n, now, PAUSE_MIN_MS) : n;
    }
    case "thrown": {
      const dt = dtMs / 1000;
      let vx = d.vx, vy = d.vy + GRAVITY * dt;
      let x = d.x + vx * dt, y = d.y + vy * dt;
      let impact = d.impact, bounces = d.bounces;
      // 부딪힐 때마다 그 순간의 속도를 기록한다. 착지할 때 화면이 충격으로 바꿔 두뇌에 알린다 (프로토콜 throw)
      const hit = (v: number) => { impact = Math.max(impact, Math.abs(v)); bounces++; };
      const maxX = w.width - w.dogWidth;
      if (x < 0) { x = 0; hit(vx); vx = -vx * BOUNCE; }
      if (x > maxX) { x = maxX; hit(vx); vx = -vx * BOUNCE; }
      if (y < 0) { y = 0; hit(vy); vy = -vy * BOUNCE; }
      const floor = w.height - w.dogHeight;
      if (y >= floor) {
        hit(vy);
        // 세게 떨어지면 바닥에서 한 번 더 튕기고, 약하면 내려앉는다
        if (vy > FLOOR_BOUNCE_SPEED) return { ...d, x, y: floor, vx: vx * FLOOR_FRICTION, vy: -vy * FLOOR_BOUNCE, impact, bounces };
        return { ...idleFor({ ...d, x, y: floor, vx: 0, vy: 0 }, now, PAUSE_MAX_MS, "idle_sit"), dir: vx >= 0 ? 1 : -1, impact, bounces };
      }
      return { ...d, x, y, vx, vy, impact, bounces };
    }
  }
}

export function playAction(d: Dog, a: DogAction, now: number, durationMs: number): Dog {
  if (d.mode === "to_house" || d.mode === "in_house" || d.mode === "from_house" || d.mode === "held" || d.mode === "thrown") return d;
  return { ...d, mode: "action", action: a, actionEnd: now + durationMs, targetWin: null, hop: 0 };
}

export function toggleHouse(d: Dog, now: number): Dog {
  switch (d.mode) {
    case "held":
    case "thrown":
      return d;
    case "to_house":
      return idleFor(d, now, PAUSE_MIN_MS);
    case "in_house":
      return { ...d, mode: "from_house", houseSince: null };
    default:
      return { ...d, mode: "to_house", targetWin: null, hop: 0 };
  }
}

export function currentAnimation(d: Dog): DogAction {
  switch (d.mode) {
    case "idle":
    case "perched":
    case "watching":
      return d.pose;
    case "walk_to":
    case "follow":
      return d.running ? "run" : "walk";
    case "action": return d.action;
    case "in_house": return "sleep";
    case "held": return "beg";
    case "hunt":
    case "pounce":
    case "to_house":
    case "thrown":
      return "run";
    default: return "walk";
  }
}

// ---- 몸 상호작용 (Jev를 거치지 않는 즉시 반응) ----

const busy = (d: Dog) => d.mode === "to_house" || d.mode === "in_house" || d.mode === "from_house" || d.mode === "held" || d.mode === "thrown" || d.mode === "pounce";

// 찌르기: 깜짝 놀라 짧게 짖는다
export function poke(d: Dog, now: number): Dog {
  return busy(d) ? d : { ...d, mode: "action", action: "bark", actionEnd: now + POKE_MS, targetWin: null };
}

// 잡기: 집에 들어가 있지 않으면 언제든 잡을 수 있다
export function grab(d: Dog): Dog {
  return d.mode === "in_house" ? d : { ...d, mode: "held", vx: 0, vy: 0, targetWin: null, hop: 0 };
}

// 잡은 채로 끌기: 강아지 왼쪽 위를 (x, y)에 둔다. 화면 안으로 제한
export function holdAt(d: Dog, x: number, y: number, w: World): Dog {
  return d.mode === "held" ? { ...d, x: clampX(x, w), y: clampY(y, w) } : d;
}

// 놓기: 천천히 놓으면 그 자리에 내려놓고, 빠르게 놓으면(던지기) 그 속도로 날아가 튕기다 화면 아래 바닥에 떨어진다
export function release(d: Dog, vx: number, vy: number, now = 0): Dog {
  if (d.mode !== "held") return d;
  if (Math.hypot(vx, vy) < THROW_MIN_SPEED) return idleFor(d, now, PAUSE_MAX_MS);
  return { ...d, mode: "thrown", vx, vy, dir: vx >= 0 ? 1 : -1, impact: 0, bounces: 0, thrownAt: now };
}

// 듣는 자세: 타이핑이 시작되면 대기 중인 강아지가 입력창(x, y: 다닐 수 있는 영역 좌표) 쪽을 바라보고,
// 멀리 있으면 가끔 몇 걸음 다가온다. 두뇌를 기다리지 않는 즉각 반응이다 (기분 8개 스펙 6절)
const LISTEN_WALK_CHANCE = 0.3, LISTEN_NEAR_PX = 250, LISTEN_STEP_PX = 120; // 잠정값
export function listenTo(d: Dog, w: World, x: number, y: number, _now: number, rand: () => number): Dog {
  if (d.mode !== "idle" || d.pose === "sleep") return d;
  const c = center(d, w);
  const dx = x - c.x, dy = y - c.y;
  const dist = Math.hypot(dx, dy);
  const faced: Dog = { ...d, dir: dx >= 0 ? 1 : -1 };
  if (dist > LISTEN_NEAR_PX && rand() < LISTEN_WALK_CHANCE) {
    const k = LISTEN_STEP_PX / dist;
    return { ...faced, mode: "walk_to", targetX: clampX(d.x + dx * k, w), targetY: clampY(d.y + dy * k, w), running: false };
  }
  return faced;
}
