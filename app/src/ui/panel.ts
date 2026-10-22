// 패널 틀: 연결 띠, 탭 바, 탭별 본문, 새 작업 화면, 꼬리. 값은 다이제스트 2절, 3절 6·7·8번.
import type { Outgoing } from "../shared/protocol";
import type { State, Tab, View } from "../shared/state";
import { isSendKey } from "../shared/forms";
import { h, svg } from "./dom";
import { alertsBody, miniBadges, tasksBody } from "./lists";

type Send = (m: Outgoing) => void;
type Go = (v: View) => void;

const USAGE_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3v18h18"/><path d="M8 16v-3"/><path d="M13 16V9"/><path d="M18 16V6"/></svg>`;
const SETTINGS_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`;
const BACK_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>`;

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

function header(title: string, backLabel: string, back: () => void): HTMLElement {
  return h("div", { class: "head" },
    h("button", { type: "button", class: "back", "aria-label": backLabel, onClick: back }, svg(BACK_ICON)),
    h("span", { class: "head-title" }, title));
}

const placeholder = () => h("div", { class: "placeholder" }, "준비 중");

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
  if (v.screen !== "list") {
    // 작업 대화·스케줄 화면은 다음 Task에서 채운다
    const title = (v.taskId !== undefined && s.tasks.get(v.taskId)?.title) || "";
    return [header(title, "목록으로", () => go({ tab: v.tab, screen: "list", page: v.page })), placeholder()];
  }
  const content = v.tab === "alerts" ? alertsBody(s, send, go) : v.tab === "tasks" ? tasksBody(s, send, go) : [placeholder()];
  return [tabBar(s, go), ...content];
}

export function renderPanel(root: HTMLElement, state: State, send: Send, go: Go): void {
  // 새 작업 화면은 입력 중에 다시 그리지 않는다(한글 조합·커서가 깨진다). 연결이 바뀔 때만 다시 그린다
  const key = state.view.screen === "newTask" ? `newTask|${state.connected}` : "";
  if (key && root.dataset.key === key) return;
  root.dataset.key = key;
  root.replaceChildren(
    ...(state.connected ? [] : [h("div", { class: "conn" }, "백엔드에 연결하는 중…")]),
    ...body(state, send, go),
    h("div", { class: "tail", "aria-hidden": "true" }),
  );
}
