import { Store } from "@tauri-apps/plugin-store";

export type Settings = { rest: boolean; hideHouseWhenInside: boolean; inputShortcut: string; houseShortcut: string };

export const DEFAULT_SETTINGS: Settings = {
  rest: false,
  hideHouseWhenInside: false,
  inputShortcut: "CommandOrControl+Shift+Space",
  houseShortcut: "CommandOrControl+Shift+H",
};

// 예전 설정 옮기기 (vision 2026-10-15): 움직임 정도 4단계는 "쉬기"만 남고, 입력창 항상 표시는 없어졌다
// (입력창은 직접 닫기 전까지 열려 있다)
export function withDefaults(partial: (Partial<Settings> & { activity?: string; inputAlwaysVisible?: boolean }) | null | undefined): Settings {
  const others: Record<string, unknown> = { ...(partial ?? {}) };
  const activity = others.activity;
  delete others.activity;
  delete others.inputAlwaysVisible;
  const merged = { ...DEFAULT_SETTINGS, ...others } as Settings;
  if (others.rest === undefined && activity !== undefined) merged.rest = activity === "rest";
  return merged;
}

export async function loadSettings(): Promise<Settings> {
  const store = await Store.load("settings.json");
  return withDefaults(await store.get<Partial<Settings>>("settings"));
}

export async function saveSettings(s: Settings): Promise<void> {
  const store = await Store.load("settings.json");
  await store.set("settings", s);
  await store.save();
}

// 단축키 등록이 실패했을 때 저장·적용할 설정: 단축키만 이전 값(없으면 기본값)으로 되돌린다.
// 실패한 단축키를 그대로 저장하면 앱을 다시 켤 때 단축키가 모두 동작하지 않기 때문이다.
export function shortcutFallback(attempted: Settings, prev: Settings | null): Settings {
  const base = prev ?? DEFAULT_SETTINGS;
  return { ...attempted, inputShortcut: base.inputShortcut, houseShortcut: base.houseShortcut };
}
