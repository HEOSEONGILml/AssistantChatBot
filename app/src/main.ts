// 보이지 않는 주 창: 두뇌 연결을 들고 입력창·설정 창과 두뇌 사이를 잇는다. 단축키도 여기서 등록한다.
// 조수 설계 전의 빈 껍데기다 (0022).
import { emit, listen } from "@tauri-apps/api/event";
import { register, unregister } from "@tauri-apps/plugin-global-shortcut";
import { loadSettings, saveSettings, DEFAULT_SETTINGS, type Settings } from "./shared/settings";
import type { AiStatus } from "./shared/brain-protocol";
import { connectBrain } from "./brain-link";

let aiStatus: AiStatus | null = null; // null: 두뇌에 연결되지 않음
const setStatus = (s: AiStatus | null) => { aiStatus = s; emit("brain-status", s); };
const brain = connectBrain({
  onMessage: (m) => { if (m.type === "status") setStatus(m.ai); },
  onOpen: () => {},
  onClose: () => setStatus(null),
});

listen<{ text: string }>("input-sent", (e) => { brain.send({ type: "message", text: e.payload.text }); });
listen<{ name: "typesafe" | "gemini"; value: string }>("brain-set-key", (e) => { brain.send({ type: "set_key", ...e.payload }); });
listen("brain-status-request", () => { emit("brain-status", aiStatus); });

// 전역 단축키. 등록은 한 번에 하나씩(직렬) 처리한다: 저장을 빠르게 두 번 하면 등록이 엉키기 때문이다.
let active: Settings | null = null;
let queue: Promise<void> = Promise.resolve();

async function tryRegister(s: Settings): Promise<boolean> {
  try {
    await register(s.inputShortcut, (e) => { if (e.state === "Pressed") emit("toggle-input"); });
    return true;
  } catch {
    return false;
  }
}

async function applyShortcut(s: Settings) {
  const prev = active;
  if (prev) await unregister(prev.inputShortcut).catch(() => {});
  if (await tryRegister(s)) { active = s; return; }
  // 실패한 단축키는 저장하지 않는다: 이전 값(앱 시작 때는 기본값)으로 되돌려 다시 등록하고 저장한다
  const fallback = prev ?? DEFAULT_SETTINGS;
  if (await tryRegister(fallback)) active = fallback;
  await saveSettings(fallback);
  emit("shortcut-error", `단축키 등록 실패 (${s.inputShortcut}). ${prev ? "이전" : "기본"} 단축키로 되돌렸어요.`);
}
const enqueue = (s: Settings) => (queue = queue.then(() => applyShortcut(s)).catch(() => {}));

loadSettings().then(enqueue);
listen<Settings>("settings-changed", (e) => { enqueue(e.payload); });
