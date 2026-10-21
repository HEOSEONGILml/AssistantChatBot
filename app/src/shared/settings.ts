import { Store } from "@tauri-apps/plugin-store";

export type Settings = { inputShortcut: string };

export const DEFAULT_SETTINGS: Settings = { inputShortcut: "CommandOrControl+Shift+Space" };

// 저장본에 예전 설정(강아지 집·쉬기 등)이 남아 있어도 지금 쓰는 값만 꺼낸다
export function withDefaults(saved: Partial<Settings> | null | undefined): Settings {
  return { inputShortcut: saved?.inputShortcut || DEFAULT_SETTINGS.inputShortcut };
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
