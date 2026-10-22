// 강아지: 자세 스프라이트, 왼쪽 위 배지 알약, 툴팁, 끌기. 값은 다이제스트 2·3(20번)·7절.
import { isDrag } from "../shared/placement";
import { badges, pose, tooltip, type Pose, type State } from "../shared/state";
import { h } from "./dom";

// 시트 768x648(프레임 96x72) 안의 위치. 정지 프레임은 첫 칸, 걷기만 아트보드대로 2번째 칸
const SPRITE: Record<Pose, string> = {
  sleep: "0 -576px",
  beg: "0 -504px",
  walk: "-192px -288px",
  lay: "0 -144px",
  stand: "0 0",
  sit: "0 -72px",
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

type Drag = { start: () => void; move: (dx: number, dy: number) => void; end: () => void };

// 강아지를 누른 채 4px 넘게 움직이면 끌기, 아니면 누르기(버튼 click 그대로). 끈 뒤의 click은 버린다.
// root는 다시 그려도 남는 바깥 요소다(버튼은 다시 그릴 때 바뀐다). 끄는 동안 root에 .dragging(20번 모양)
export function bindDogDrag(root: HTMLElement, on: Drag): void {
  let from: { x: number; y: number; id: number } | null = null;
  let dragging = false;
  let swallow = false;
  root.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    from = { x: e.screenX, y: e.screenY, id: e.pointerId };
    dragging = false;
    swallow = false;
  });
  root.addEventListener("pointermove", (e) => {
    if (!from || e.pointerId !== from.id) return;
    const dx = e.screenX - from.x;
    const dy = e.screenY - from.y;
    if (!dragging) {
      if (!isDrag(dx, dy)) return;
      dragging = true;
      root.setPointerCapture(e.pointerId); // 누르기에는 잡지 않는다: 잡으면 click이 버튼에 가지 않는다
      root.classList.add("dragging");
      on.start();
    }
    on.move(dx, dy);
  });
  const finish = (e: PointerEvent) => {
    if (!from || e.pointerId !== from.id) return;
    from = null;
    if (!dragging) return;
    dragging = false;
    swallow = true;
    setTimeout(() => { swallow = false; }); // click이 안 오면(놓은 곳이 다르면) 다음 키보드 누르기를 막지 않게
    root.classList.remove("dragging");
    on.end();
  };
  root.addEventListener("pointerup", finish);
  root.addEventListener("pointercancel", finish);
  root.addEventListener("lostpointercapture", finish);
  root.addEventListener("click", (e) => {
    if (!swallow) return;
    swallow = false;
    e.stopPropagation();
    e.preventDefault();
  }, true);
}
