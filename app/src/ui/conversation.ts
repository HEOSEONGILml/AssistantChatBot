// 대화 화면: 줄 목록과 입력줄. 작업 대화(11)·대화 탭(18)·큰 창(12)이 같이 쓴다. 값은 다이제스트 2~4절.
// 같은 세션을 다시 그릴 때는 입력줄을 그대로 두고(글·커서 보호) 줄 목록만 바꾼다.
// 맨 아래 준비 중 줄(22)은 걸린 시간만 1초마다 바꾼다(대화 전체를 다시 그리지 않는다).
import type { Entry, Outgoing, Session } from "../shared/protocol";
import { elapsedText, type Activity, type View } from "../shared/state";
import { answered, answerKey, chipTarget, TAB_OF, toItems, type Item } from "../shared/entries";
import { clockText, dateTimeText, isSendKey } from "../shared/forms";
import { h, markdown, svg } from "./dom";

type Send = (m: Outgoing) => unknown; // false를 돌려주면 못 보낸 것(입력 글을 지우지 않는다)
type Go = (v: View) => void;
// compact: 패널(13px, 진행 줄 접기). 아니면 큰 창(14px, 진행 줄 펼침, 날짜 줄)
// height: 줄 목록 높이(px). 0이면 대화 화면이 부모 높이를 채운다
// activity: 그 세션이 지금 하는 일. 있으면 맨 아래 준비 중 줄을 그린다
export type ConversationOpts = { session: Session; entries: Entry[]; activity?: Activity; height: number; compact: boolean };

const PLACEHOLDER: Record<Session["source"], string> = { user: "답하거나 되묻기", schedule: "이 스케줄에 말하기", chat: "Claude에게 말하기" };

const ICON = {
  check: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="10" fill="#E3F4EA"/><path d="M7.5 12.5l3 3 6-6.5" stroke="#15803D" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  spin: `<svg class="spin" width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="#D5DAE1" stroke-width="3"/><path d="M21 12a9 9 0 0 0-9-9" stroke="#1D4ED8" stroke-width="3" stroke-linecap="round"/></svg>`,
  down: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>`,
  up: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 15l6-6 6 6"/></svg>`,
  warn: `<svg class="warn" width="16" height="16" viewBox="0 0 24 24" fill="none" role="img" aria-label="못 함"><circle cx="12" cy="12" r="10" fill="#FEF3C7"/><path d="M12 7v6" stroke="#B45309" stroke-width="2.4" stroke-linecap="round"/><circle cx="12" cy="16.5" r="1.4" fill="#B45309"/></svg>`,
  send: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14"/><path d="M13 6l6 6-6 6"/></svg>`,
};

type Ctl = {
  sessionId: number; compact: boolean; log: HTMLElement; area: HTMLTextAreaElement;
  expanded: Set<number>; // 펼친 진행 묶음(첫 줄 id)
  opts: ConversationOpts; send: Send; go: Go;
  drawn?: [Session, Entry[], boolean]; // 그린 세션·줄·준비 중 줄 여부
  status?: { li: HTMLElement; text: HTMLElement; time: HTMLElement; timer: number }; // 준비 중 줄
};
const ctls = new WeakMap<HTMLElement, Ctl>();

export function renderConversation(root: HTMLElement, opts: ConversationOpts, send: Send, go: Go): void {
  let c = ctls.get(root);
  if (!c || c.sessionId !== opts.session.id || c.compact !== opts.compact || !root.contains(c.log)) {
    c = build(root, opts, send, go);
    ctls.set(root, c);
  }
  c.opts = opts; c.send = send; c.go = go;
  syncStatus(c);
  const busy = !!opts.activity;
  if (c.drawn && c.drawn[0] === opts.session && c.drawn[1] === opts.entries && c.drawn[2] === busy) return;
  c.drawn = [opts.session, opts.entries, busy];
  drawLog(c);
}

