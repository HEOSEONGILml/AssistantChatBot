import type { Limit, Rule } from "./protocol";

export type RuleForm = { repeat: Rule["repeat"]; time: string; weekday: number | null; day: number | null };

export const REPEAT_LABELS = { daily: "매일", weekdays: "평일", weekly: "매주", monthly: "매월" } as const;
export const WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"] as const;

// 규칙 또는 한국어 오류 글
export function formToRule(f: RuleForm): Rule | string {
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(f.time)) return "시각을 골라 주세요";
  if (f.repeat === "weekly") {
    if (f.weekday === null || !Number.isInteger(f.weekday) || f.weekday < 0 || f.weekday > 6) return "요일을 골라 주세요";
    return { repeat: "weekly", time: f.time, weekday: f.weekday };
  }
  if (f.repeat === "monthly") {
    if (f.day === null || !Number.isInteger(f.day) || f.day < 1 || f.day > 31) return "날짜는 1~31일이에요";
    return { repeat: "monthly", time: f.time, day: f.day };
  }
  return { repeat: f.repeat, time: f.time };
}

export const ruleToForm = (r: Rule): RuleForm =>
  ({ repeat: r.repeat, time: r.time, weekday: r.weekday ?? null, day: r.day ?? null });

// Enter만 보낸다. Shift+Enter는 줄바꿈, 한글 조합 중 Enter는 무시
export const isSendKey = (e: { key: string; shiftKey: boolean; isComposing: boolean }): boolean =>
  e.key === "Enter" && !e.shiftKey && !e.isComposing;

const p2 = (n: number) => String(n).padStart(2, "0");
const hhmm = (d: Date) => `${p2(d.getHours())}:${p2(d.getMinutes())}`;
const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();

export function timeText(iso: string, now: Date): string {
  const d = new Date(iso);
  return sameDay(d, now) ? hhmm(d) : `${d.getMonth() + 1}/${d.getDate()}`;
}

export const nextRunText = (iso: string | null, now: Date = new Date()): string =>
  iso ? `다음 ${timeText(iso, now)}` : "";

// 초기화 시각: ISO 글, 초 또는 밀리초 숫자
export function resetText(at: Limit["resets_at"], now: Date): string {
  if (at === null) return "";
  const d = new Date(typeof at === "number" ? (at < 1e12 ? at * 1000 : at) : at);
  const ms = d.getTime() - now.getTime();
  if (Number.isNaN(ms)) return "";
  if (ms <= 0) return "곧 초기화";
  if (ms >= 24 * 3600_000) return `${WEEKDAY_LABELS[(d.getDay() + 6) % 7]} ${hhmm(d)} 초기화`;
  const total = Math.round(ms / 60_000);
  const h = Math.floor(total / 60), m = total % 60;
  return `${[h ? `${h}시간` : "", m || !h ? `${m}분` : ""].filter(Boolean).join(" ")} 뒤 초기화`;
}

export type LimitRow = { name: string; percent: number | null; resets_at: Limit["resets_at"] };

// utilization은 0~1을 %로, 1보다 크면 이미 %
const percentOf = (u: number | null) => (u === null ? null : Math.round(u > 1 ? u : u * 100));

export function limitRows(limits: Limit[]): { common: LimitRow[]; models: LimitRow[] } {
  const common: LimitRow[] = [], models: LimitRow[] = [];
  for (const l of limits) {
    const t = l.type.toLowerCase();
    const row = (name: string): LimitRow => ({ name, percent: percentOf(l.utilization), resets_at: l.resets_at });
    if (t.includes("opus")) models.push(row("Opus"));
    else if (t.includes("sonnet")) models.push(row("Sonnet"));
    else if (l.type === "five_hour") common.push(row("현재 세션"));
    else if (l.type === "seven_day") common.push(row("이번 주"));
    else common.push(row(l.type));
  }
  return { common, models };
}

export const clockText = (iso: string): string => hhmm(new Date(iso));

// 상세 창 날짜 줄: "10월 21일 09:10"
export function dateTimeText(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${hhmm(d)}`;
}
