// 큰 창(12): 패널 전체를 넓게 그린다. 값은 다이제스트 2절 "큰 창(12번)", 3절 12·19번·지우기 버튼 위치, 4절의 큰 창 값.
// 알림·작업·스케줄 탭은 두 칸(왼쪽 300px 목록, 오른쪽 고른 대화 또는 양식), 대화·사용량·설정은 한 칸(context "정한 값").
// 패널의 목록·양식·대화·지우기 확인을 그대로 쓰고, 탭 바와 오른쪽 대화 머리만 큰 창 모양이다.
import type { Entry, Outgoing, Session } from "../shared/protocol";
import { STATE_TEXT, TWO_COLUMN, type State, type Tab, type View } from "../shared/state";
import { clockText } from "../shared/forms";
import { h, svg, switchButton, trashIcon } from "./dom";
import { renderConversation } from "./conversation";
import { ICON, alertsBody, miniBadges, tasksBody } from "./lists";
import { SOURCE_TEXT, chatStrip, conversationSession, formKey, newTask, openConfirm, syncConfirm } from "./panel";
import { instructionRow, scheduleForm, schedulesBody } from "./schedule";
import { settingsBody } from "./settings";
import { usageBody } from "./usage";

type Send = (m: Outgoing) => unknown;
type Go = (v: View) => void;

const NO_ENTRIES: Entry[] = []; // 줄을 아직 모를 때도 같은 배열(대화 화면이 참조 비교로 다시 그리지 않게)
const TABS: [Tab, string][] = [["alerts", "알림"], ["chat", "대화"], ["tasks", "작업"], ["schedules", "스케줄"], ["usage", "사용량"], ["settings", "설정"]];

// 탭 바: 글자 탭 6개. 크게 보기는 없다
function tabBar(s: State, go: Go): HTMLElement {
  return h("div", { role: "tablist", "aria-label": "보기", class: "big-tabs" },
    ...TABS.map(([tab, label]) => h("button", {
      type: "button", role: "tab", class: "tab", "aria-selected": String(s.view.tab === tab),
      onClick: () => go({ tab, screen: "list", page: 1 }),
    }, label, ...(tab === "alerts" ? miniBadges(s) : []))));
}

// 오른쪽 대화 머리: 제목 16px/700 + 부제, (스케줄이면 켜짐 스위치), [지우기], [멈추기](일하는 중·답 기다림일 때만)
function head(s: State, t: Session, send: Send, go: Go, askDelete: () => void): Node[] {
  const sc = t.source === "schedule" ? s.schedules.get(t.id) : undefined;
  const live = t.state === "working" || t.state === "waiting";
  const sub = t.source === "schedule"
    ? [h("span", { class: "src-schedule" }, SOURCE_TEXT.schedule)]
    : [h("span", { class: `src-${t.source}` }, SOURCE_TEXT[t.source]), ` · ${clockText(t.created_at)} 시작 · `,
      h("span", { class: t.state === "waiting" ? "sub-ask" : "" }, STATE_TEXT[t.state])];
  const el = h("div", { class: "big-head" },
    h("div", { class: "big-head-main" }, h("span", { class: "big-title" }, sc?.name ?? t.title), h("span", { class: "big-sub" }, ...sub)),
    sc ? switchButton({ on: sc.enabled, label: "스케줄", disabled: !s.connected, onToggle: () => send({ type: "set_schedule_enabled", session_id: t.id, enabled: !sc.enabled }) }) : null,
    h("button", { type: "button", class: "big-btn", onClick: askDelete }, svg(trashIcon(13)), "지우기"),
    live ? h("button", { type: "button", class: "big-btn big-stop", onClick: () => send({ type: "stop", session_id: t.id }) }, svg(ICON.stop), "멈추기") : null);
  return sc ? [el, instructionRow(sc, s.view, go)] : [el];
}

function listBody(s: State, send: Send, go: Go): Node[] {
  const tab = s.view.tab;
  return tab === "alerts" ? alertsBody(s, send, go) : tab === "tasks" ? tasksBody(s, send, go) : schedulesBody(s, go);
}

type Parts = { top: HTMLElement; left: HTMLElement; head: HTMLElement; content: HTMLElement };
const built = new WeakMap<HTMLElement, Parts>();

function parts(root: HTMLElement): Parts {
  let p = built.get(root);
  if (!p) {
    p = { top: h("div", { class: "big-top" }), left: h("div", { class: "big-list" }), head: h("div", { class: "slot" }), content: h("div", { class: "big-content" }) };
    root.replaceChildren(p.top, h("div", { class: "big-main" }, p.left, h("div", { class: "big-right" }, p.head, p.content)));
    built.set(root, p);
  }
  return p;
}

// 오른쪽(한 칸이면 본문) 칸을 열쇠가 바뀔 때만 새로 채운다. 대화 입력줄·양식 입력을 지킨다
function setContent(content: HTMLElement, key: string, fill: () => Node[]): void {
  if (key && content.dataset.key === key) return;
  content.dataset.key = key;
  content.replaceChildren(...fill());
}

export function renderBig(root: HTMLElement, s: State, send: Send, go: Go): void {
  const { top, left, head: headSlot, content } = parts(root);
  const v = s.view;
  const two = TWO_COLUMN.has(v.tab);
  const t = conversationSession(s);
  syncConfirm(root, t?.id);
  const name = t && ((t.source === "schedule" && s.schedules.get(t.id)?.name) || t.title);
  const askDelete = () => { if (t) openConfirm(root, t, name!, send); };

  const conn = s.connected ? [] : [h("div", { class: "conn" }, "백엔드에 연결하는 중…")];
  const isChat = !!t && v.screen === "list"; // 대화 탭의 대화(그 밖은 작업·스케줄 대화)
  top.replaceChildren(...conn, tabBar(s, go), ...(isChat ? [chatStrip(askDelete)] : []));
  left.hidden = !two;
  left.replaceChildren(...(two ? listBody(s, send, go) : []));

  if (t) {
    headSlot.replaceChildren(...(isChat ? [] : head(s, t, send, go, askDelete)));
    setContent(content, `conv|${t.id}|${v.screen}`, () => []);
    renderConversation(content, {
      session: t, entries: s.entries.get(t.id) ?? NO_ENTRIES, activity: s.activity.get(t.id), height: 0, compact: false,
    }, send, go);
    return;
  }
  headSlot.replaceChildren();
  const fk = formKey(s);
  if (fk) { setContent(content, fk, () => (v.screen === "newTask" ? newTask(s, send, go) : scheduleForm(s, send, go))); return; }
  // 대화 화면인데 세션을 아직 모르면 "불러오는 중", 두 칸 목록이면 고르라는 글, 한 칸 탭이면 그 본문
  const loading = v.screen !== "list" || v.tab === "chat";
  setContent(content, "", () => loading ? [h("p", { class: "empty" }, "불러오는 중…")]
    : two ? [h("p", { class: "big-none" }, "왼쪽 목록에서 골라 주세요")]
    : v.tab === "usage" ? usageBody(s)
    : settingsBody(s, send));
}