// 준비 중 줄(22): 점 3개 + 굵은 하는 일 + "· <걸린 시간>". 줄을 만들고 글을 맞춘다. 하는 일이 없으면 줄과 시계를 치운다.
// 줄을 목록에 넣고 빼는 것은 drawLog가 한다(준비 중 줄 여부가 바뀌면 다시 그린다)
function syncStatus(c: Ctl): void {
  const a = c.opts.activity;
  if (!a) { stopStatus(c); return; }
  if (!c.status) {
    const text = h("b", {});
    const time = h("span", { class: "status-time" });
    const li = h("li", { class: "status-line", role: "status", "aria-live": "polite" },
      h("span", { class: "status-dots", "aria-hidden": "true" }, h("span"), h("span"), h("span")),
      h("span", {}, text, " ", time));
    c.status = { li, text, time, timer: window.setInterval(() => tick(c), 1000) };
  }
  c.status.text.textContent = a.text;
  tick(c);
}

// 걸린 시간 글만 바꾼다. 대화 화면이 사라졌으면(다른 세션으로 바뀜·패널 닫힘) 시계를 멈춘다
function tick(c: Ctl): void {
  const a = c.opts.activity;
  if (!a || !c.log.isConnected) { stopStatus(c); return; }
  c.status!.time.textContent = `· ${elapsedText(Date.now() - a.since)}`;
}

function stopStatus(c: Ctl): void {
  if (!c.status) return;
  window.clearInterval(c.status.timer);
  c.status.li.remove();
  c.status = undefined;
}

function build(root: HTMLElement, opts: ConversationOpts, send: Send, go: Go): Ctl {
  const [min, max] = opts.compact ? [40, 120] : [44, 140];
  const log = h("div", {
    class: "conv-log", tabindex: 0, "aria-label": "대화 기록",
    style: opts.height > 0 ? `flex: none; height: ${opts.height}px` : null,
  });
  const placeholder = PLACEHOLDER[opts.session.source];
  const area = h("textarea", { id: `msg-${opts.session.id}`, class: "conv-input", rows: 1, placeholder }) as HTMLTextAreaElement;
  // 한 줄 40px에서 120px까지(큰 창은 44px에서 140px까지) 늘어난다
  const grow = () => {
    area.style.height = "auto";
    area.style.height = `${Math.min(Math.max(area.scrollHeight + 2, min), max)}px`;
  };
  const c: Ctl = { sessionId: opts.session.id, compact: opts.compact, log, area, expanded: new Set(), opts, send, go };
  const submit = (e: Event) => {
    e.preventDefault();
    const text = area.value.trim();
    if (!text) return;
    if (c.send({ type: "say", session_id: c.opts.session.id, text }) === false) return;
    area.value = "";
    grow();
    area.focus();
  };
  area.addEventListener("input", grow);
  area.addEventListener("keydown", (e) => { if (isSendKey(e)) submit(e); });
  const form = h("form", { class: "conv-form", onSubmit: submit },
    h("label", { for: area.id, class: "sr-only" }, placeholder),
    h("div", { class: "conv-form-inner" }, area,
      h("button", { type: "submit", class: "conv-send", "aria-label": "보내기" }, svg(ICON.send))));
  root.replaceChildren(h("div", { class: opts.compact ? "conv" : "conv conv-big" }, log, form));
  return c;
}

// 줄 목록을 다시 그린다. 사용자가 둔 스크롤 자리를 지키고, 맨 아래에 있었을 때만 새 줄을 따라 내려간다
function drawLog(c: Ctl): void {
  const { log } = c;
  const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 8;
  const top = log.scrollTop;
  const { session, entries } = c.opts;
  const items = toItems(entries, session.state, session.source, !!c.status);
  const key = answerKey(session, entries);
  log.replaceChildren(h("ol", { class: "conv-list" },
    ...(c.compact ? [] : [h("li", { class: "run-line" }, dateTimeText(session.created_at))]),
    ...items.map((it) => itemEl(c, it, key)),
    c.status?.li));
  log.scrollTop = atBottom ? log.scrollHeight : top;
}

const bubble = (cls: string, ...children: (Node | string)[]) => h("li", { class: `msg ${cls}` }, ...children);

