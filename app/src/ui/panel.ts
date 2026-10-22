// 패널 틀: 연결 띠, 탭 바, 탭별 본문, 새 작업 화면, 대화 화면, 꼬리. 값은 다이제스트 2절, 3절 6·7·8·16번.
import type { Entry, Outgoing, Task } from "../shared/protocol";
import { STATE_TEXT, type State, type Tab, type View } from "../shared/state";
import { isSendKey } from "../shared/forms";
import { BACK_ICON, EXPAND_ICON, h, header, svg } from "./dom";
import { renderConversation } from "./conversation";
import { alertsBody, miniBadges, tasksBody } from "./lists";
import { settingsBody } from "./settings";
import { usageBody } from "./usage";
import { formReady, scheduleForm, scheduleHead, schedulesBody } from "./schedule";

type Send = (m: Outgoing) => unknown;
type Go = (v: View) => void;

const USAGE_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3v18h18"/><path d="M8 16v-3"/><path d="M13 16V9"/><path d="M18 16V6"/></svg>`;
const SETTINGS_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`;
const STOP_ICON = `<svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2" fill="#B42318"/></svg>`;

const TEXT_TABS: [Tab, string][] = [["alerts", "알림"], ["chat", "대화"], ["tasks", "작업"], ["schedules", "스케줄"]];
const ICON_TABS: [Tab, string, string][] = [["usage", "사용량", USAGE_ICON], ["settings", "설정", SETTINGS_ICON]];

let draft = ""; // 새 작업 입력 글. 다시 그려도 남는다

function tabBar(s: State, go: Go): HTMLElement {
  const open = (tab: Tab) => () => go({ tab, screen: "list", page: 1 });
  const sel = (tab: Tab) => s.view.tab === tab;
  return h("div", { class: "tabbar" },
    h("div", { role: "tablist", "aria-label": "보기", class: "tabs" },
      ...TEXT_TABS.map(([tab, label]) => h("button", {
        type: "button", role: "tab", class: "tab", "aria-selected": String(sel(tab)), onClick: open(tab),
      }, label, ...(tab === "alerts" ? [" ", ...miniBadges(s)] : []))),
      ...ICON_TABS.map(([tab, label, icon]) => h("button", {
        type: "button", role: "tab", class: "tab tab-icon", "aria-label": label, "aria-selected": String(sel(tab)), onClick: open(tab),
      }, svg(icon)))));
}

const loading = () => h("p", { class: "empty" }, "불러오는 중…");

