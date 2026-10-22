// 주 창: 강아지와 패널. 백엔드 메시지를 상태에 쌓고 다시 그린다.
import "./ui/styles.css";
import { connectBackend } from "./backend-link";
import { apply, disconnected, followUps, initialState, refreshRequests, type State } from "./shared/state";
import { renderDog } from "./ui/dog";
import { h } from "./ui/dom";
import { placeWindow } from "./window";

const DOG = { width: 128, height: 96 };
const PANEL_WIDTH = 340;
const PANEL_GAP = 12; // 패널은 강아지 위 12px

const dogRoot = document.getElementById("dog")!;
const panelRoot = document.getElementById("panel")!;

let state: State = initialState();
let size = "";

const backend = connectBackend({
  onMessage: (m) => {
    state = apply(state, m);
    for (const out of followUps(state, m)) backend.send(out);
    render();
  },
  onOpen: () => { for (const out of refreshRequests(state)) backend.send(out); },
  onClose: () => { state = disconnected(state); render(); },
});

function togglePanel() {
  const panelOpen = !state.panelOpen;
  // 로그아웃이면 패널을 열 때 설정 탭부터 보인다
  const view = panelOpen && state.loggedIn === false ? { tab: "settings" as const, screen: "list" as const, page: 1 } : state.view;
  state = { ...state, panelOpen, view };
  if (panelOpen) for (const out of refreshRequests(state)) backend.send(out);
  render();
}

function render() {
  renderDog(dogRoot, state, togglePanel);
  panelRoot.hidden = !state.panelOpen;
  // 패널 내용은 다음 Task에서 채운다
  panelRoot.replaceChildren(...(state.panelOpen ? [h("div", { class: "placeholder" }, "준비 중")] : []));
  const [w, ht] = state.panelOpen
    ? [PANEL_WIDTH, panelRoot.offsetHeight + PANEL_GAP + DOG.height]
    : [DOG.width, DOG.height];
  if (`${w}x${ht}` !== size) {
    size = `${w}x${ht}`;
    placeWindow(w, ht).catch((e) => console.warn("창 배치 실패", e));
  }
}

render();
