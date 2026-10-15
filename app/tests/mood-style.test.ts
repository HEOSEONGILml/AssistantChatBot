import { describe, expect, test } from "vitest";
import { EMOTES, faceMood, REACTION_MS, moodStyle, reactionHop } from "../src/body/mood-style";

describe("기분 스타일", () => {
  test("평온은 아무 변형이 없다", () => {
    expect(moodStyle("calm")).toEqual({ speed: 1, offsetY: 0, tint: null, jitter: 0, tilt: 0, bounce: 0 });
  });
  test("신남은 빠르고 튄다, 서운함은 느리고 고개를 숙인다", () => {
    expect(moodStyle("excited").speed).toBeGreaterThan(1);
    expect(moodStyle("excited").bounce).toBeGreaterThan(0);
    expect(moodStyle("sad").speed).toBeLessThan(1);
    expect(moodStyle("sad").offsetY).toBeGreaterThan(0);
  });
  test("짜증은 붉은빛, 무서움은 떨림, 궁금함은 갸웃", () => {
    expect(moodStyle("annoyed").tint).toMatch(/^rgba\(2/);
    expect(moodStyle("scared").jitter).toBeGreaterThan(0);
    expect(moodStyle("curious").tilt).not.toBe(0);
  });
});

describe("반응 표시", () => {
  test("모든 반응에 아이콘이 있다", () => {
    expect(Object.keys(EMOTES).sort()).toEqual(["annoyed", "bored", "curious", "excited", "happy", "sad", "scared", "sleepy", "surprised"]);
  });
  test("반응이 오면 몸이 한 번 톡 튀고 금방 내려온다", () => {
    expect(reactionHop("excited", 0)).toBe(0);
    expect(reactionHop("excited", 120)).toBeGreaterThan(0);
    expect(reactionHop("excited", 400)).toBe(0);
    expect(reactionHop("surprised", 120)).toBeGreaterThan(reactionHop("bored", 120));
    expect(REACTION_MS).toBeGreaterThanOrEqual(1000);
  });
});

describe("얼굴 기분", () => {
  test("반응을 보여 주는 동안은 반응의 기분, 아니면 두드러진 기분", () => {
    expect(faceMood("calm", "surprised")).toBe("surprised");
    expect(faceMood("sad", null)).toBe("sad");
  });
});
