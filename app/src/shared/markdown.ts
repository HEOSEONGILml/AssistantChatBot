// 에이전트 글의 작은 마크다운: 문단(줄바꿈 유지), `- `·`* ` 목록, `1. ` 번호 목록, **굵게**, `코드`.
// 그 밖(제목, 링크, 기울임 등)은 글 그대로 둔다. 화면은 이 나무로 DOM을 만든다(innerHTML을 쓰지 않는다)
export type Inline = { t: "text" | "b" | "code"; v: string };
export type Block =
  | { type: "p"; lines: Inline[][] }
  | { type: "ul" | "ol"; items: Inline[][] };

const INLINE = /`([^`\n]+)`|\*\*([^*\n]+?)\*\*/g;

export function parseInline(s: string): Inline[] {
  const out: Inline[] = [];
  let at = 0;
  for (const m of s.matchAll(INLINE)) {
    if (m.index > at) out.push({ t: "text", v: s.slice(at, m.index) });
    out.push(m[1] !== undefined ? { t: "code", v: m[1] } : { t: "b", v: m[2] });
    at = m.index + m[0].length;
  }
  if (at < s.length) out.push({ t: "text", v: s.slice(at) });
  return out;
}

const BULLET = /^\s*[-*] (.*)$/;
const NUMBER = /^\s*\d+\. (.*)$/;

export function parseMarkdown(text: string): Block[] {
  const blocks: Block[] = [];
  let open = null as Block | null; // 이어 붙일 블록 (빈 줄에서 닫힌다)
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) { open = null; continue; }
    const bullet = BULLET.exec(line), number = bullet ? null : NUMBER.exec(line);
    const type = bullet ? "ul" : number ? "ol" : "p";
    const content = parseInline((bullet ?? number)?.[1] ?? line);
    const cur: Block = open?.type === type ? open : type === "p" ? { type, lines: [] } : { type, items: [] };
    if (cur !== open) { blocks.push(cur); open = cur; }
    if (cur.type === "p") cur.lines.push(content); else cur.items.push(content);
  }
  return blocks;
}
