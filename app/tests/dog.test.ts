import { describe, test, expect } from "vitest";
import { newDog, step, playAction, toggleHouse, currentAnimation, type World } from "../src/body/dog";

const w: World = { floorWidth: 1000, dogWidth: 128, houseX: 800, speed: 100 };

describe("wander", () => {
  test("방향대로 speed만큼 움직인다", () => expect(step(newDog(100), w, 0, 1000).x).toBe(200));
  test("오른쪽 끝에서 방향을 바꾸고 화면 밖으로 나가지 않는다", () => {
    const d = step({ ...newDog(860), dir: 1 }, w, 0, 1000);
    expect(d.x).toBe(w.floorWidth - w.dogWidth);
    expect(d.dir).toBe(-1);
  });
  test("왼쪽 끝에서 방향을 바꾼다", () => {
    const d = step({ ...newDog(50), dir: -1 }, w, 0, 1000);
    expect(d.x).toBe(0);
    expect(d.dir).toBe(1);
  });
});

describe("action", () => {
  test("끝나기 전에는 제자리, 끝나면 wander", () => {
    let d = playAction(newDog(100), "bark", 0, 2000);
    d = step(d, w, 1000, 1000);
    expect(d.x).toBe(100);
    expect(currentAnimation(d)).toBe("bark");
    d = step(d, w, 2000, 1000);
    expect(d.mode).toBe("wander");
  });
  test("집에 가는 중에는 무시", () => {
    const d = playAction(toggleHouse(newDog(100), 0), "bark", 0, 2000);
    expect(d.mode).toBe("to_house");
  });
});

describe("house", () => {
  test("집으로 걸어가 도착하면 in_house", () => {
    let d = toggleHouse(newDog(700), 0);
    d = step(d, w, 2000, 2000);
    expect(d.x).toBe(800);
    expect(d.mode).toBe("in_house");
    expect(d.houseSince).toBe(2000);
  });
  test("가는 도중 다시 누르면 바로 돌아선다", () => {
    let d = toggleHouse(newDog(100), 0);
    d = toggleHouse(d, 10);
    expect(d.mode).toBe("wander");
  });
  test("집에서 나오면 from_house를 거쳐 wander", () => {
    let d = step(toggleHouse(newDog(800), 0), w, 0, 16);
    expect(d.mode).toBe("in_house");
    d = toggleHouse(d, 5000);
    expect(d.mode).toBe("from_house");
    d = step(d, w, 6000, 1000);
    expect(d.mode).toBe("wander");
    expect(d.x).toBeLessThan(800);
  });
});
