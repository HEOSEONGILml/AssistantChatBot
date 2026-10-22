// 주 창: 강아지와 패널. 백엔드 메시지를 상태에 쌓고 다시 그린다.
// 큰 창이 보이는 동안 큰 창 몫의 상태(따로 고른 화면)도 들고, 바뀌면 통째로 넘긴다. 큰 창이 보낸 메시지는 대신 보낸다.
import "./ui/styles.css";
import { emitTo, listen } from "@tauri-apps/api/event";
import { connectBackend } from "./backend-link";
import { answered, pruneAnswered } from "./shared/entries";
import type { Outgoing } from "./shared/protocol";
import {
  apply, bigFollowUps, bigRequests, disconnected, firstWaiting, followUps, initialState, mergeRequests, needsSeen, pendingQuestion,
  refreshRequests, toSnapshot, type State, type View,
} from "./shared/state";
import { bindDogDrag, renderDog } from "./ui/dog";
import { renderPanel } from "./ui/panel";
import { clearDraft } from "./ui/schedule";
import { beginDrag, dragBy, endDrag, onPlaced, placeWindow, showBig } from "./window";

const PANEL_WIDTH = 340;

const dogRoot = document.getElementById("dog")!;
const panelRoot = document.getElementById("panel")!;

let state: State = initialState();
let big: State | null = null; // 큰 창 몫 상태: 데이터는 state와 같고 화면(view)만 따로다. 큰 창이 보이는 동안만 있다
const asked = new Set<number>(); // 질문 카드용으로 get_session을 이미 보낸 세션
const seenSent = new Set<number>(); // seen을 보내고 답을 기다리는 세션

// 백엔드에서 온 변화는 두 상태에 똑같이 준다(apply가 보던 화면에 따라 목록 쪽을 고르므로 상태를 둘 둔다)
function update(f: (s: State) => State) {
  state = f(state);
  if (big) big = f(big);
}

const chatShown = (s: State) => s.view.tab === "chat" && s.view.screen === "list";

const backend = connectBackend({
  onMessage: (m) => {
    update((s) => apply(s, m));
    pruneAnswered(answered, (id) => state.sessions.get(id)?.state === "waiting");
    for (const out of mergeRequests(followUps(state, m), big ? bigFollowUps(big, m) : [])) backend.send(out);
    // 대화 탭을 연 채 붙으면 대화 세션을 나중에 알게 된다: 그때 대화를 받아 온다
    if (m.type === "session" && m.session.source === "chat" && !state.entries.has(m.session.id)
      && ((state.panelOpen && chatShown(state)) || (big && chatShown(big)))) backend.send({ type: "get_session", session_id: m.session.id });
    render();
  },
  onOpen: () => {
    for (const out of mergeRequests(refreshRequests(state), big ? bigRequests(big) : [])) backend.send(out);
  },
  onClose: () => { update(disconnected); asked.clear(); seenSent.clear(); answered.clear(); render(); },
});
const send = (m: Outgoing): boolean => {
  const ok = backend.send(m);
  // [로그인]을 누르면 status가 올 때까지 버튼을 막는다
  if (ok && m.type === "login") { update((s) => ({ ...s, loggingIn: true })); render(); }
  return ok;
};

// 화면을 바꾸고 그 화면에 필요한 목록을 요청한다
function go(view: View) {
  if (view.proposal) clearDraft(); // [고치기]로 여는 수정 화면은 남은 적던 값 없이 등록 확인 값으로 채운다
  state = { ...state, view };
  for (const out of refreshRequests(state)) send(out);
  render();
}

function togglePanel() {
  const panelOpen = !state.panelOpen;
  // 로그아웃이면 패널을 열 때 설정 탭부터 보인다
  const view = panelOpen && state.loggedIn === false ? { tab: "settings" as const, screen: "list" as const, page: 1 } : state.view;
  state = { ...state, panelOpen, view };
  if (panelOpen) for (const out of refreshRequests(state)) send(out);
  render();
}

// 강아지 누르기. 먼저 말 걸기 배지(23번)가 떠 있으면 패널을 대화 탭으로 열고 nudge_open(큰 창이 떠 있어도 같다)
function dogClick() {
  if (!state.nudge || state.loggedIn === false) { togglePanel(); return; }
  state = { ...state, panelOpen: true, view: { tab: "chat", screen: "list", page: 1 } };
  for (const out of refreshRequests(state)) send(out);
  send({ type: "nudge_open" });
  render();
}

