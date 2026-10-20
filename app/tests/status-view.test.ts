import { describe, expect, test } from "vitest";
import { judgementLines, stateSections } from "../src/shared/status-view";
import type { BrainState, Judgement } from "../src/shared/brain-protocol";

const MOODS = { 심심함: 0.6, 졸림: 0.3, 들뜸: 0.4, 시무룩: 0.2, 분노: 0.1, 궁금함: 0.5, 놀람: 0.1, 무서움: 0.1, 행복: 0.4 };
const state: BrainState = {
  dog: { mood: { ...MOODS, 분노: 0.75 } },
  movement: { weights: { rest: 0.6, sleep: 0.02, roam: 0.4, approach: 0.18, play: 0.06, explore: 0.2 }, run: 0.2, idle_scale: 1.1 },
};

describe("stateSections", () => {
  test("기분과 움직임 경향만 보여 준다", () => {
    expect(stateSections(state).map((s) => s.title)).toEqual(["기분", "평소 움직임 경향"]);
  });
  test("기분 9개를 모두 보여 준다", () => {
    expect(stateSections(state)[0].rows.map((r) => r.label)).toEqual(Object.keys(MOODS));
  });
  test("기분 값을 보여 준다", () => {
    const [mood] = stateSections(state);
    expect(mood.rows.find((r) => r.label === "분노")).toEqual({ label: "분노", value: 0.75 });
  });
  test("움직임 경향은 비율로 보여 준다", () => {
    const move = stateSections(state)[1];
    const total = 0.6 + 0.02 + 0.4 + 0.18 + 0.06 + 0.2;
    expect(move.rows.find((r) => r.label === "쉬기")?.value).toBeCloseTo(0.6 / total);
    expect(move.rows.find((r) => r.label === "달리기 비율")?.value).toBe(0.2);
  });
});

describe("judgementLines", () => {
  const j: Judgement = {
    ts: new Date(2026, 9, 15, 14, 3, 7).getTime() / 1000,
    events: [{ 종류: "찌르기" }, { 종류: "메시지 보냄", 맥락: { 글: "안녕" } }],
    jev: { action: { beg: 1 }, speak: 0.5, change: { "들뜸↑": 0.7, "변화없음": 0.3 } },
    model: { action: { beg: 1 }, speak: 0.62 },
    picked: { reaction: "excited", action: "beg", speak: true },
    mood_change: { 들뜸: 0.05, 분노: -0.02 },
    utterance: "멍! 안녕",
  };
  test("이벤트, 분포, 뽑힌 결과, 기분 변화, 대사를 줄로 만든다", () => {
    expect(judgementLines(j)).toEqual([
      "14:03:07 · 찌르기, 메시지 보냄(글 안녕)",
      "  변화  Jev 들뜸↑ 0.70 변화없음 0.30",
      "  반응  신남 (가장 크게 오른 기분)",
      "  동작  Jev 조르기 1.00 → 보정 조르기 1.00 → 조르기",
      "  말하기  Jev 0.50 → 최종 0.62 → 말함: 멍! 안녕",
      "  기분  들뜸 +0.05, 분노 -0.02",
    ]);
  });
  test("판단이 실패했으면 이유를 보여 준다", () => {
    expect(judgementLines({ ts: j.ts, events: [{ 종류: "찌르기" }], error: "Jev 실패: timeout" }))
      .toEqual(["14:03:07 · 찌르기", "  Jev 실패: timeout"]);
  });
});
