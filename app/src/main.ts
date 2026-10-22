// 주 창: 강아지와 패널. 백엔드 메시지를 상태에 쌓고 다시 그린다. 상세 창에 그릴 거리를 보내고, 상세 창의 말을 백엔드로 넘긴다.
import "./ui/styles.css";
import { emitTo, listen } from "@tauri-apps/api/event";
import { connectBackend } from "./backend-link";
import { answered, pruneAnswered } from "./shared/entries";
import type { Entry, Outgoing, Task } from "./shared/protocol";
import {
  apply, disconnected, firstWaiting, followUps, initialState, needsSeen, pendingQuestion, refreshRequests, type State, type View,
} from "./shared/state";
import { renderDog } from "./ui/dog";
import { renderPanel } from "./ui/panel";
import { openDetail as showDetail, placeWindow } from "./window";

const DOG = { width: 128, height: 96 };
const PANEL_WIDTH = 340;
const PANEL_GAP = 12; // 패널은 강아지 위 12px

const dogRoot = document.getElementById("dog")!;
const panelRoot = document.getElementById("panel")!;

let state: State = initialState();
const asked = new Set<number>(); // 질문 카드용으로 get_task를 이미 보낸 작업
const seenSent = new Set<number>(); // seen을 보내고 답을 기다리는 작업
let detailTaskId: number | null = null; // 상세 창이 그리는 작업

const backend = connectBackend({
  onMessage: (m) => {
    state = apply(state, m);
    pruneAnswered(answered, (id) => state.tasks.get(id)?.state === "waiting");
    for (const out of followUps(state, m)) backend.send(out);
    // 대화 탭을 연 채 붙으면 대화 작업을 나중에 알게 된다: 그때 대화를 받아 온다
    const v = state.view;
    if (m.type === "task" && m.task.source === "chat" && !state.entries.has(m.task.id)
      && state.panelOpen && v.tab === "chat" && v.screen === "list") backend.send({ type: "get_task", task_id: m.task.id });
    render();
  },
  onOpen: () => {
    for (const out of refreshRequests(state)) backend.send(out);
    if (detailTaskId !== null) backend.send({ type: "get_task", task_id: detailTaskId });
  },
  onClose: () => { state = disconnected(state); asked.clear(); seenSent.clear(); answered.clear(); render(); },
});
const send = (m: Outgoing): boolean => backend.send(m);

// 화면을 바꾸고 그 화면에 필요한 목록을 요청한다
function go(view: View) {
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

// 알림 탭의 질문 카드: 그 작업의 질문 줄이 캐시에 없으면 한 번 받아 온다
function fetchCardQuestion() {
  for (const id of asked) if (state.tasks.get(id)?.state !== "waiting") asked.delete(id);
  if (!state.panelOpen || state.view.tab !== "alerts" || state.view.screen !== "list") return;
  const t = firstWaiting(state);
  if (t && !pendingQuestion(state, t.id) && !asked.has(t.id)) {
    asked.add(t.id);
    send({ type: "get_task", task_id: t.id });
  }
}

// 열어 본 작업이 끝났고 안 봤으면 seen. 답(seen: true)이 올 때까지 다시 보내지 않는다
function markSeen(id: number) {
  if (!needsSeen(state, id) || seenSent.has(id)) return;
  if (send({ type: "seen", task_id: id })) seenSent.add(id);
}
function markShownSeen() {
  for (const id of seenSent) if (!needsSeen(state, id)) seenSent.delete(id);
  const v = state.view;
  if (state.panelOpen && (v.screen === "task" || v.screen === "schedule") && v.taskId !== undefined) markSeen(v.taskId);
}

// --- 상세 창 ---
// 마지막으로 보낸 작업·줄·연결. 같으면 다시 보내지 않는다. 끊겨 상태에서 작업이 지워져도 마지막 것을 연결 끊김과 함께 보낸다
let detailSent: { task?: Task; entries?: Entry[]; connected?: boolean } = {};

function pushDetail(force = false) {
  if (detailTaskId === null) return;
  const task = state.tasks.get(detailTaskId) ?? (detailSent.task?.id === detailTaskId ? detailSent.task : undefined);
  if (!task) return;
  const entries = state.entries.get(detailTaskId) ?? detailSent.entries ?? [];
  const connected = state.connected;
  const d = detailSent;
  if (!force && d.task === task && d.entries === entries && d.connected === connected) return;
  detailSent = { task, entries, connected };
  emitTo("detail", "detail-data", { task, entries, connected }).catch((e) => console.warn("상세 창 보내기 실패", e));
}

function openDetail(taskId: number) {
  detailTaskId = taskId;
  detailSent = {};
  send({ type: "get_task", task_id: taskId });
  showDetail(taskId).then(() => pushDetail(true)).catch((e) => console.warn("상세 창 열기 실패", e));
}

// 상세 창이 늦게 떠서 첫 detail-open·detail-data를 놓쳤을 수 있다: 준비됐다고 하면 다시 보낸다
listen("detail-ready", () => {
  if (detailTaskId === null) return;
  emitTo("detail", "detail-open", detailTaskId).then(() => pushDetail(true)).catch((e) => console.warn("상세 창 보내기 실패", e));
});
listen<{ taskId: number; text: string }>("detail-say", (e) => send({ type: "say", task_id: e.payload.taskId, text: e.payload.text }));
listen<{ taskId: number }>("detail-stop", (e) => send({ type: "stop", task_id: e.payload.taskId }));
listen<{ taskId: number }>("detail-seen", (e) => { if (e.payload.taskId === detailTaskId) markSeen(e.payload.taskId); });
// 상세 창의 작업 칩·[고치기]: 패널을 열고 그 화면으로
listen<View>("detail-go", (e) => { state = { ...state, panelOpen: true }; go(e.payload); });

// 창 크기: 패널이 열리면 패널 + 12 + 강아지, 닫히면 강아지만. 같은 크기는 다시 요청하지 않는다
let lastSize = "";
function fit() {
  const [w, hh] = state.panelOpen ? [PANEL_WIDTH, panelRoot.offsetHeight + PANEL_GAP + DOG.height] : [DOG.width, DOG.height];
  const key = `${w}x${hh}`;
  if (key === lastSize) return;
  lastSize = key;
  placeWindow(w, hh);
}
new ResizeObserver(fit).observe(panelRoot);

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
