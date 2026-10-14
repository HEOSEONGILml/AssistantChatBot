import type { Win } from "./dog";

type Span = { left: number; right: number };

// 창 목록(위에 있는 창부터)에서 각 창 윗변 중 위 창들에 가려지지 않고 보이는 가장 넓은 구간을 구한다.
// 강아지가 가려진 창의 윗변(보이지 않는 곳)에 올라앉지 않게 하려는 것이다.
export function exposeTopEdges(wins: Win[]): Win[] {
  return wins.map((w, i) => {
    let spans: Span[] = [{ left: w.left, right: w.left + w.width }];
    for (const above of wins.slice(0, i)) {
      // 위 창이 이 창의 윗변 높이를 덮을 때만 가린다
      if (!(above.top <= w.top && above.top + above.height > w.top)) continue;
      const cl = above.left, cr = above.left + above.width;
      spans = spans.flatMap((s) => {
        if (cr <= s.left || cl >= s.right) return [s];
        const parts: Span[] = [];
        if (cl > s.left) parts.push({ left: s.left, right: cl });
        if (cr < s.right) parts.push({ left: cr, right: s.right });
        return parts;
      });
    }
    const widest = spans.reduce<Span | null>((best, s) => (!best || s.right - s.left > best.right - best.left ? s : best), null);
    return { ...w, span: widest };
  });
}
