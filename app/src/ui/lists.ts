// 알림 탭·작업 탭의 목록: 질문 카드, 작업 행, 페이저. 값은 다이제스트 2·3절(7 Alerts, 8 TaskPanel).
import type { Outgoing, Session } from "../shared/protocol";
import { alertRows, badges, firstWaiting, pendingQuestion, rowNote, type State, type View } from "../shared/state";
import { timeText } from "../shared/forms";
import { answered, answerKey } from "../shared/entries";
import { h, markdown, svg } from "./dom";

type Send = (m: Outgoing) => unknown; // false면 못 보냄
type Go = (v: View) => void;

export const ICON = {
  waiting: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" role="img" aria-label="답을 기다림"><circle cx="12" cy="12" r="10" fill="#C81E1E"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.4" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="17" r="1.2" fill="#FFFFFF"/></svg>`,
  working: `<svg class="spin" width="16" height="16" viewBox="0 0 24 24" fill="none" role="img" aria-label="진행 중"><circle cx="12" cy="12" r="9" stroke="#D5DAE1" stroke-width="3"/><path d="M21 12a9 9 0 0 0-9-9" stroke="#1D4ED8" stroke-width="3" stroke-linecap="round"/></svg>`,
  scheduleWorking: `<svg class="spin" width="16" height="16" viewBox="0 0 24 24" fill="none" role="img" aria-label="스케줄 진행 중"><circle cx="12" cy="12" r="9" stroke="#A7DCD3" stroke-width="3"/><path d="M21 12a9 9 0 0 0-9-9" stroke="#0F766E" stroke-width="3" stroke-linecap="round"/></svg>`,
  failed: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" role="img" aria-label="못 함"><circle cx="12" cy="12" r="10" fill="#FEF3C7"/><path d="M12 7v6" stroke="#B45309" stroke-width="2.4" stroke-linecap="round"/><circle cx="12" cy="16.5" r="1.4" fill="#B45309"/></svg>`,
  done: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" role="img" aria-label="다 함"><circle cx="12" cy="12" r="10" fill="#E3F4EA"/><path d="M7.5 12.5l3 3 6-6.5" stroke="#15803D" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  stopped: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" role="img" aria-label="멈춤"><circle cx="12" cy="12" r="9" stroke="#9AA3AF" stroke-width="2.4"/><path d="M7 12h10" stroke="#9AA3AF" stroke-width="2.4" stroke-linecap="round"/></svg>`,
  stop: `<svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2" fill="#B42318"/></svg>`,
  prev: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>`,
  next: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>`,
  plus: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14"/><path d="M5 12h14"/></svg>`,
};

const now = () => new Date();
const openSession = (s: State, t: Session, go: Go) => () => go({ tab: s.view.tab, screen: "task", sessionId: t.id, page: s.view.page });
const scheduleTag = (t: Session) => (t.source === "schedule" ? [" ", h("span", { class: "tag-schedule" }, "스케줄")] : []);

function stateIcon(t: Session): Element {
  if (t.state === "working") return svg(t.source === "schedule" ? ICON.scheduleWorking : ICON.working);
  return svg(ICON[t.state]);
}

// 세션 행 하나: 아이콘 · 이름(+스케줄 태그) · 부가 글 | [답하기] · 멈추기 · 시각
function sessionRow(s: State, t: Session, send: Send, go: Go): HTMLElement {
  const open = openSession(s, t, go);
  const note = rowNote(s, t);
  const right = t.state === "waiting"
    ? h("button", { type: "button", class: "row-answer", onClick: open }, "답하기")
    : t.state === "working"
      ? h("button", { type: "button", class: "row-stop", "aria-label": `${t.title} 멈추기`, onClick: () => send({ type: "stop", session_id: t.id }) }, svg(ICON.stop))
      : h("span", { class: "row-time" }, timeText(t.created_at, now()));
  return h("li", { class: "row" },
    h("button", { type: "button", class: "row-open", onClick: open },
      stateIcon(t),
      h("span", { class: "row-text" },
        h("b", {}, t.title), ...scheduleTag(t), " ",
        h("span", { class: t.state === "waiting" ? "note-ask" : "note" }, `· ${note}`))),
    right);
}

