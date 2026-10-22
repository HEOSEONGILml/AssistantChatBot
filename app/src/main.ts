// 주 창: 강아지와 패널. 백엔드 메시지를 상태에 쌓고 다시 그린다. 상세 창에 그릴 거리를 보내고, 상세 창의 말을 백엔드로 넘긴다.
import "./ui/styles.css";
import { emitTo, listen } from "@tauri-apps/api/event";
import { connectBackend } from "./backend-link";
import { answered, pruneAnswered } from "./shared/entries";
import type { Entry, Outgoing, Session } from "./shared/protocol";
import {
  apply, disconnected, firstWaiting, followUps, initialState, needsSeen, pendingQuestion, refreshRequests, type State, type View,
} from "./shared/state";
import { bindDogDrag, renderDog } from "./ui/dog";
import { renderPanel } from "./ui/panel";
import { clearDraft } from "./ui/schedule";
import { beginDrag, dragBy, endDrag, onPlaced, openDetail as showDetail, placeWindow } from "./window";

const PANEL_WIDTH = 340;

const dogRoot = document.getElementById("dog")!;
const panelRoot = document.getElementById("panel")!;

let state: State = initialState();
const asked = new Set<number>(); // 질문 카드용으로 get_session을 이미 보낸 세션
const seenSent = new Set<number>(); // seen을 보내고 답을 기다리는 세션
let detailSessionId: number | null = null; // 상세 창이 그리는 세션

const backend = connectBackend({
  onMessage: (m) => {
    state = apply(state, m);
    pruneAnswered(answered, (id) => state.sessions.get(id)?.state === "waiting");
    for (const out of followUps(state, m)) backend.send(out);
    // 대화 탭을 연 채 붙으면 대화 세션을 나중에 알게 된다: 그때 대화를 받아 온다
    const v = state.view;
    if (m.type === "session" && m.session.source === "chat" && !state.entries.has(m.session.id)
      && state.panelOpen && v.tab === "chat" && v.screen === "list") backend.send({ type: "get_session", session_id: m.session.id });
    render();
  },
  onOpen: () => {
    for (const out of refreshRequests(state)) backend.send(out);
    if (detailSessionId !== null) backend.send({ type: "get_session", session_id: detailSessionId });
  },
  onClose: () => { state = disconnected(state); asked.clear(); seenSent.clear(); answered.clear(); render(); },
});
const send = (m: Outgoing): boolean => {
  const ok = backend.send(m);
  // [로그인]을 누르면 status가 올 때까지 버튼을 막는다
  if (ok && m.type === "login") { state = { ...state, loggingIn: true }; render(); }
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

// 알림 탭의 질문 카드: 그 세션의 질문 줄이 캐시에 없으면 한 번 받아 온다
function fetchCardQuestion() {
  for (const id of asked) if (state.sessions.get(id)?.state !== "waiting") asked.delete(id);
  if (!state.panelOpen || state.view.tab !== "alerts" || state.view.screen !== "list") return;
  const t = firstWaiting(state);
  if (t && !pendingQuestion(state, t.id) && !asked.has(t.id)) {
    asked.add(t.id);
    send({ type: "get_session", session_id: t.id });
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

// --- 상세 창 ---
// 마지막으로 보낸 세션·줄·연결. 같으면 다시 보내지 않는다. 끊겨 상태에서 세션이 지워져도 마지막 것을 연결 끊김과 함께 보낸다
let detailSent: { session?: Session; entries?: Entry[]; connected?: boolean } = {};

function pushDetail(force = false) {
  if (detailSessionId === null) return;
  const session = state.sessions.get(detailSessionId) ?? (detailSent.session?.id === detailSessionId ? detailSent.session : undefined);
  if (!session) return;
  const entries = state.entries.get(detailSessionId) ?? detailSent.entries ?? [];
  const connected = state.connected;
  const d = detailSent;
  if (!force && d.session === session && d.entries === entries && d.connected === connected) return;
  detailSent = { session, entries, connected };
  emitTo("detail", "detail-data", { session, entries, connected }).catch((e) => console.warn("상세 창 보내기 실패", e));
}

function openDetail(sessionId: number) {
  detailSessionId = sessionId;
  detailSent = {};
  send({ type: "get_session", session_id: sessionId });
  showDetail(sessionId).then(() => pushDetail(true)).catch((e) => console.warn("상세 창 열기 실패", e));
}

// 상세 창이 늦게 떠서 첫 detail-open·detail-data를 놓쳤을 수 있다: 준비됐다고 하면 다시 보낸다
listen("detail-ready", () => {
  if (detailSessionId === null) return;
  emitTo("detail", "detail-open", detailSessionId).then(() => pushDetail(true)).catch((e) => console.warn("상세 창 보내기 실패", e));
});
// 못 보냈으면(그 사이 연결이 끊김) 상세 창에 알려 입력 글을 되돌리게 한다
listen<{ sessionId: number; text: string }>("detail-say", (e) => {
  if (send({ type: "say", session_id: e.payload.sessionId, text: e.payload.text })) return;
  emitTo("detail", "detail-send-failed", e.payload.text).catch((err) => console.warn("상세 창 보내기 실패", err));
});
listen<{ sessionId: number }>("detail-stop", (e) => send({ type: "stop", session_id: e.payload.sessionId }));
listen<{ sessionId: number }>("detail-seen", (e) => { if (e.payload.sessionId === detailSessionId) markSeen(e.payload.sessionId); });
// 상세 창의 세션 칩·[고치기]: 패널을 열고 그 화면으로
listen<View>("detail-go", (e) => { state = { ...state, panelOpen: true }; go(e.payload); });

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
  renderDog(dogRoot, state, togglePanel);
  panelRoot.hidden = !state.panelOpen;
  if (state.panelOpen) renderPanel(panelRoot, state, send, go, openDetail);
  else { panelRoot.replaceChildren(); panelRoot.dataset.key = ""; }
  fetchCardQuestion();
  markShownSeen();
  pushDetail();
  fit();
}

render();
