// 스케줄 탭: 목록(9), 새 스케줄(15), 스케줄 대화의 머리·작업 지시서 줄(16), 지시서 수정(17). 값은 다이제스트 3절·5절.
import type { Outgoing, Schedule, Session } from "../shared/protocol";
import type { State, View } from "../shared/state";
import { REPEAT_LABELS, WEEKDAY_LABELS, type RuleForm } from "../shared/forms";
import {
  afterEdit, draftOf, draftOfProposal, draftToFields, emptyDraft, instructionMeta, rowIcon, rowRight, type RowIcon, type ScheduleDraft,
} from "../shared/schedules";
import { BACK_ICON, deleteButton, expandButton, h, header, svg, switchButton } from "./dom";
import { ICON, pager } from "./lists";

type Send = (m: Outgoing) => unknown; // false면 못 보냄
type Go = (v: View) => void;

const ROW_ICON: Record<Exclude<RowIcon, null>, string> = {
  running: ICON.scheduleWorking,
  failed: ICON.failed.replace('aria-label="못 함"', 'aria-label="지난번 못 함"'),
  done: ICON.done.replace('aria-label="다 함"', 'aria-label="지난번 완료"'),
  off: ICON.stopped.replace('aria-label="멈춤"', 'aria-label="꺼짐"'),
};
const PEN_ICON = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>`;

// 양식에 적던 값. 다시 그려도(연결이 바뀌어도) 남는다. 양식을 열 때·마칠 때 비운다
let draft: { key: string; d: ScheduleDraft } | null = null;
const formKey = (v: View) => `${v.screen}|${v.sessionId ?? ""}`;

// 적던 값을 버린다
export function clearDraft(): void {
  draft = null;
}

// 양식 화면을 새로 연다
export function openForm(go: Go, v: View): void {
  clearDraft();
  go(v);
}

// --- 목록 (9) ---
export function schedulesBody(s: State, go: Go): Node[] {
  const list = s.lists.schedules;
  const v = s.view;
  const now = new Date();
  const rows = list?.items.map((r) => {
    const icon = rowIcon(r, s.schedules.get(r.session_id));
    return h("li", { class: r.state === "off" ? "row row-off" : "row" },
      h("button", { type: "button", class: "row-open", onClick: () => go({ tab: "schedules", screen: "schedule", sessionId: r.session_id, page: v.page }) },
        icon ? svg(ROW_ICON[icon]) : h("span", { class: "icon-gap", "aria-hidden": "true" }),
        h("span", { class: "row-text" }, h("b", {}, r.name), " ", h("span", { class: "note" }, `· ${r.label}`))),
      h("span", { class: r.state === "running" ? "row-right row-running" : "row-right" }, rowRight(r, now)));
  });
  return [
    !list ? h("p", { class: "empty" }, "불러오는 중…")
      : rows!.length ? h("ul", { class: "rows rows-schedule" }, ...rows!) : h("p", { class: "empty" }, "아직 스케줄이 없어요"),
    pager("스케줄 목록 페이지", v.page, Math.max(list?.pages ?? 1, 1), (page) => go({ ...v, page })),
    h("div", { class: "add" },
      h("button", { type: "button", class: "add-btn", onClick: () => openForm(go, { tab: "schedules", screen: "newSchedule", page: v.page }) },
        svg(ICON.plus), "새 스케줄")),
  ];
}

// --- 스케줄 대화 (16): 머리와 작업 지시서 줄. 대화는 renderConversation이 그린다 ---
// 머리: 뒤로, 이름 + 부제, 켜짐 스위치, 지우기(→ 확인), 크게 보기
export function scheduleHead(s: State, t: Session, send: Send, go: Go, openBig: (v: View) => void, askDelete: () => void): Node[] {
  const v = s.view;
  const sc = s.schedules.get(t.id);
  const on = sc?.enabled ?? false;
  const head = h("div", { class: "head" },
    h("button", { type: "button", class: "back", "aria-label": "스케줄 목록으로", onClick: () => go({ tab: "schedules", screen: "list", page: v.page }) }, svg(BACK_ICON)),
    h("div", { class: "head-main" },
      h("span", { class: "head-title" }, sc?.name ?? t.title),
      h("span", { class: "head-sub src-schedule" }, "스케줄")),
    sc ? switchButton({ on, label: "스케줄", disabled: !s.connected, onToggle: () => send({ type: "set_schedule_enabled", session_id: t.id, enabled: !on }) }) : null,
    deleteButton("스케줄 지우기", askDelete),
    expandButton("icon-btn", () => openBig(v)));
  return sc ? [head, instructionRow(sc, v, go)] : [head];
}

function instructionRow(sc: Schedule, v: View, go: Go): HTMLElement {
  return h("div", { class: "instr" },
    h("div", { class: "instr-main" },
      h("span", { class: "instr-meta" }, h("b", {}, "작업 지시서"), ` · ${instructionMeta(sc, new Date())}`),
      h("span", { class: "instr-text" }, sc.instruction)),
    h("button", { type: "button", class: "instr-edit", onClick: () => openForm(go, { tab: v.tab, screen: "editSchedule", sessionId: sc.session_id, page: v.page }) },
      svg(PEN_ICON), "수정"));
}

// --- 새 스케줄 (15) · 지시서 수정 (17) ---
// 그릴 준비가 됐는지(지시서 수정은 스케줄이나 등록 확인 값이 있어야 채운다). 패널이 다시 그릴지 정하는 열쇠에 쓴다
export function formReady(s: State): boolean {
  return !!startDraft(s);
}

function startDraft(s: State): ScheduleDraft | null {
  const v = s.view;
  if (draft?.key === formKey(v)) return draft.d;
  if (v.screen === "newSchedule") return emptyDraft();
  if (v.proposal) return draftOfProposal(v.proposal);
  const sc = v.sessionId !== undefined ? s.schedules.get(v.sessionId) : undefined;
  return sc ? draftOf(sc) : null;
}

const field = (label: string, id: string, control: HTMLElement, cls = "field") =>
  h("div", { class: cls }, h("label", { for: id, class: "label" }, label), control);

export function scheduleForm(s: State, send: Send, go: Go): Node[] {
  const v = s.view;
  const isNew = v.screen === "newSchedule";
  const back = () => { draft = null; go(isNew ? { tab: "schedules", screen: "list", page: v.page } : afterEdit(v)); };
  const backLabel = isNew ? "스케줄 목록으로" : v.proposal && v.tab !== "schedules" ? "대화로" : "스케줄 대화로";
  const title = isNew ? "새 스케줄" : "작업 지시서 수정";
  const start = startDraft(s);
  if (!start) return [header(title, backLabel, back), h("p", { class: "empty" }, "불러오는 중…")];
  const cur = { key: formKey(v), d: { ...start, form: { ...start.form } } };
  draft = cur;
  const d = cur.d;

  const name = h("input", { id: "sname", type: "text", class: "input", placeholder: "예: 메일 요약", onInput: (e) => { d.name = (e.target as HTMLInputElement).value; } }) as HTMLInputElement;
  name.value = d.name;
  const repeat = h("select", { id: "srepeat", class: "input" },
    ...Object.entries(REPEAT_LABELS).map(([k, label]) => h("option", { value: k, selected: d.form.repeat === k }, label))) as HTMLSelectElement;
  const time = h("input", { id: "stime", type: "time", class: "input", onInput: (e) => { d.form.time = (e.target as HTMLInputElement).value; } }) as HTMLInputElement;
  time.value = d.form.time;
  const day = h("input", {
    id: "sday", type: "number", class: "input", min: 1, max: 31, inputmode: "numeric",
    onInput: (e) => { const x = (e.target as HTMLInputElement).value; d.form.day = x === "" ? null : Number(x); },
  }) as HTMLInputElement;
  day.value = d.form.day === null ? "" : String(d.form.day);
  const dayField = field("일", "sday", day, "field field-day");
  const days = h("fieldset", { class: "days" }, h("legend", { class: "sr-only" }, "요일"),
    ...WEEKDAY_LABELS.map((label, i) => {
      const input = h("input", { type: "radio", name: "sweekday", value: i, checked: d.form.weekday === i, onChange: () => { d.form.weekday = i; } });
      return h("label", { class: "day-chip" }, input, label);
    }));
  // 반복에 따라 요일 칩(매주)·날짜 칸(매월)을 보인다
  const showExtra = () => {
    days.hidden = d.form.repeat !== "weekly";
    dayField.hidden = d.form.repeat !== "monthly";
  };
  repeat.addEventListener("change", () => { d.form.repeat = repeat.value as RuleForm["repeat"]; showExtra(); });
  showExtra();
  const body = h("textarea", { id: "sbody", class: "input body", placeholder: "무엇을 할지 적어 주세요", onInput: (e) => { d.instruction = (e.target as HTMLTextAreaElement).value; } }) as HTMLTextAreaElement;
  body.value = d.instruction;
  const error = h("p", { class: "form-error", role: "alert" });

  const submit = (e: Event) => {
    e.preventDefault();
    const f = draftToFields(d);
    if (typeof f === "string") { error.textContent = f; return; }
    const ok = isNew ? send({ type: "add_schedule", ...f }) : send({ type: "set_schedule", session_id: v.sessionId!, ...f });
    if (ok === false) { error.textContent = "백엔드에 연결되지 않아 보내지 못했어요"; return; }
    draft = null;
    go(isNew ? { tab: "schedules", screen: "list", page: 1 } : afterEdit(v));
  };
  return [
    header(title, backLabel, back),
    // 고치기 시작하면 오류 글을 지운다
    // 브라우저 기본 검사 말풍선 대신 양식 아래 글로 알린다
    h("form", { class: "form sform", novalidate: true, onSubmit: submit, onInput: () => { error.textContent = ""; }, onChange: () => { error.textContent = ""; } },
      field("이름", "sname", name),
      h("div", { class: "when" },
        h("div", { class: "when-row" }, field("반복", "srepeat", repeat), field("시각", "stime", time), dayField),
        days),
      field("할 일", "sbody", body),
      isNew || v.proposal ? null : h("span", { class: "form-hint" }, "저장하면 다음 실행부터 적용돼요"),
      error,
      h("div", { class: "form-buttons" },
        h("button", { type: "button", class: "btn-secondary", onClick: back }, "취소"),
        h("button", { type: "submit", class: "btn-primary", disabled: !s.connected }, isNew ? "등록" : "저장"))),
  ];
}
