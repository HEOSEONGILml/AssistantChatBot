// 패널 틀: 연결 띠, 탭 바, 탭별 본문, 새 작업 화면, 대화 화면, 지우기 확인, 꼬리. 값은 다이제스트 2절, 3절 6·7·8·11·16·18·19번.
import type { Entry, Outgoing, Session } from "../shared/protocol";
import { badges, STATE_TEXT, type State, type Tab, type View } from "../shared/state";
import { isSendKey } from "../shared/forms";
import { BACK_ICON, deleteButton, expandButton, h, header, svg, trashIcon } from "./dom";
import { renderConversation } from "./conversation";
import { alertsBody, miniBadges, tasksBody } from "./lists";
import { settingsBody } from "./settings";
import { usageBody } from "./usage";
import { formReady, scheduleForm, scheduleHead, schedulesBody } from "./schedule";

type Send = (m: Outgoing) => unknown;
type Go = (v: View) => void;
type OpenBig = (v: View) => void; // 크게 보기: 지금 보는 화면을 큰 창으로

const USAGE_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3v18h18"/><path d="M8 16v-3"/><path d="M13 16V9"/><path d="M18 16V6"/></svg>`;
const SETTINGS_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`;
const STOP_ICON = `<svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2" fill="#B42318"/></svg>`;

const TEXT_TABS: [Tab, string][] = [["alerts", "알림"], ["chat", "대화"], ["tasks", "작업"], ["schedules", "스케줄"]];
const ICON_TABS: [Tab, string, string][] = [["usage", "사용량", USAGE_ICON], ["settings", "설정", SETTINGS_ICON]];

let draft = ""; // 새 작업 입력 글. 다시 그려도 남는다

// 탭 바: 텍스트 탭 4개, 아이콘 탭 2개, 오른쪽 끝에 크게 보기
function tabBar(s: State, go: Go, openBig: OpenBig): HTMLElement {
  const open = (tab: Tab) => () => go({ tab, screen: "list", page: 1 });
  const sel = (tab: Tab) => s.view.tab === tab;
  return h("div", { class: "tabbar" },
    h("div", { role: "tablist", "aria-label": "보기", class: "tabs" },
      ...TEXT_TABS.map(([tab, label]) => h("button", {
        type: "button", role: "tab", class: "tab", "aria-selected": String(sel(tab)), onClick: open(tab),
      }, label, ...(tab === "alerts" ? [" ", ...miniBadges(s)] : []))),
      ...ICON_TABS.map(([tab, label, icon]) => h("button", {
        type: "button", role: "tab", class: "tab tab-icon", "aria-label": label, "aria-selected": String(sel(tab)), onClick: open(tab),
      }, svg(icon)))),
    expandButton("icon-btn tab-expand", () => openBig(s.view)));
}

const loading = () => h("p", { class: "empty" }, "불러오는 중…");

// 새 작업 화면(6 Input): [취소]·뒤로 → 작업 탭, [맡기기]·Enter → request 후 작업 탭
export function newTask(s: State, send: Send, go: Go): Node[] {
  const toTasks = () => go({ tab: "tasks", screen: "list", page: 1 });
  const area = h("textarea", {
    id: "newreq", class: "newreq", placeholder: "예: 아까 슬랙에서 본 링크, 카톡으로 민지한테 보내 줘",
    onInput: (e) => { draft = (e.target as HTMLTextAreaElement).value; },
  }) as HTMLTextAreaElement;
  area.value = draft;
  const submit = (e?: Event) => {
    e?.preventDefault();
    const text = area.value.trim();
    if (!text || !s.connected) return;
    if (send({ type: "request", text }) === false) return; // 못 보냈으면 글을 두고 이 화면에 남는다
    draft = "";
    toTasks();
  };
  area.addEventListener("keydown", (e) => { if (isSendKey(e)) submit(e); });
  queueMicrotask(() => area.focus());
  return [
    header("새 작업", "작업 목록으로", toTasks),
    h("form", { class: "form", onSubmit: submit },
      h("label", { for: "newreq", class: "label" }, "무엇을 할까요?"),
      area,
      h("div", { class: "form-actions" },
        h("span", { class: "hint" }, "Enter 보내기 · Shift+Enter 줄바꿈"),
        h("button", { type: "button", class: "btn-secondary", onClick: toTasks }, "취소"),
        h("button", { type: "submit", class: "btn-primary", disabled: !s.connected }, "맡기기"))),
  ];
}

