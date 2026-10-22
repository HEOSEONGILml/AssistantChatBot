// 작은 DOM 도우미: 요소를 만들고 속성·이벤트·자식을 붙인다.
import { parseMarkdown, type Inline } from "../shared/markdown";
type Attr = string | number | boolean | null | undefined | ((e: Event) => void);
type Child = Node | string | null | undefined | false;

export function h(tag: string, attrs: Record<string, Attr> = {}, ...children: Child[]): HTMLElement {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v); // onClick → click
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v != null) el.setAttribute(k, String(v));
  }
  for (const c of children) if (c !== null && c !== undefined && c !== false) el.append(c);
  return el;
}

// 고정된 SVG 글(코드 안의 상수만, 사용자 글은 넣지 않는다)을 요소로 만든다
export function svg(markup: string): Element {
  const t = document.createElement("template");
  t.innerHTML = markup.trim();
  return t.content.firstElementChild!;
}

// 에이전트 글(마크다운)을 요소로 만든다. 글은 텍스트 노드로만 넣는다
export function markdown(text: string): HTMLElement {
  const inline = (xs: Inline[]) => xs.map((x) => (x.t === "text" ? x.v : h(x.t === "b" ? "b" : "code", {}, x.v)));
  return h("div", { class: "md" }, ...parseMarkdown(text).map((b) => b.type === "p"
    ? h("p", {}, ...b.lines.flatMap((l, i) => [...(i ? [h("br")] : []), ...inline(l)]))
    : h(b.type, {}, ...b.items.map((it) => h("li", {}, ...inline(it))))));
}

// 패널 머리 아이콘(고정 SVG)
export const BACK_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>`;
// 크게 보기: 대각 화살표 둘 (다이제스트 2절, 탭 바·작업 대화·스케줄 대화 머리 공통)
export const EXPAND_ICON = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M21 3l-7 7"/><path d="M3 21l7-7"/></svg>`;
// 휴지통 (다이제스트 3절 "지우기 버튼 위치"). 머리 아이콘은 15px, 대화 탭 줄은 13px
export const trashIcon = (size: number) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>`;

// 크게 보기 버튼(aria-label·title "크게 보기")
export const expandButton = (cls: string, onClick: () => void) =>
  h("button", { type: "button", class: cls, "aria-label": "크게 보기", title: "크게 보기", onClick }, svg(EXPAND_ICON));
// 대화 머리의 지우기 버튼(휴지통 44x44). label: "작업 지우기" | "스케줄 지우기"
export const deleteButton = (label: string, onClick: () => void) =>
  h("button", { type: "button", class: "icon-btn", "aria-label": label, title: label, onClick }, svg(trashIcon(15)));

// 켜짐·꺼짐 스위치(스케줄 대화 머리, 설정 탭 화면 기록). aria-label은 "<label> 켜짐|꺼짐"
export function switchButton(o: { on: boolean; label: string; disabled: boolean; onToggle: () => void }): HTMLElement {
  return h("button", {
    type: "button", role: "switch", class: o.on ? "switch" : "switch switch-off", "aria-checked": String(o.on),
    "aria-label": `${o.label} ${o.on ? "켜짐" : "꺼짐"}`, disabled: o.disabled, onClick: o.onToggle,
  }, h("span", {}, o.on ? "켜짐" : "꺼짐"), h("span", { class: "switch-track", "aria-hidden": "true" }, h("span", { class: "switch-knob" })));
}

// 패널 머리: 뒤로 + 제목
export function header(title: string, backLabel: string, back: () => void): HTMLElement {
  return h("div", { class: "head" },
    h("button", { type: "button", class: "back", "aria-label": backLabel, onClick: back }, svg(BACK_ICON)),
    h("span", { class: "head-title" }, title));
}
