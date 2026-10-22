import { emit, listen } from "@tauri-apps/api/event";
import { loadSettings, saveSettings, type Settings } from "./shared/settings";
type AiStatus = "ok" | "no_keys"; // v5 잔재. 이 창은 화면 계획 Task 3에서 지운다

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const msg = $("msg");
const KEYS = ["typesafe", "gemini"] as const;

const AI_STATE_TEXT: Record<AiStatus, string> = { ok: "정상", no_keys: "키를 넣어 주세요" };
let aiStatus: AiStatus | null = null;
listen<AiStatus | null>("backend-status", (e) => {
  aiStatus = e.payload;
  $("ai-state").textContent = aiStatus ? AI_STATE_TEXT[aiStatus] : "백엔드에 연결되지 않음";
});

async function init() {
  const s = await loadSettings();
  ($("inputShortcut") as HTMLInputElement).value = s.inputShortcut;
  await emit("backend-status-request");
}

$("save").addEventListener("click", async () => {
  msg.textContent = "";
  const s: Settings = { inputShortcut: ($("inputShortcut") as HTMLInputElement).value.trim() };
  try {
    const keys = KEYS.filter((k) => ($(k) as HTMLInputElement).value.trim());
    // 키는 백엔드가 보관한다. 백엔드에 연결되지 않았으면 보내지 못하므로 입력값을 그대로 둔다
    if (keys.length && aiStatus === null) throw new Error("백엔드에 연결되지 않아 키를 저장하지 못했어요");
    for (const k of keys) {
      await emit("backend-set-key", { name: k, value: ($(k) as HTMLInputElement).value.trim() });
      ($(k) as HTMLInputElement).value = "";
    }
    await saveSettings(s);
    await emit("settings-changed", s);
    msg.textContent = "저장했습니다.";
  } catch (e) {
    msg.textContent = `저장 실패: ${e}`;
  }
});

// 단축키 등록이 실패하면 주 창이 이전 값으로 되돌려 저장한다. 화면의 값도 다시 읽는다
listen<string>("shortcut-error", async (e) => { await init(); msg.textContent = e.payload; });
init();
