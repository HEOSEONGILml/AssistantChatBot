import { describe, test, expect } from "vitest";
import {
  newDog, step, playAction, toggleHouse, currentAnimation, decide,
  SLEEP_IDLE_MS, type World, type Senses, type Dog,
} from "../src/body/dog";

// 강아지 크기 100×80, 움직일 수 있는 영역은 강아지 왼쪽 위 기준 x 0~900, y 0~520
const w: World = { width: 1000, height: 600, dogWidth: 100, dogHeight: 80, houseX: 800, houseY: 520, walkSpeed: 100, runSpeed: 250 };
const seq = (...xs: number[]) => { let i = 0; return () => xs[i++ % xs.length]; };
const senses = (o: Partial<Senses> = {}): Senses => ({ cursor: null, userIdleMs: 0, rand: seq(0.99), ...o });
const at = (x: number, y: number, o: Partial<Dog> = {}): Dog => ({ ...newDog(x, y), ...o });

describe("idle", () => {
  test("정해진 시간까지는 제자리에서 같은 자세", () => {
    const d = step(at(300, 200, { pose: "idle_sit", until: 5000 }), w, 1000, 16, senses());
    expect(d.mode).toBe("idle");
    expect([d.x, d.y]).toEqual([300, 200]);
    expect(currentAnimation(d)).toBe("idle_sit");
  });
  test("커서가 가까우면 커서 쪽을 바라본다", () => {
    const d = step(at(300, 200, { dir: 1, until: 5000 }), w, 1000, 16, senses({ cursor: { x: 250, y: 240 } }));
    expect(d.dir).toBe(-1);
  });
  test("시간이 지나면 다음 행동을 고른다", () => {
    const d = step(at(300, 200, { until: 1000 }), w, 1000, 16, senses({ rand: seq(0.9, 0.0, 0.5, 0.5) }));
    expect(d.mode).toBe("walk_to");
  });
});

describe("decide", () => {
  test("대부분은 가만히 있고 자세와 시간을 무작위로 고른다", () => {
    const d = decide(at(300, 200), w, 1000, senses({ rand: seq(0.1, 0.6, 0) }));
    expect(d.mode).toBe("idle");
    expect(d.pose).toBe("idle_sit");
    expect(d.until).toBe(1000 + 3000);
  });
  test("가끔 2차원 방향으로 걸어가고, 목표는 화면 안으로 제한된다", () => {
    // 0.9 → 걷기, 각도 0.5 → 180°(왼쪽), 거리 1.0 → 최대, 0.9 → 걷기
    const d = decide(at(100, 200), w, 0, senses({ rand: seq(0.9, 0.5, 0.999, 0.9) }));
    expect(d.mode).toBe("walk_to");
    expect(d.targetX).toBe(0);
    expect(d.targetY).toBeCloseTo(200);
    expect(d.running).toBe(false);
  });
  test("위아래로도 걸어간다", () => {
    // 각도 0.25 → 90°(아래쪽, 화면 좌표)
    const d = decide(at(300, 100), w, 0, senses({ rand: seq(0.9, 0.25, 0.0, 0.9) }));
    expect(d.targetX).toBeCloseTo(300);
    expect(d.targetY).toBeCloseTo(180);
  });
  test("걸어갈 때 가끔 달린다", () => {
    const d = decide(at(300, 200), w, 0, senses({ rand: seq(0.9, 0.0, 0.5, 0.1) }));
    expect(d.running).toBe(true);
  });
  test("커서가 가까우면 가끔 커서 쪽으로 다가가 조금 앞에서 멈춘다", () => {
    const d = decide(at(100, 100), w, 0, senses({ cursor: { x: 450, y: 140 }, rand: seq(0.1) }));
    expect(d.mode).toBe("walk_to");
    const cx = d.targetX + w.dogWidth / 2, cy = d.targetY + w.dogHeight / 2;
    const gap = Math.hypot(450 - cx, 140 - cy);
    expect(gap).toBeGreaterThan(40);
    expect(gap).toBeLessThan(100);
  });
});

