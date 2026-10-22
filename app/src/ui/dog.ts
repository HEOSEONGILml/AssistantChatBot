// 강아지: 자세 스프라이트, 왼쪽 위 배지 알약, 툴팁. 값은 다이제스트 2·7절.
import { badges, pose, tooltip, type Pose, type State } from "../shared/state";
import { h } from "./dom";

// 시트 1024x864(프레임 128x96) 안의 위치. 정지 프레임은 첫 칸, 걷기만 아트보드대로 2번째 칸
const SPRITE: Record<Pose, string> = {
  sleep: "0 -768px",
  beg: "0 -672px",
  walk: "-256px -384px",
  lay: "0 -192px",
  stand: "0 0",
  sit: "0 -96px",
};

export function renderDog(root: HTMLElement, state: State, onClick: () => void): void {
  const tip = tooltip(state);
  const b = badges(state);
  const pills = state.loggedIn === false ? [] : ([["red", b.red], ["yellow", b.yellow], ["green", b.green]] as const)
    .filter(([, n]) => n > 0)
    .map(([color, n]) => h("span", { class: `badge badge-${color}` }, String(n)));
  root.replaceChildren(h("button", {
    class: "dog", type: "button", title: tip, "aria-label": `강아지 — ${tip}`,
    "aria-expanded": String(state.panelOpen), onClick,
  },
  h("span", { class: "sprite", style: `background-position: ${SPRITE[pose(state)]}` }),
  pills.length ? h("span", { class: "badges", "aria-hidden": "true" }, ...pills) : null));
}
