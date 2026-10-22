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