function body(s: State, send: Send, go: Go, openBig: OpenBig): Node[] {
  const v = s.view;
  if (v.screen === "newTask") return newTask(s, send, go);
  if (v.screen === "newSchedule" || v.screen === "editSchedule") return scheduleForm(s, send, go);
  if (v.screen !== "list") {
    // 작업 대화·스케줄 대화는 세션을 받기 전까지 "불러오는 중"
    const title = (v.sessionId !== undefined && s.sessions.get(v.sessionId)?.title) || "";
    const backLabel = v.screen === "schedule" ? "스케줄 목록으로" : "목록으로";
    return [header(title, backLabel, () => go({ tab: v.tab, screen: "list", page: v.page })), loading()];
  }
  const content = v.tab === "alerts" ? alertsBody(s, send, go)
    : v.tab === "tasks" ? tasksBody(s, send, go)
    : v.tab === "chat" ? [loading()] // 대화 작업을 아직 모를 때
    : v.tab === "schedules" ? schedulesBody(s, go)
    : v.tab === "usage" ? usageBody(s)
    : settingsBody(s, send);
  return [tabBar(s, go, openBig), ...content];
}

export const SOURCE_TEXT: Record<Session["source"], string> = { user: "내 요청", schedule: "스케줄", chat: "대화" };
const NO_ENTRIES: Entry[] = [];

// 작업 대화 머리(11): 뒤로, 제목 + 부제(출처 · 상태), 크게 보기, 지우기(→ 확인), 멈추기(일하는 중·답 기다림일 때만)
function taskHead(s: State, t: Session, send: Send, go: Go, openBig: OpenBig, askDelete: () => void): HTMLElement {
  const v = s.view;
  const live = t.state === "working" || t.state === "waiting";
  return h("div", { class: "head" },
    h("button", { type: "button", class: "back", "aria-label": "목록으로", onClick: () => go({ tab: v.tab, screen: "list", page: v.page }) }, svg(BACK_ICON)),
    h("div", { class: "head-main" },
      h("span", { class: "head-title" }, t.title),
      h("span", { class: "head-sub" },
        h("span", { class: `src-${t.source}` }, SOURCE_TEXT[t.source]), " · ",
        h("span", { class: t.state === "waiting" ? "sub-ask" : "" }, STATE_TEXT[t.state]))),
    expandButton("icon-btn", () => openBig(v)),
    deleteButton("작업 지우기", askDelete),
    live ? h("button", { type: "button", class: "icon-btn", "aria-label": "작업 멈추기", onClick: () => send({ type: "stop", session_id: t.id }) }, svg(STOP_ICON)) : null);
}

// 대화 화면(작업 대화·스케줄 대화·대화 탭)이면 그 세션. 아직 모르면 undefined
export function conversationSession(s: State): Session | undefined {
  const v = s.view;
  if ((v.screen === "task" || v.screen === "schedule") && v.sessionId !== undefined) return s.sessions.get(v.sessionId);
  if (v.screen === "list" && v.tab === "chat" && s.chatSessionId !== null) return s.sessions.get(s.chatSessionId);
  return undefined;
}

// 대화 탭 머리 아래 얇은 줄(18): "Claude와 나눈 대화" + [대화 지우기](→ 확인)
export function chatStrip(askDelete: () => void): HTMLElement {
  return h("div", { class: "chat-strip" },
    h("span", { class: "chat-strip-title" }, "Claude와 나눈 대화"),
    h("button", { type: "button", class: "chat-clear", onClick: askDelete }, svg(trashIcon(13)), "대화 지우기"));
}

// --- 확인 상자: 지우기(19), 화면 기록 비우기(25). 같은 덮개·상자 ---
// 지우기(19): 패널 안 덮개 + alertdialog. 문구는 context "정한 값" ---
const DELETE_TEXT: Record<Session["source"], { title: string; body: (name: string) => (Node | string)[] }> = {
  user: { title: "이 작업을 지울까요?", body: (n) => [h("b", {}, n), "과 그 대화 기록이 모두 지워져요. 되돌릴 수 없어요. 돌고 있는 작업이면 먼저 멈춰요."] },
  schedule: { title: "이 스케줄을 지울까요?", body: (n) => [h("b", {}, n), "과 작업 지시서, 대화 기록이 모두 지워져요. 되돌릴 수 없어요. 돌고 있으면 먼저 멈춰요."] },
  chat: { title: "대화를 지울까요?", body: () => ["Claude와 나눈 대화 기록이 모두 지워지고 새 대화로 시작해요. 되돌릴 수 없어요."] },
};

// 열린 확인 상자. 연 화면(세션 대화, 또는 sessionId 없는 설정 탭)을 떠나면(다시 그릴 때) 닫는다
let confirming: { sessionId: number | undefined; el: HTMLElement } | null = null;

export type ConfirmSpec = { title: string; body: (Node | string)[]; action: string; run: () => unknown };

function closeConfirm(): void {
  confirming?.el.remove();
  confirming = null;
}

