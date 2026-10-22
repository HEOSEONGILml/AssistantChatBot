// 사용량 탭(14): 모든 모델 공통, 모델별 막대. 값은 다이제스트 6절.
import { limitRight, limitRows, type LimitRow } from "../shared/forms";
import type { State } from "../shared/state";
import { h } from "./dom";

function row(r: LimitRow, now: Date): HTMLElement {
  const { percent, reset } = limitRight(r, now);
  const bar = h("div", {
    class: "bar", role: "progressbar", "aria-label": r.name, "aria-valuemin": 0, "aria-valuemax": 100,
    "aria-valuenow": r.percent === null ? undefined : Math.min(r.percent, 100),
  }, h("span", { class: "bar-fill" }));
  (bar.firstElementChild as HTMLElement).style.width = `${Math.min(r.percent ?? 0, 100)}%`;
  return h("div", { class: "use-row" },
    h("div", { class: "use-top" }, h("span", { class: "use-name" }, r.name),
      h("span", { class: "use-val" }, h("b", {}, percent), reset ? ` · ${reset}` : "")),
    bar);
}

export function usageBody(s: State): Node[] {
  const { common, models } = limitRows(s.limits);
  if (!common.length && !models.length) return [h("p", { class: "empty" }, "아직 사용량 정보가 없어요. 작업이 돌면 채워져요.")];
  const now = new Date();
  return [h("div", { class: "usage" },
    common.length ? h("section", { class: "use-sec" }, h("h3", {}, "모든 모델 공통"), ...common.map((r) => row(r, now))) : null,
    models.length ? h("section", { class: common.length ? "use-sec use-sep" : "use-sec" }, h("h3", {}, "모델별"), ...models.map((r) => row(r, now))) : null,
    h("p", { class: "use-note" }, "이 PC에서 계산한 근삿값이에요. 다른 기기와 claude.ai 사용량은 빠져 있어요."))];
}
