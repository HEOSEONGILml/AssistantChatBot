import { emit, listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { PhysicalPosition } from "@tauri-apps/api/dpi";
import { placeAbove } from "./body/coords";

const win = getCurrentWindow();
const box = document.getElementById("talk") as HTMLInputElement;

async function show(anchor: { left: number; top: number; right: number; bottom: number }) {
  const size = await win.outerSize();
  const p = placeAbove(anchor, size, Math.round(8 * (await win.scaleFactor())));
  await win.setPosition(new PhysicalPosition(p.x, p.y));
  await win.show();
  await win.setFocus();
  box.focus();
  emit("input-visibility", true);
}

async function hide() {
  await win.hide();
  emit("input-visibility", false);
}

// 말풍선 아이콘·단축키: 누를 때마다 열고 닫는다. payload는 집 영역(물리 좌표) — 입력창은 집 위에 뜬다
listen<{ left: number; top: number; right: number; bottom: number }>("toggle-input", async (e) => {
  if (await win.isVisible()) await hide();
  else await show(e.payload);
});

// 강아지가 집에 들어가면 입력창을 닫는다
listen("close-input", async () => { if (await win.isVisible()) await hide(); });

box.addEventListener("input", () => emit("input-typing", { text: box.value }));
box.addEventListener("keydown", async (ev) => {
  if (ev.key === "Escape") { await hide(); return; }
  if (ev.key !== "Enter" || ev.isComposing || !box.value.trim()) return;
  emit("input-sent", { text: box.value.trim() });
  box.value = "";
});
