import { Store } from "@tauri-apps/plugin-store";

export type Settings = { inputAlwaysVisible: boolean; hideHouseWhenInside: boolean; inputShortcut: string; houseShortcut: string };

export const DEFAULT_SETTINGS: Settings = {
  inputAlwaysVisible: false,
  hideHouseWhenInside: false,
  inputShortcut: "CommandOrControl+Shift+Space",
  houseShortcut: "CommandOrControl+Shift+H",
};

export function withDefaults(partial: Partial<Settings> | null | undefined): Settings {
  return { ...DEFAULT_SETTINGS, ...(partial ?? {}) };
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
