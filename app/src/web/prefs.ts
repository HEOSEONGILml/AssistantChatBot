// 웹 화면 설정. PC 앱의 Tauri store 대신 localStorage에 둔다. 단축키는 웹에 없다
export type Prefs = { rest: boolean; hideHouseWhenInside: boolean };
type Storage = { getItem(k: string): string | null; setItem(k: string, v: string): void };

export const DEFAULT_PREFS: Prefs = { rest: false, hideHouseWhenInside: false };
const KEY = "dog.prefs";

export function loadPrefs(s: Storage): Prefs {
  try {
    const raw = JSON.parse(s.getItem(KEY) ?? "{}");
    return { rest: raw.rest === true, hideHouseWhenInside: raw.hideHouseWhenInside === true };
  } catch {
    return { ...DEFAULT_PREFS }; // 깨진 값이나 막힌 저장소(사생활 보호 모드 등)
  }
}

export function savePrefs(s: Storage, p: Prefs): void {
  try { s.setItem(KEY, JSON.stringify(p)); } catch { /* 저장 못 해도 이번 세션은 계속 */ }
}