// 새 작업 화면(6 Input): [취소]·뒤로 → 작업 탭, [맡기기]·Enter → request 후 작업 탭
function newTask(s: State, send: Send, go: Go): Node[] {
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
    send({ type: "request", text });
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

function body(s: State, send: Send, go: Go): Node[] {
  const v = s.view;
  if (v.screen === "newTask") return newTask(s, send, go);
  if (v.screen === "newSchedule" || v.screen === "editSchedule") return scheduleForm(s, send, go);
  if (v.screen !== "list") {
    // 작업 대화·스케줄 대화는 작업을 받기 전까지 "불러오는 중"
    const title = (v.taskId !== undefined && s.tasks.get(v.taskId)?.title) || "";
    const backLabel = v.screen === "schedule" ? "스케줄 목록으로" : "목록으로";
    return [header(title, backLabel, () => go({ tab: v.tab, screen: "list", page: v.page })), loading()];
  }
  const content = v.tab === "alerts" ? alertsBody(s, send, go)
    : v.tab === "tasks" ? tasksBody(s, send, go)
    : v.tab === "chat" ? [loading()] // 대화 작업을 아직 모를 때
    : v.tab === "schedules" ? schedulesBody(s, go)
    : v.tab === "usage" ? usageBody(s)
    : settingsBody(s, send);
  return [tabBar(s, go), ...content];
}

const SOURCE_TEXT: Record<Task["source"], string> = { user: "내 요청", schedule: "스케줄", chat: "대화" };
const NO_ENTRIES: Entry[] = [];

// 작업 대화 머리(11): 뒤로, 제목 + 부제(출처 · 상태), 창으로 크게 보기, 멈추기(일하는 중·답 기다림일 때만)
function taskHead(s: State, t: Task, send: Send, go: Go, openDetail: (id: number) => void): HTMLElement {
  const v = s.view;
  const live = t.state === "working" || t.state === "waiting";
  return h("div", { class: "head" },
    h("button", { type: "button", class: "back", "aria-label": "목록으로", onClick: () => go({ tab: v.tab, screen: "list", page: v.page }) }, svg(BACK_ICON)),
    h("div", { class: "head-main" },
      h("span", { class: "head-title" }, t.title),
      h("span", { class: "head-sub" },
        h("span", { class: `src-${t.source}` }, SOURCE_TEXT[t.source]), " · ",
        h("span", { class: t.state === "waiting" ? "sub-ask" : "" }, STATE_TEXT[t.state]))),
    h("button", { type: "button", class: "icon-btn", "aria-label": "창으로 크게 보기", onClick: () => openDetail(t.id) }, svg(EXPAND_ICON)),
    live ? h("button", { type: "button", class: "icon-btn", "aria-label": "작업 멈추기", onClick: () => send({ type: "stop", task_id: t.id }) }, svg(STOP_ICON)) : null);
}

// 대화 화면(작업 대화·스케줄 대화·대화 탭)이면 그 작업. 아직 모르면 undefined
function conversationTask(s: State): Task | undefined {
  const v = s.view;
  if ((v.screen === "task" || v.screen === "schedule") && v.taskId !== undefined) return s.tasks.get(v.taskId);
  if (v.screen === "list" && v.tab === "chat" && s.chatTaskId !== null) return s.tasks.get(s.chatTaskId);
  return undefined;
}

export function renderPanel(root: HTMLElement, state: State, send: Send, go: Go, openDetail: (id: number) => void): void {
  const conn = state.connected ? [] : [h("div", { class: "conn" }, "백엔드에 연결하는 중…")];
  const tail = () => h("div", { class: "tail", "aria-hidden": "true" });
  const v = state.view;
  root.classList.toggle("panel-task", v.screen === "task");
  root.classList.toggle("panel-schedule", v.screen === "schedule");

  // 대화 화면: 입력줄을 지키려고 대화 자리는 그대로 두고 위(연결 띠·탭 바·머리)만 바꾼다
  const t = conversationTask(state);
  if (t) {
    const isChat = v.screen === "list";
    const key = `conv|${t.id}|${v.screen}`;
    if (root.dataset.key !== key) {
      root.dataset.key = key;
      root.replaceChildren(h("div", { class: "slot" }), h("div", { class: "conv-host" }), tail());
    }
    const top = isChat ? [tabBar(state, go)]
      : v.screen === "schedule" ? scheduleHead(state, t, send, go, openDetail) : [taskHead(state, t, send, go, openDetail)];
    root.querySelector(".slot")!.replaceChildren(...conn, ...top);
    renderConversation(root.querySelector(".conv-host") as HTMLElement,
      { task: t, entries: state.entries.get(t.id) ?? NO_ENTRIES, height: isChat ? 360 : 0, compact: true }, send, go);
    return;
  }

  // 양식 화면(새 작업·새 스케줄·지시서 수정)은 입력 중에 다시 그리지 않는다(한글 조합·커서가 깨진다).
  // 연결이 바뀔 때, 지시서 수정은 채울 스케줄이 올 때만 다시 그린다
  const key = v.screen === "newTask" ? `newTask|${state.connected}`
    : v.screen === "newSchedule" || v.screen === "editSchedule" ? `form|${v.screen}|${v.taskId ?? ""}|${state.connected}|${formReady(state)}`
    : "";
  if (key && root.dataset.key === key) return;
  root.dataset.key = key;
  root.replaceChildren(...conn, ...body(state, send, go), tail());
}
