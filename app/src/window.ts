// 창 위치·크기와 상세 창 열기.
import { emitTo } from "@tauri-apps/api/event";
import { PhysicalPosition, PhysicalSize, Window, getCurrentWindow, primaryMonitor } from "@tauri-apps/api/window";

const RIGHT_GAP = 20; // 정한 값: 창 오른쪽 끝 = 작업 영역 오른쪽 − 20px

let applied = ""; // 마지막으로 성공한 배치 (모니터 작업 영역 + 크기)
let wanted: [number, number] | null = null; // 아직 적용하지 않은 가장 최근 요청
let running: Promise<void> | null = null;

// 주 창을 width x height(논리 px)로 바꾸고 주 모니터 작업 영역의 오른쪽 아래에 붙인다.
// 호출이 겹치면 차례로 하나씩 하고, 밀린 요청 가운데 가장 최근 것만 적용한다
export function placeWindow(width: number, height: number): Promise<void> {
  wanted = [width, height];
  running ??= (async () => {
    try {
      while (wanted) {
        const [w, hh] = wanted;
        wanted = null;
        try { await place(w, hh); } catch (e) { console.warn("창 배치 실패", e); }
      }
    } finally { running = null; }
  })();
  return running;
}

async function place(width: number, height: number): Promise<void> {
  const m = await primaryMonitor();
  if (!m) return;
  const k = m.scaleFactor;
  const { position: p, size: s } = m.workArea; // 물리 px
  const w = Math.round(width * k);
  const hh = Math.round(height * k);
  const key = `${p.x},${p.y},${s.width},${s.height},${w}x${hh}`;
  if (key === applied) return;
  const win = getCurrentWindow();
  const pos = new PhysicalPosition(p.x + s.width - Math.round(RIGHT_GAP * k) - w, p.y + s.height - hh);
  const cur = await win.innerSize();
  // 커질 때는 위치를 먼저 옮긴다. 크기부터 바꾸면 잠깐 작업 영역 밖으로 넘친다
  if (w > cur.width || hh > cur.height) {
    await win.setPosition(pos);
    await win.setSize(new PhysicalSize(w, hh));
  } else {
    await win.setSize(new PhysicalSize(w, hh));
    await win.setPosition(pos);
  }
  applied = key;
}

// 상세 창을 보이고 어떤 세션을 그릴지 알린다. 그리는 쪽은 detail.html(Task 5)
export async function openDetail(sessionId: number): Promise<void> {
  const win = await Window.getByLabel("detail");
  if (!win) return;
  await emitTo("detail", "detail-open", sessionId);
  await win.show();
  await win.setFocus();
}
