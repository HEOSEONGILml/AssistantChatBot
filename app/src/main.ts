// 주 창: 강아지와 패널. 백엔드 메시지를 상태에 쌓고 다시 그린다.
import "./ui/styles.css";
import { connectBackend } from "./backend-link";
import type { Outgoing } from "./shared/protocol";
import {
  apply, disconnected, firstWaiting, followUps, initialState, pendingQuestion, refreshRequests, type State, type View,
} from "./shared/state";
import { renderDog } from "./ui/dog";
import { renderPanel } from "./ui/panel";
import { placeWindow } from "./window";

const DOG = { width: 128, height: 96 };
const PANEL_WIDTH = 340;
const PANEL_GAP = 12; // 패널은 강아지 위 12px

const dogRoot = document.getElementById("dog")!;
const panelRoot = document.getElementById("panel")!;

let state: State = initialState();
const asked = new Set<number>(); // 질문 카드용으로 get_task를 이미 보낸 작업

const backend = connectBackend({
  onMessage: (m) => {
    state = apply(state, m);
    for (const out of followUps(state, m)) backend.send(out);
    render();
  },
  onOpen: () => { for (const out of refreshRequests(state)) backend.send(out); },
  onClose: () => { state = disconnected(state); asked.clear(); render(); },
});
const send = (m: Outgoing) => { backend.send(m); };

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

// 창 크기: 패널이 열리면 패널 + 12 + 강아지, 닫히면 강아지만
function fit() {
  if (state.panelOpen) placeWindow(PANEL_WIDTH, panelRoot.offsetHeight + PANEL_GAP + DOG.height);
  else placeWindow(DOG.width, DOG.height);
}
new ResizeObserver(fit).observe(panelRoot);

function render() {
  renderDog(dogRoot, state, togglePanel);
  panelRoot.hidden = !state.panelOpen;
  if (state.panelOpen) renderPanel(panelRoot, state, send, go);
  else { panelRoot.replaceChildren(); panelRoot.dataset.key = ""; }
  fetchCardQuestion();
  fit();
}

render();