// 첫 질문 카드: 이름 · 출처 | 시각, 질문 글, [선택지…] 대화 보기 ›
function questionCard(s: State, t: Session, send: Send, go: Go): HTMLElement {
  const q = pendingQuestion(s, t.id);
  // 한 번 누르면 세션·줄이 바뀔 때까지 막는다 (두 번 답하지 않게)
  const key = answerKey(t, s.entries.get(t.id) ?? []);
  const pick = (c: string) => () => {
    if (send({ type: "say", session_id: t.id, text: c }) === false) return;
    answered.add(key);
    for (const b of choices) (b as HTMLButtonElement).disabled = true;
  };
  const choices = (q?.choices ?? []).map((c, i) =>
    h("button", { type: "button", class: i === 0 ? "btn-primary btn-sm" : "btn-secondary btn-sm", disabled: answered.has(key), onClick: pick(c) }, c));
  return h("div", { class: "card-wrap" },
    h("div", { class: "card" },
      h("div", { class: "card-head" },
        h("span", { class: "card-title" }, h("b", {}, t.title), " ",
          ...(t.source === "schedule" ? [h("span", { class: "tag-schedule" }, "스케줄")] : [h("span", { class: "note" }, "· 내 요청")])),
        h("span", { class: "card-time" }, timeText(q?.at ?? t.created_at, now()))),
      q ? h("div", { class: "card-text" }, markdown(q.text)) : h("span", { class: "card-text" }, rowNote(s, t)),
      h("div", { class: "card-actions" }, ...choices,
        h("button", { type: "button", class: "link", onClick: openSession(s, t, go) }, "대화 보기 ›"))));
}

export function pager(label: string, page: number, pages: number, onPage: (p: number) => void): HTMLElement {
  return h("nav", { class: "pager", "aria-label": label },
    h("button", { type: "button", "aria-label": "이전 페이지", disabled: page <= 1, onClick: () => onPage(page - 1) }, svg(ICON.prev)),
    h("span", {}, `${page} / ${pages}`),
    h("button", { type: "button", "aria-label": "다음 페이지", disabled: page >= pages, onClick: () => onPage(page + 1) }, svg(ICON.next)));
}

const rows = (s: State, ts: Session[], send: Send, go: Go, empty: string): HTMLElement =>
  ts.length ? h("ul", { class: "rows" }, ...ts.map((t) => sessionRow(s, t, send, go))) : h("p", { class: "empty" }, empty);

const toPage = (s: State, go: Go) => (page: number) => go({ ...s.view, page });

export function alertsBody(s: State, send: Send, go: Go): Node[] {
  const list = s.lists.alerts;
  if (!list) return [h("p", { class: "empty" }, "불러오는 중…")];
  const card = firstWaiting(s);
  const rest = alertRows(s);
  return [
    ...(card ? [questionCard(s, card, send, go)] : []),
    ...(card && !rest.length ? [] : [rows(s, rest, send, go, "새 알림이 없어요")]),
    pager("알림 페이지", s.view.page, Math.max(list.pages, 1), toPage(s, go)),
  ];
}

export function tasksBody(s: State, send: Send, go: Go): Node[] {
  const list = s.lists.user;
  return [
    list ? rows(s, list.items, send, go, "아직 맡긴 작업이 없어요") : h("p", { class: "empty" }, "불러오는 중…"),
    pager("작업 목록 페이지", s.view.page, Math.max(list?.pages ?? 1, 1), toPage(s, go)),
    h("div", { class: "add" },
      h("button", { type: "button", class: "add-btn", onClick: () => go({ tab: "tasks", screen: "newTask", page: s.view.page }) }, svg(ICON.plus), "새 작업")),
  ];
}

// 알림 탭 라벨 옆 미니 배지 (로그아웃이면 없음)
export function miniBadges(s: State): HTMLElement[] {
  if (s.loggedIn === false) return [];
  const b = badges(s);
  return ([["red", b.red], ["yellow", b.yellow], ["green", b.green]] as const)
    .filter(([, n]) => n > 0)
    .map(([c, n]) => h("span", { class: `mini mini-${c}` }, String(n)));
}
