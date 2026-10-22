// 스케줄 탭의 글과 양식: 목록 행 아이콘·오른쪽 글, 작업 지시서 줄, 양식 채우기·검사, 수정 뒤 돌아갈 화면.
import type { Rule, Schedule, ScheduleRow } from "./protocol";
import type { View } from "./state";
import { formToRule, nextRunText, ruleToForm, REPEAT_LABELS, type RuleForm } from "./forms";

// 행 아이콘. 지난번 결과는 목록 행에 없어 캐시의 스케줄(`last_result`)로 고른다. 없으면 아이콘 없이
export type RowIcon = "running" | "failed" | "done" | "off" | null;

export function rowIcon(row: ScheduleRow, sc: Schedule | undefined): RowIcon {
  if (row.state === "running" || row.state === "off") return row.state;
  return sc?.last_result === "failed" || sc?.last_result === "done" ? sc.last_result : null;
}

export function rowRight(row: ScheduleRow, now: Date): string {
  if (row.state === "running") return "도는 중";
  if (row.state === "off") return "꺼짐";
  return nextRunText(row.next_run, now);
}

// 작업 지시서 줄 1행: `매일 09:00 · 다음 10/23` (꺼져 있으면 규칙 글만)
export const instructionMeta = (sc: Schedule, now: Date): string =>
  [sc.label, nextRunText(sc.next_run, now)].filter(Boolean).join(" · ");

export type ScheduleDraft = { name: string; form: RuleForm; instruction: string };

export const emptyDraft = (): ScheduleDraft =>
  ({ name: "", form: { repeat: "daily", time: "09:00", weekday: null, day: null }, instruction: "" });

export const draftOf = (sc: Schedule): ScheduleDraft => ({ name: sc.name, form: ruleToForm(sc.rule), instruction: sc.instruction });

// 등록 확인의 `data`({name, rule, instruction, …})로 채운다. 모양이 틀린 칸은 빈 값
export function draftOfProposal(data: Record<string, unknown>): ScheduleDraft {
  const d = emptyDraft();
  const r = data.rule as Record<string, unknown> | null | undefined;
  const int = (x: unknown) => (Number.isInteger(x) ? (x as number) : null);
  const form: RuleForm = typeof r === "object" && r !== null && typeof r.repeat === "string" && Object.hasOwn(REPEAT_LABELS, r.repeat) && typeof r.time === "string"
    ? { repeat: r.repeat as Rule["repeat"], time: r.time, weekday: int(r.weekday), day: int(r.day) }
    : d.form;
  return {
    name: typeof data.name === "string" ? data.name : d.name,
    form,
    instruction: typeof data.instruction === "string" ? data.instruction : d.instruction,
  };
}

// 보낼 값 또는 한국어 오류 글
export function draftToFields(d: ScheduleDraft): { name: string; rule: Rule; instruction: string } | string {
  const name = d.name.trim();
  if (!name) return "이름을 적어 주세요";
  const rule = formToRule(d.form);
  if (typeof rule === "string") return rule;
  const instruction = d.instruction.trim();
  if (!instruction) return "할 일을 적어 주세요";
  return { name, rule, instruction };
}

// 지시서 수정을 마치거나 그만둔 뒤: [고치기]로 열었으면 그 작업의 대화, 아니면 스케줄 대화
export function afterEdit(v: View): View {
  const taskId = v.taskId;
  if (v.proposal && v.tab === "chat") return { tab: "chat", screen: "list", page: 1 };
  if (v.tab === "schedules" || !v.proposal) return { tab: "schedules", screen: "schedule", taskId, page: v.page };
  return { tab: v.tab, screen: "task", taskId, page: v.page };
}
