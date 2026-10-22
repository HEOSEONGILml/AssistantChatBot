import { describe, expect, it } from "vitest";
import {
  clockText, dateTimeText, formToRule, isSendKey, limitRight, limitRows, bytesText, nextRunText, resetText, ruleToForm, timeText, REPEAT_LABELS, WEEKDAY_LABELS,
  type RuleForm,
} from "../src/shared/forms";

const form = (o: Partial<RuleForm>): RuleForm => ({ repeat: "daily", time: "09:00", weekday: null, day: null, ...o });

describe("formToRule", () => {
  it("test_rule_form_validation", () => {
    expect(formToRule(form({ repeat: "weekly" }))).toBe("요일을 골라 주세요");
    expect(formToRule(form({ repeat: "monthly", day: 32 }))).toBe("날짜는 1~31일이에요");
    expect(formToRule(form({ repeat: "monthly", day: null }))).toBe("날짜는 1~31일이에요");
    expect(formToRule(form({ time: "" }))).toBe("시각을 골라 주세요");
    expect(formToRule(form({}))).toEqual({ repeat: "daily", time: "09:00" });
    expect(formToRule(form({ repeat: "weekdays", weekday: 3 }))).toEqual({ repeat: "weekdays", time: "09:00" });
  });
  it("왕복", () => {
    for (const r of [
      { repeat: "daily", time: "09:00" }, { repeat: "weekdays", time: "18:30" },
      { repeat: "weekly", time: "10:00", weekday: 0 }, { repeat: "monthly", time: "08:15", day: 31 },
    ] as const) expect(formToRule(ruleToForm(r))).toEqual(r);
    expect(ruleToForm({ repeat: "weekly", time: "10:00", weekday: 2 })).toEqual(form({ repeat: "weekly", time: "10:00", weekday: 2 }));
  });
  it("라벨", () => {
    expect(REPEAT_LABELS.weekdays).toBe("평일");
    expect(WEEKDAY_LABELS).toEqual(["월", "화", "수", "목", "금", "토", "일"]);
  });
});

describe("isSendKey", () => {
  it("test_enter_while_composing_does_not_send", () => {
    expect(isSendKey({ key: "Enter", shiftKey: false, isComposing: true })).toBe(false);
    expect(isSendKey({ key: "Enter", shiftKey: false, isComposing: false })).toBe(true);
  });
  it("Shift+Enter와 다른 키는 보내지 않는다", () => {
    expect(isSendKey({ key: "Enter", shiftKey: true, isComposing: false })).toBe(false);
    expect(isSendKey({ key: "a", shiftKey: false, isComposing: false })).toBe(false);
  });
});

describe("시간 글", () => {
  const now = new Date(2026, 9, 22, 12, 0); // 10/22 목
  it("timeText", () => {
    expect(timeText("2026-10-22T09:05:00", now)).toBe("09:05");
    expect(timeText("2026-10-21T09:05:00", now)).toBe("10/21");
  });
  it("nextRunText", () => {
    expect(nextRunText("2026-10-22T14:00:00", now)).toBe("다음 14:00");
    expect(nextRunText("2026-10-26T10:00:00", now)).toBe("다음 10/26");
    expect(nextRunText(null, now)).toBe("");
  });
  it("resetText", () => {
    expect(resetText("2026-10-22T14:10:00", now)).toBe("2시간 10분 뒤 초기화");
    expect(resetText("2026-10-22T12:45:00", now)).toBe("45분 뒤 초기화");
    expect(resetText("2026-10-23T14:00:00", now)).toBe("금 14:00 초기화");
    expect(resetText(null, now)).toBe("");
  });
  it("resetText는 초·밀리초 숫자도 받는다", () => {
    const t = new Date(2026, 9, 22, 14, 10).getTime();
    expect(resetText(t, now)).toBe("2시간 10분 뒤 초기화");
    expect(resetText(t / 1000, now)).toBe("2시간 10분 뒤 초기화");
  });
});

describe("limitRows", () => {
  const l = (type: string, utilization: number | null) => ({ type, utilization, resets_at: null, received_at: "x" });
  it("이름 규칙과 묶음", () => {
    const r = limitRows([l("five_hour", 0.426), l("seven_day", 0.5), l("seven_day_opus", 0.1), l("sonnet", 12), l("other", null)]);
    expect(r.common.map((x) => [x.name, x.percent])).toEqual([["현재 세션", 43], ["이번 주", 50], ["other", null]]);
    expect(r.models.map((x) => [x.name, x.percent])).toEqual([["Opus", 10], ["Sonnet", 12]]);
  });
  it("빈 목록", () => {
    expect(limitRows([])).toEqual({ common: [], models: [] });
  });
});

describe("clockText, dateTimeText", () => {
  it("시각과 날짜 시각", () => {
    expect(clockText("2026-10-21T09:05:00")).toBe("09:05");
    expect(dateTimeText("2026-10-21T09:10:00")).toBe("10월 21일 09:10");
  });
});

describe("limitRight", () => {
  const now = new Date("2026-10-22T12:00:00");
  it("퍼센트와 초기화 글", () => {
    expect(limitRight({ name: "현재 세션", percent: 42, resets_at: "2026-10-22T14:10:00" }, now)).toEqual({ percent: "42%", reset: "2시간 10분 뒤 초기화" });
  });
  it("값이 없으면 줄표, 초기화 시각이 없으면 빈 글", () => {
    expect(limitRight({ name: "x", percent: null, resets_at: null }, now)).toEqual({ percent: "—", reset: "" });
  });
});

describe("bytesText", () => {
  it("GB는 소수 한 자리, MB·KB는 정수로 올림 없이 가까운 값", () => {
    expect(bytesText(0)).toBe("0 KB");
    expect(bytesText(1536)).toBe("2 KB");
    expect(bytesText(5 * 1024 ** 2)).toBe("5 MB");
    expect(bytesText(1.8 * 1024 ** 3)).toBe("1.8 GB");
  });
});
