// 웹 프로토타입 화면의 순수 로직 (스펙 2026-10-19 웹 프로토타입 4절)
import { describe, expect, it } from "vitest";
import { brainUrls } from "../src/web/endpoint";
import { newPresence, noteInput, setHidden, idleMs, AWAY_MS } from "../src/web/presence";
import { loadPrefs, savePrefs, DEFAULT_PREFS } from "../src/web/prefs";
import { retryAfterClose } from "../src/web/link";

describe("brainUrls", () => {
  it("같은 출처의 /ws와 /token", () => {
    expect(brainUrls({ protocol: "http:", host: "127.0.0.1:8787" })).toEqual({ ws: "ws://127.0.0.1:8787/ws", token: "/token" });
  });
  it("https 페이지면 wss", () => {
    expect(brainUrls({ protocol: "https:", host: "dog.example.com" }).ws).toBe("wss://dog.example.com/ws");
  });
});

describe("presence", () => {
  it("마지막 입력 뒤 흐른 시간", () => {
    let p = newPresence(1000);
    p = noteInput(p, 5000);
    expect(idleMs(p, 8000)).toBe(3000);
  });
  it("탭이 숨겨지면 바로 자리 비움으로 보고, 숨겨진 시간만큼 늘어난다", () => {
    let p = noteInput(newPresence(0), 1000);
    p = setHidden(p, true, 2000);
    expect(idleMs(p, 2000)).toBeGreaterThanOrEqual(AWAY_MS);
    expect(idleMs(p, 12000)).toBe(AWAY_MS + 10000);
  });
  it("다시 보이고 입력하면 돌아온다", () => {
    let p = setHidden(noteInput(newPresence(0), 0), true, 0);
    p = setHidden(p, false, 90_000);
    p = noteInput(p, 90_500);
    expect(idleMs(p, 91_000)).toBe(500);
  });
});

describe("prefs", () => {
  const mem = (init: Record<string, string> = {}) => {
    const m = new Map(Object.entries(init));
    return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
  };
  it("없거나 깨진 값은 기본값", () => {
    expect(loadPrefs(mem())).toEqual(DEFAULT_PREFS);
    expect(loadPrefs(mem({ "dog.prefs": "{oops" }))).toEqual(DEFAULT_PREFS);
  });
  it("저장한 값을 읽는다", () => {
    const s = mem();
    savePrefs(s, { rest: true, hideHouseWhenInside: true });
    expect(loadPrefs(s)).toEqual({ rest: true, hideHouseWhenInside: true });
  });
  it("저장소를 못 쓰면 기본값으로 계속한다", () => {
    const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    expect(loadPrefs(broken)).toEqual(DEFAULT_PREFS);
    expect(() => savePrefs(broken, DEFAULT_PREFS)).not.toThrow();
  });
});

describe("retryAfterClose", () => {
  it("다른 탭이 연결을 가져가면(4002) 다시 접속하지 않는다", () => {
    expect(retryAfterClose(4002)).toBe(false);
  });
  it("그 밖의 끊김은 다시 접속한다", () => {
    expect(retryAfterClose(1006)).toBe(true);
    expect(retryAfterClose(1000)).toBe(true);
  });
});