describe("walk_to", () => {
  test("목표까지 대각선으로 걸어가 도착하면 잠깐 멈춰 선다", () => {
    let d = at(100, 100, { mode: "walk_to", targetX: 160, targetY: 180, running: false }); // 거리 100
    d = step(d, w, 0, 500, senses());
    expect(d.x).toBeCloseTo(130);
    expect(d.y).toBeCloseTo(140);
    expect(currentAnimation(d)).toBe("walk");
    d = step(d, w, 1000, 1000, senses());
    expect([d.x, d.y]).toEqual([160, 180]);
    expect(d.mode).toBe("idle");
    expect(d.until).toBeGreaterThan(1000);
  });
  test("가로로 움직일 때 그쪽을 바라본다", () => {
    const d = step(at(300, 200, { dir: 1, mode: "walk_to", targetX: 100, targetY: 200 }), w, 0, 16, senses());
    expect(d.dir).toBe(-1);
  });
  test("달릴 때는 runSpeed로 움직이고 run 애니메이션", () => {
    const d = step(at(100, 200, { mode: "walk_to", targetX: 900, targetY: 200, running: true }), w, 0, 1000, senses());
    expect(d.x).toBeCloseTo(350);
    expect(currentAnimation(d)).toBe("run");
  });
});

describe("sleep", () => {
  test("사용자가 오래 입력하지 않으면 잠든다", () => {
    const d = step(at(300, 200, { until: 99999 }), w, 1000, 16, senses({ userIdleMs: SLEEP_IDLE_MS }));
    expect(currentAnimation(d)).toBe("sleep");
  });
  test("걷던 중이어도 그 자리에서 잠든다", () => {
    const d = step(at(300, 200, { mode: "walk_to", targetX: 900, targetY: 200 }), w, 0, 16, senses({ userIdleMs: SLEEP_IDLE_MS }));
    expect(currentAnimation(d)).toBe("sleep");
    expect(d.mode).toBe("idle");
  });
  test("사용자가 돌아오면 깨어나 다음 행동을 고른다", () => {
    const d = step(at(300, 200, { pose: "sleep", until: 99999 }), w, 1000, 16, senses({ userIdleMs: 500, rand: seq(0.1, 0.0, 0) }));
    expect(currentAnimation(d)).toBe("idle_stand");
  });
});

describe("action", () => {
  test("끝나기 전에는 제자리, 끝나면 대기", () => {
    let d = playAction(at(100, 200), "bark", 0, 2000);
    d = step(d, w, 1000, 1000, senses());
    expect([d.x, d.y]).toEqual([100, 200]);
    expect(currentAnimation(d)).toBe("bark");
    d = step(d, w, 2000, 16, senses());
    expect(d.mode).toBe("idle");
  });
  test("집에 가는 중에는 무시", () => {
    const d = playAction(toggleHouse(at(100, 200), 0), "bark", 0, 2000);
    expect(d.mode).toBe("to_house");
  });
});

describe("house", () => {
  test("집 아이콘을 누르면 평소 달리기보다 빠르게 뛰어 들어간다", () => {
    const d = step(toggleHouse(at(100, 520), 0), w, 0, 1000, senses());
    expect(currentAnimation(d)).toBe("run");
    expect(d.x).toBeGreaterThan(100 + w.runSpeed);
  });
  test("어디에 있든 집까지 걸어가 도착하면 in_house", () => {
    let d = toggleHouse(at(800, 400), 0);
    d = step(d, w, 2000, 2000, senses());
    expect([d.x, d.y]).toEqual([800, 520]);
    expect(d.mode).toBe("in_house");
    expect(d.houseSince).toBe(2000);
  });
  test("가는 도중 다시 누르면 그 자리에 멈춘다", () => {
    const d = toggleHouse(toggleHouse(at(100, 200), 0), 10);
    expect(d.mode).toBe("idle");
    expect([d.x, d.y]).toEqual([100, 200]);
  });
  test("집에서 나오면 from_house를 거쳐 대기", () => {
    let d = step(toggleHouse(at(800, 520), 0), w, 0, 16, senses());
    expect(d.mode).toBe("in_house");
    d = toggleHouse(d, 5000);
    expect(d.mode).toBe("from_house");
    d = step(d, w, 6000, 1000, senses());
    expect(d.mode).toBe("idle");
    expect(d.x).toBeLessThan(800);
  });
  test("집에 있을 때는 사용자가 자리를 비워도 그대로", () => {
    const d = step(at(800, 520, { mode: "in_house" }), w, 0, 16, senses({ userIdleMs: SLEEP_IDLE_MS }));
    expect(d.mode).toBe("in_house");
  });
});
