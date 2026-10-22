import { describe, expect, it } from "vitest";
import {
  clockText, dateTimeText, formToRule, isSendKey, limitRows, nextRunText, resetText, ruleToForm, timeText, REPEAT_LABELS, WEEKDAY_LABELS,
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