function itemEl(c: Ctl, it: Item, key: string): HTMLElement {
  switch (it.kind) {
    case "user": return bubble("msg-user", it.text);
    case "agent": return bubble("msg-agent msg-md", markdown(it.text));
    case "failure": return bubble("msg-agent msg-failure msg-md", svg(ICON.warn), markdown(it.text));
    case "run": return h("li", { class: "run-line" }, it.text);
    case "progress": return progress(c, it);
    case "question":
      if (!it.answerable || !it.choices?.length) return bubble("msg-agent msg-md", markdown(it.text));
      return h("li", { class: "msg msg-card msg-md" }, markdown(it.text),
        choiceRow(it.choices, key, (choice) => say(c, choice)));
    case "proposal": return proposal(c, it, key);
    case "chip": return chip(c, it);
  }
}

const say = (c: Ctl, text: string) => c.send({ type: "say", session_id: c.opts.session.id, text });

// 선택지 버튼 줄. 첫 버튼이 주 버튼. 답을 보내는 버튼은 보내기에 성공하면 막는다(pick이 false면 못 보낸 것)
function choiceRow(choices: string[], key: string, pick: (choice: string) => unknown, answers = (_: string) => true): HTMLElement {
  const done = answered.has(key);
  const row = h("div", { class: "choices" });
  for (const [i, choice] of choices.entries()) {
    row.append(h("button", {
      type: "button", class: i === 0 ? "choice choice-primary" : "choice", disabled: done,
      onClick: () => {
        if (pick(choice) === false || !answers(choice)) return;
        answered.add(key);
        for (const b of row.querySelectorAll("button")) b.disabled = true;
      },
    }, choice));
  }
  return row;
}

// 등록 확인: [등록] → say("등록"), [고치기] → 지시서 수정 화면을 이 확인의 data로 연다
function proposal(c: Ctl, it: Item, key: string): HTMLElement {
  const d = (it.data ?? {}) as Record<string, unknown>;
  const name = typeof d.name === "string" ? d.name : it.text;
  const label = typeof d.label === "string" ? `${d.label} · 스케줄` : "스케줄";
  const session = c.opts.session;
  const edit = () => c.go({ tab: TAB_OF[session.source], screen: "editSchedule", sessionId: session.id, page: 1, proposal: d });
  return h("li", { class: it.answerable ? "msg msg-card msg-proposal" : "msg msg-card msg-proposal msg-closed" },
    h("span", { class: "proposal-title" }, "이렇게 등록할까요?"),
    h("span", {}, h("b", {}, name), h("br"), h("span", { class: "proposal-label" }, label)),
    ...(it.answerable && it.choices?.length
      ? [choiceRow(it.choices, key, (ch) => (ch === "고치기" ? edit() : say(c, ch)), (ch) => ch !== "고치기")]
      : []));
}

// 세션 칩: 이 대화에서 만든 세션. 누르면 그 세션 대화로
function chip(c: Ctl, it: Item): HTMLElement {
  const target = chipTarget(it.data, c.opts.session.source);
  const open = () => { if (target) c.go(target.view); };
  return h("li", {},
    h("button", { type: "button", class: "chip", onClick: open },
      h("span", { class: "chip-kind" }, target?.label ?? "작업"), h("b", {}, it.text), h("span", { class: "chip-go", "aria-hidden": "true" }, "›")));
}

// 진행 묶음: 패널에서는 한 줄 칩(누르면 펼침), 큰 창에서는 늘 펼친 박스
function progress(c: Ctl, it: Item): HTMLElement {
  const first = it.entries[0].id;
  const toggle = () => {
    if (c.expanded.has(first)) c.expanded.delete(first); else c.expanded.add(first);
    drawLog(c);
  };
  const icon = svg(it.spinning ? ICON.spin : ICON.check);
  if (c.compact && !c.expanded.has(first)) {
    return h("li", {}, h("button", { type: "button", class: "prog-chip", "aria-expanded": "false", onClick: toggle },
      icon, h("span", { class: "prog-text" }, it.text), svg(ICON.down)));
  }
  const title = `진행 ${it.entries.length}단계`;
  const head = c.compact
    ? h("button", { type: "button", class: "prog-head", "aria-expanded": "true", onClick: toggle }, icon, title, svg(ICON.up))
    : h("span", { class: "prog-head" }, ...(it.spinning ? [icon] : []), title);
  return h("li", { class: "prog-box" }, head,
    ...it.entries.map((e) => h("span", {}, h("span", { class: "prog-time" }, clockText(e.at)), " ", e.text)));
}