// 알림 탭의 질문 카드: 그 세션의 질문 줄이 캐시에 없으면 한 번 받아 온다. 패널과 큰 창(알림 탭이면 왼쪽에 늘 목록)
function fetchCardQuestion() {
  for (const id of asked) if (state.sessions.get(id)?.state !== "waiting") asked.delete(id);
  const shown = [
    state.panelOpen && state.view.tab === "alerts" && state.view.screen === "list" ? state : null,
    big?.view.tab === "alerts" ? big : null,
  ];
  for (const s of shown) {
    const t = s && firstWaiting(s);
    if (t && !pendingQuestion(s, t.id) && !asked.has(t.id)) {
      asked.add(t.id);
      send({ type: "get_session", session_id: t.id });
    }
  }
}

// 열어 본 세션이 끝났고 안 봤으면 seen. 답(seen: true)이 올 때까지 다시 보내지 않는다
function markSeen(id: number) {
  if (!needsSeen(state, id) || seenSent.has(id)) return;
  if (send({ type: "seen", session_id: id })) seenSent.add(id);
}
function markShownSeen() {
  for (const id of seenSent) if (!needsSeen(state, id)) seenSent.delete(id);
  const v = state.view;
  if (state.panelOpen && (v.screen === "task" || v.screen === "schedule") && v.sessionId !== undefined) markSeen(v.sessionId);
}

// --- 큰 창 ---
let bigSent: State | null = null; // 마지막으로 넘긴 상태. 같으면 다시 넘기지 않는다

function pushBig(force = false) {
  if (!big || (!force && big === bigSent)) return;
  bigSent = big;
  emitTo("big", "big-state", toSnapshot(big)).catch((e) => console.warn("큰 창 보내기 실패", e));
}

function goBig(view: View) {
  if (!big) return;
  big = { ...big, view };
  for (const out of bigRequests(big)) send(out);
  render();
}

// 크게 보기(탭 바·작업 대화·스케줄 대화 머리): 작은 패널을 닫고, 패널이 보던 화면 그대로 큰 창을 보인다
function openBig(v: View) {
  big = { ...state, view: v };
  state = { ...state, panelOpen: false };
  goBig(v);
  showBig().then(() => pushBig(true)).catch((e) => console.warn("큰 창 열기 실패", e));
}

// 큰 창이 늦게 떠서 첫 상태를 놓쳤을 수 있다: 준비됐다고 하면 다시 넘긴다
listen("big-ready", () => pushBig(true));
listen<View>("big-go", (e) => goBig(e.payload));
// seen은 같은 세션을 두 번 보내지 않게 markSeen으로. 그 밖은 못 보냈으면 큰 창에 알려 입력 글을 되돌리게 한다
listen<Outgoing>("big-send", (e) => {
  const m = e.payload;
  if (m.type === "seen") { markSeen(m.session_id); return; }
  if (send(m)) return;
  emitTo("big", "big-send-failed", m).catch((err) => console.warn("큰 창 보내기 실패", err));
});
// 큰 창을 닫으면(숨김, lib.rs) 큰 창 몫 상태를 버린다. 작은 패널은 다시 열지 않는다
listen("big-closed", () => { big = null; bigSent = null; });

// 창 자리: 패널이 열리면 패널 크기를 넘겨 강아지 위나 옆에 놓는다(shared/placement.ts). 같은 크기는 다시 요청하지 않는다
let lastSize: string | null = null;
function fit() {
  const key = state.panelOpen ? `${PANEL_WIDTH}x${panelRoot.offsetHeight}` : "";
  if (key === lastSize) return;
  lastSize = key;
  placeWindow(state.panelOpen ? { width: PANEL_WIDTH, height: panelRoot.offsetHeight } : null);
}
new ResizeObserver(fit).observe(panelRoot);

// 창을 놓은 뒤 창 안 강아지·패널 자리와 꼬리를 맞춘다. 꼬리는 위 모양일 때만
onPlaced((l) => {
  dogRoot.style.left = `${l.dog.x}px`;
  dogRoot.style.top = `${l.dog.y}px`;
  if (l.panel) {
    panelRoot.style.left = `${l.panel.x}px`;
    panelRoot.style.top = `${l.panel.y}px`;
  }
  panelRoot.classList.toggle("side", l.tail === null);
  if (l.tail !== null) panelRoot.style.setProperty("--tail-left", `${l.tail}px`);
});

// 끌기: 시작하면 패널을 닫고, 놓으면 그 자리에 둔다(window.ts가 당기고 저장한다)
bindDogDrag(dogRoot, {
  start: () => {
    if (state.panelOpen) { state = { ...state, panelOpen: false }; render(); }
    beginDrag();
  },
  move: dragBy,
  end: () => { endDrag().catch((e) => console.warn("강아지 놓기 실패", e)); },
});

function render() {
  renderDog(dogRoot, state, dogClick);
  panelRoot.hidden = !state.panelOpen;
  if (state.panelOpen) renderPanel(panelRoot, state, send, go, openBig);
  else { panelRoot.replaceChildren(); panelRoot.dataset.key = ""; }
  fetchCardQuestion();
  markShownSeen();
  pushBig();
  fit();
}

render();