// 다시 그릴 때: 확인 상자를 연 세션의 대화 화면이 아니면 닫는다
export function deleteConfirm(root: HTMLElement, t: Session, name: string, send: Send): void {
  const text = DELETE_TEXT[t.source];
  openConfirm(root, t.id, {
    title: text.title, body: text.body(name), action: "지우기",
    run: () => send({ type: "delete_session", session_id: t.id }),
  });
}

export function syncConfirm(root: HTMLElement, sessionId: number | undefined): void {
  if (confirming && (confirming.sessionId !== sessionId || !root.contains(confirming.el))) closeConfirm();
}

// [취소]·Esc는 닫기. 실행 버튼은 run()을 부르고 닫는다. run()이 false를 돌려주면(못 보냄·끊김) 상자를 둔다
export function openConfirm(root: HTMLElement, sessionId: number | undefined, spec: ConfirmSpec): void {
  closeConfirm();
  const cancel = h("button", { type: "button", class: "btn-secondary", onClick: closeConfirm }, "취소");
  const run = () => { if (spec.run() !== false) closeConfirm(); };
  const el = h("div", { class: "confirm", onKeydown: (e) => { if ((e as KeyboardEvent).key === "Escape") closeConfirm(); } },
    h("div", { role: "alertdialog", "aria-modal": "true", "aria-labelledby": "deltitle", "aria-describedby": "deldesc", class: "confirm-box" },
      h("h2", { id: "deltitle" }, spec.title),
      h("p", { id: "deldesc" }, ...spec.body),
      h("div", { class: "confirm-buttons" },
        cancel,
        h("button", { type: "button", class: "btn-danger", onClick: run }, spec.action))));
  root.append(el);
  confirming = { sessionId, el };
  cancel.focus();
}

// 양식 화면(새 작업·새 스케줄·지시서 수정·설정 탭의 Jev 키)을 다시 그릴지 정하는 열쇠. 양식이 아니면 ""
// 설정 탭은 그 화면에 보이는 값(연결·로그인·설정·탭 바 작은 배지)이 바뀔 때만 다시 그린다
export function formKey(s: State): string {
  const v = s.view;
  const b = badges(s);
  return v.screen === "newTask" ? `newTask|${s.connected}`
    : v.screen === "newSchedule" || v.screen === "editSchedule" ? `form|${v.screen}|${v.sessionId ?? ""}|${s.connected}|${formReady(s)}`
    : v.screen === "list" && v.tab === "settings"
      ? `settings|${s.connected}|${s.loggedIn}|${s.loggingIn}|${JSON.stringify(s.settings)}|${b.red},${b.yellow},${b.green}`
    : "";
}

export function renderPanel(root: HTMLElement, state: State, send: Send, go: Go, openBig: OpenBig): void {
  const conn = state.connected ? [] : [h("div", { class: "conn" }, "백엔드에 연결하는 중…")];
  const tail = () => h("div", { class: "tail", "aria-hidden": "true" });
  const v = state.view;
  root.classList.toggle("panel-task", v.screen === "task");
  root.classList.toggle("panel-schedule", v.screen === "schedule");

  // 대화 화면: 입력줄을 지키려고 대화 자리는 그대로 두고 위(연결 띠·탭 바·머리)만 바꾼다
  const t = conversationSession(state);
  syncConfirm(root, t?.id);
  if (t) {
    const isChat = v.screen === "list";
    const key = `conv|${t.id}|${v.screen}`;
    if (root.dataset.key !== key) {
      root.dataset.key = key;
      root.replaceChildren(h("div", { class: "slot" }), h("div", { class: "conv-host" }), tail());
    }
    const name = (v.screen === "schedule" && state.schedules.get(t.id)?.name) || t.title;
    const askDelete = () => deleteConfirm(root, t, name, send);
    const top = isChat ? [tabBar(state, go, openBig), chatStrip(askDelete)]
      : v.screen === "schedule" ? scheduleHead(state, t, send, go, openBig, askDelete) : [taskHead(state, t, send, go, openBig, askDelete)];
    root.querySelector(".slot")!.replaceChildren(...conn, ...top);
    renderConversation(root.querySelector(".conv-host") as HTMLElement, {
      session: t, entries: state.entries.get(t.id) ?? NO_ENTRIES, activity: state.activity.get(t.id), height: isChat ? 324 : 0, compact: true,
    }, send, go);
    return;
  }

  // 양식 화면(새 작업·새 스케줄·지시서 수정)은 입력 중에 다시 그리지 않는다(한글 조합·커서가 깨진다).
  // 연결이 바뀔 때, 지시서 수정은 채울 스케줄이 올 때만 다시 그린다
  const key = formKey(state);
  if (key && root.dataset.key === key) return;
  root.dataset.key = key;
  root.replaceChildren(...conn, ...body(state, send, go, openBig), tail());
}
