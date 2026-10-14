import { emit, listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { PhysicalPosition } from "@tauri-apps/api/dpi";

const win = getCurrentWindow();
const box = document.getElementById("talk") as HTMLInputElement;

listen<{ x: number; y: number }>("open-input", async (e) => {
  await win.setPosition(new PhysicalPosition(e.payload.x, Math.max(0, e.payload.y - 70)));
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
  await win.hide(); // Task 9 Step 5에서 "입력창 항상 표시" 설정을 따르도록 바꾼다
});
