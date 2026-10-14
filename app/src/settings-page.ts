import { invoke } from "@tauri-apps/api/core";
import { emit, listen } from "@tauri-apps/api/event";
import { loadSettings, saveSettings, type Settings } from "./shared/settings";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const msg = $("msg");
const KEYS = ["typesafe", "gemini"] as const;

async function refreshKeyState() {
  for (const k of KEYS) {
    try { $(`${k}-state`).textContent = (await invoke<boolean>("key_has", { name: k })) ? "(저장됨)" : "(없음)"; }
    catch (e) { $(`${k}-state`).textContent = `(확인 실패: ${e})`; }
  }
}

async function init() {
  const s = await loadSettings();
  ($("activity") as HTMLSelectElement).value = s.activity;
  ($("inputAlwaysVisible") as HTMLInputElement).checked = s.inputAlwaysVisible;
  ($("hideHouseWhenInside") as HTMLInputElement).checked = s.hideHouseWhenInside;
  ($("inputShortcut") as HTMLInputElement).value = s.inputShortcut;
  ($("houseShortcut") as HTMLInputElement).value = s.houseShortcut;
  await refreshKeyState();
}

$("save").addEventListener("click", async () => {
  msg.textContent = "";
  const s: Settings = {
    activity: ($("activity") as HTMLSelectElement).value as Settings["activity"],
    inputAlwaysVisible: ($("inputAlwaysVisible") as HTMLInputElement).checked,
    hideHouseWhenInside: ($("hideHouseWhenInside") as HTMLInputElement).checked,
    inputShortcut: ($("inputShortcut") as HTMLInputElement).value.trim(),
    houseShortcut: ($("houseShortcut") as HTMLInputElement).value.trim(),
  };
  try {
    for (const k of KEYS) {
      const v = ($(k) as HTMLInputElement).value;
      if (v.trim()) { await invoke("key_set", { name: k, value: v }); ($(k) as HTMLInputElement).value = ""; }
    }
    await saveSettings(s);
    await emit("settings-changed", s);
    msg.textContent = "저장했습니다.";
  } catch (e) {
    msg.textContent = `저장 실패: ${e}`;
  }
  await refreshKeyState();
});

document.querySelectorAll<HTMLButtonElement>("[data-del]").forEach((b) =>
  b.addEventListener("click", async () => {
    try { await invoke("key_delete", { name: b.dataset.del }); msg.textContent = "키를 삭제했습니다."; }
    catch (e) { msg.textContent = `삭제 실패: ${e}`; }
    await refreshKeyState();
  }),
);

// 단축키 등록이 실패하면 강아지 화면이 이전 값으로 되돌려 저장한다. 화면의 값도 다시 읽는다
listen<string>("shortcut-error", async (e) => { await init(); msg.textContent = e.payload; });
init();
