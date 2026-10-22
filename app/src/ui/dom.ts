// 작은 DOM 도우미: 요소를 만들고 속성·이벤트·자식을 붙인다.
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
