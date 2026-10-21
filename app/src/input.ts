import { emit, listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";

const win = getCurrentWindow();
const box = document.getElementById("talk") as HTMLInputElement;

// 단축키: 누를 때마다 열고 닫는다. 창 위치는 tauri.conf.json의 center가 정한다
listen("toggle-input", async () => {
  if (await win.isVisible()) { await win.hide(); return; }
  await win.show();
  await win.setFocus();
  box.focus();
});

box.addEventListener("keydown", async (ev) => {
  if (ev.key === "Escape") { await win.hide(); return; }
  if (ev.key !== "Enter" || ev.isComposing || !box.value.trim()) return;
  emit("input-sent", { text: box.value.trim() });
  box.value = "";
});
