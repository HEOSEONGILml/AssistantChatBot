import { emit, listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { PhysicalPosition } from "@tauri-apps/api/dpi";
import { loadSettings } from "./shared/settings";
import { placeAbove } from "./body/coords";

const win = getCurrentWindow();
const box = document.getElementById("talk") as HTMLInputElement;

// 입력창은 강아지 집 위에 뜬다. payload는 집 영역(물리 좌표)
listen<{ left: number; top: number; right: number; bottom: number }>("open-input", async (e) => {
  const size = await win.outerSize();
  const p = placeAbove(e.payload, size, Math.round(8 * (await win.scaleFactor())));
  await win.setPosition(new PhysicalPosition(p.x, p.y));
  await win.show();
  await win.setFocus();
  box.focus();
});

box.addEventListener("input", () => emit("signal", { kind: "typing", text: box.value }));
box.addEventListener("keydown", async (ev) => {
  if (ev.key === "Escape") { await win.hide(); return; }
  if (ev.key !== "Enter" || ev.isComposing || !box.value.trim()) return;
  emit("signal", { kind: "sent", text: box.value.trim() });
  box.value = "";
  if (!(await loadSettings()).inputAlwaysVisible) await win.hide();
});
