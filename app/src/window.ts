// 창 위치·크기와 상세 창 열기.
import { emitTo } from "@tauri-apps/api/event";
import { PhysicalPosition, PhysicalSize, Window, getCurrentWindow, primaryMonitor } from "@tauri-apps/api/window";

const RIGHT_GAP = 20; // 정한 값: 창 오른쪽 끝 = 작업 영역 오른쪽 − 20px

// 주 창을 width x height(논리 px)로 바꾸고 주 모니터 작업 영역의 오른쪽 아래에 붙인다
export async function placeWindow(width: number, height: number): Promise<void> {
  const m = await primaryMonitor();
  if (!m) return;
  const k = m.scaleFactor;
  const { position: p, size: s } = m.workArea; // 물리 px
  const w = Math.round(width * k);
  const hh = Math.round(height * k);
  const win = getCurrentWindow();
  await win.setSize(new PhysicalSize(w, hh));
  await win.setPosition(new PhysicalPosition(p.x + s.width - Math.round(RIGHT_GAP * k) - w, p.y + s.height - hh));
}

// 상세 창을 보이고 어떤 작업을 그릴지 알린다. 그리는 쪽은 detail.html(Task 5)
export async function openDetail(taskId: number): Promise<void> {
  const win = await Window.getByLabel("detail");
  if (!win) return;
  await emitTo("detail", "detail-open", taskId);
  await win.show();
  await win.setFocus();
}
