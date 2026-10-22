import { describe, expect, it } from "vitest";
import type { Schedule, ScheduleRow } from "../src/shared/protocol";
import {
  afterEdit, draftOf, draftOfProposal, draftToFields, emptyDraft, instructionMeta, rowIcon, rowRight, type ScheduleDraft,
} from "../src/shared/schedules";

const row = (o: Partial<ScheduleRow> = {}): ScheduleRow =>
  ({ session_id: 3, name: "메일 요약", label: "매일 09:00", next_run: "2026-10-23T09:00:00", state: "next", ...o });
const sc = (o: Partial<Schedule> = {}): Schedule => ({
  session_id: 3, name: "메일 요약", rule: { repeat: "weekly", time: "10:30", weekday: 0 }, instruction: "메일을 요약해 줘",
  label: "매주 월 10:30", enabled: true, next_run: "2026-10-26T10:30:00", last_run_at: null, last_result: null, ...o,
});
const now = new Date("2026-10-22T12:00:00");

describe("스케줄 목록 행", () => {
  it("아이콘: 도는 중·꺼짐은 행 상태, 켜짐은 캐시의 지난번 결과", () => {
    expect(rowIcon(row({ state: "running" }), sc({ last_result: "failed" }))).toBe("running");
    expect(rowIcon(row({ state: "off" }), sc({ last_result: "done" }))).toBe("off");
    expect(rowIcon(row(), sc({ last_result: "failed" }))).toBe("failed");
    expect(rowIcon(row(), sc({ last_result: "done" }))).toBe("done");
    expect(rowIcon(row(), sc({ last_result: "stopped" }))).toBeNull();
    expect(rowIcon(row(), sc())).toBeNull();
    expect(rowIcon(row(), undefined)).toBeNull(); // 캐시에 없으면 아이콘 없이
  });

  it("오른쪽 글: 도는 중 · 다음 … · 꺼짐", () => {
    expect(rowRight(row({ state: "running" }), now)).toBe("도는 중");
    expect(rowRight(row({ state: "off", next_run: null }), now)).toBe("꺼짐");
    expect(rowRight(row({ next_run: "2026-10-22T14:00:00" }), now)).toBe("다음 14:00");
    expect(rowRight(row({ next_run: "2026-10-26T10:30:00" }), now)).toBe("다음 10/26");
    expect(rowRight(row({ next_run: null }), now)).toBe("");
  });

  it("작업 지시서 줄: 규칙 글 · 다음 실행", () => {
    expect(instructionMeta(sc(), now)).toBe("매주 월 10:30 · 다음 10/26");
    expect(instructionMeta(sc({ enabled: false, next_run: null }), now)).toBe("매주 월 10:30");
  });
});

describe("스케줄 양식", () => {
  const d = (o: Partial<ScheduleDraft> = {}): ScheduleDraft => ({ ...emptyDraft(), name: "테스트", instruction: "할 일", ...o });

  it("빈 양식은 매일 09:00", () => {
    expect(emptyDraft()).toEqual({ name: "", form: { repeat: "daily", time: "09:00", weekday: null, day: null }, instruction: "" });
  });

  it("검사: 이름 → 규칙 → 할 일 순서, 앞뒤 빈칸은 뗀다", () => {
    expect(draftToFields(d({ name: "  " }))).toBe("이름을 적어 주세요");
    expect(draftToFields(d({ form: { repeat: "weekly", time: "09:00", weekday: null, day: null } }))).toBe("요일을 골라 주세요");
    expect(draftToFields(d({ instruction: "\n " }))).toBe("할 일을 적어 주세요");
    expect(draftToFields(d({ name: " 테스트 ", instruction: " 지금 몇 시인지 알려 줘\n" })))
      .toEqual({ name: "테스트", rule: { repeat: "daily", time: "09:00" }, instruction: "지금 몇 시인지 알려 줘" });
  });

  it("스케줄에서 채우기", () => {
    expect(draftOf(sc())).toEqual({ name: "메일 요약", form: { repeat: "weekly", time: "10:30", weekday: 0, day: null }, instruction: "메일을 요약해 줘" });
  });

  it("등록 확인 data에서 채우기. 모양이 틀린 칸은 빈 값", () => {
    expect(draftOfProposal({ name: "슬랙 정리", rule: { repeat: "monthly", time: "08:00", day: 5 }, instruction: "정리해 줘", label: "매월 5일 08:00" }))
      .toEqual({ name: "슬랙 정리", form: { repeat: "monthly", time: "08:00", weekday: null, day: 5 }, instruction: "정리해 줘" });
    expect(draftOfProposal({ name: 3, rule: { repeat: "yearly", time: "08:00" } })).toEqual(emptyDraft());
    expect(draftOfProposal({ rule: { repeat: "weekly", time: "08:00", weekday: "월" } }).form)
      .toEqual({ repeat: "weekly", time: "08:00", weekday: null, day: null });
  });
});

describe("지시서 수정 뒤 돌아갈 화면", () => {
  it("스케줄 대화에서 열었으면 그 스케줄 대화로", () => {
    expect(afterEdit({ tab: "schedules", screen: "editSchedule", sessionId: 3, page: 2 }))
      .toEqual({ tab: "schedules", screen: "schedule", sessionId: 3, page: 2 });
  });
  it("[고치기]로 열었으면 그 작업의 대화로", () => {
    const p = { name: "x" };
    expect(afterEdit({ tab: "chat", screen: "editSchedule", sessionId: 1, page: 1, proposal: p })).toEqual({ tab: "chat", screen: "list", page: 1 });
    expect(afterEdit({ tab: "tasks", screen: "editSchedule", sessionId: 5, page: 1, proposal: p })).toEqual({ tab: "tasks", screen: "task", sessionId: 5, page: 1 });
    expect(afterEdit({ tab: "schedules", screen: "editSchedule", sessionId: 3, page: 1, proposal: p })).toEqual({ tab: "schedules", screen: "schedule", sessionId: 3, page: 1 });
  });
});
