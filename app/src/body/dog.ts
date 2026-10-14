import type { DogAction } from "./sprite";

export type DogMode = "wander" | "action" | "to_house" | "in_house" | "from_house";
export type Dog = { x: number; dir: 1 | -1; mode: DogMode; action: DogAction; actionEnd: number; houseSince: number | null };
export type World = { floorWidth: number; dogWidth: number; houseX: number; speed: number };

const EXIT_DISTANCE = 80; // 집에서 나와 걷는 거리(CSS px)

export function newDog(x: number): Dog {
  return { x, dir: 1, mode: "wander", action: "walk", actionEnd: 0, houseSince: null };
}

function walkToward(d: Dog, target: number, w: World, dtMs: number): Dog {
  const stepPx = (w.speed * dtMs) / 1000;
  const dir: 1 | -1 = target >= d.x ? 1 : -1;
  const x = Math.abs(target - d.x) <= stepPx ? target : d.x + dir * stepPx;
  return { ...d, x, dir };
}

export function step(d: Dog, w: World, now: number, dtMs: number): Dog {
  switch (d.mode) {
    case "wander": {
      const max = w.floorWidth - w.dogWidth;
      let x = d.x + (d.dir * w.speed * dtMs) / 1000;
      let dir = d.dir;
      if (x >= max) { x = max; dir = -1; }
      if (x <= 0) { x = 0; dir = 1; }
      return { ...d, x, dir };
    }
    case "action":
      return now >= d.actionEnd ? { ...d, mode: "wander" } : d;
    case "to_house": {
      const n = walkToward(d, w.houseX, w, dtMs);
      return n.x === w.houseX ? { ...n, mode: "in_house", houseSince: now } : n;
    }
    case "in_house":
      return d;
    case "from_house": {
      const target = w.houseX - EXIT_DISTANCE;
      const n = walkToward(d, target, w, dtMs);
      return n.x === target ? { ...n, mode: "wander", dir: -1 } : n;
    }
  }
}

export function playAction(d: Dog, a: DogAction, now: number, durationMs: number): Dog {
  if (d.mode === "to_house" || d.mode === "in_house" || d.mode === "from_house") return d;
  return { ...d, mode: "action", action: a, actionEnd: now + durationMs };
}

export function toggleHouse(d: Dog, _now: number): Dog {
  switch (d.mode) {
    case "wander":
    case "action":
    case "from_house":
      return { ...d, mode: "to_house" };
    case "to_house":
      return { ...d, mode: "wander" };
    case "in_house":
      return { ...d, mode: "from_house", houseSince: null };
  }
}

export function currentAnimation(d: Dog): DogAction {
  if (d.mode === "action") return d.action;
  if (d.mode === "in_house") return "sleep";
  return "walk";
}
