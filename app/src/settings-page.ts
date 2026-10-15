import { emit, listen } from "@tauri-apps/api/event";
import { loadSettings, saveSettings, type Settings } from "./shared/settings";
import type { AiStatus } from "./shared/brain-protocol";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const msg = $("msg");
const KEYS = ["typesafe", "gemini"] as const;

const AI_STATE_TEXT: Record<AiStatus, string> = { ok: "정상", no_keys: "키를 넣어 주세요", bad_key: "키를 확인해 주세요" };
let aiStatus: AiStatus | null = null;
listen<AiStatus | null>("brain-status", (e) => {
  aiStatus = e.payload;
  $("ai-state").textContent = aiStatus ? AI_STATE_TEXT[aiStatus] : "두뇌에 연결되지 않음";
});

async function init() {
  const s = await loadSettings();
  ($("rest") as HTMLInputElement).checked = s.rest;
  ($("inputAlwaysVisible") as HTMLInputElement).checked = s.inputAlwaysVisible;
  ($("hideHouseWhenInside") as HTMLInputElement).checked = s.hideHouseWhenInside;
  ($("inputShortcut") as HTMLInputElement).value = s.inputShortcut;
  ($("houseShortcut") as HTMLInputElement).value = s.houseShortcut;
  await emit("brain-status-request");
}

$("save").addEventListener("click", async () => {
  msg.textContent = "";
  const s: Settings = {
    rest: ($("rest") as HTMLInputElement).checked,
    inputAlwaysVisible: ($("inputAlwaysVisible") as HTMLInputElement).checked,
    hideHouseWhenInside: ($("hideHouseWhenInside") as HTMLInputElement).checked,
    inputShortcut: ($("inputShortcut") as HTMLInputElement).value.trim(),
    houseShortcut: ($("houseShortcut") as HTMLInputElement).value.trim(),
  };
  try {
    const keys = KEYS.filter((k) => ($(k) as HTMLInputElement).value.trim());
    // 키는 두뇌가 보관한다. 두뇌에 연결되지 않았으면 보내지 못하므로 입력값을 그대로 둔다
    if (keys.length && aiStatus === null) throw new Error("두뇌에 연결되지 않아 키를 저장하지 못했어요");
    for (const k of keys) {
      await emit("brain-set-key", { name: k, value: ($(k) as HTMLInputElement).value.trim() });
      ($(k) as HTMLInputElement).value = "";
    }
    await saveSettings(s);
    await emit("settings-changed", s);
    msg.textContent = "저장했습니다.";
  } catch (e) {
    msg.textContent = `저장 실패: ${e}`;
  }
});

$("clear-history").addEventListener("click", async () => {
  if (!confirm("대화 기록을 모두 지울까요? 되돌릴 수 없어요.")) return;
  if (aiStatus === null) { msg.textContent = "두뇌에 연결되지 않아 지우지 못했어요"; return; }
  await emit("brain-clear-history");
  msg.textContent = "대화 기록을 지웠습니다.";
});

// 단축키 등록이 실패하면 강아지 화면이 이전 값으로 되돌려 저장한다. 화면의 값도 다시 읽는다
listen<string>("shortcut-error", async (e) => { await init(); msg.textContent = e.payload; });
init();
