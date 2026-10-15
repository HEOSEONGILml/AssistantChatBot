// 두뇌 프로토콜 v1 (docs/brain-protocol.md). 두뇌가 정한 어휘를 이 화면의 몸체 동작에 대응시킨다.
import type { DogAction } from "../body/sprite";

export const PROTOCOL_VERSION = 1;

const EMOTIONS = ["excited", "angry", "curious", "surprised", "sad", "sleepy", "calm"] as const;
export type Emotion = (typeof EMOTIONS)[number];

export const ACTION_TO_DOG = {
  stand: "idle_stand", sit: "idle_sit", lie_down: "idle_lay", sleep: "sleep", beg: "beg", bark: "bark",
} as const satisfies Record<string, DogAction>;
export type BrainAction = keyof typeof ACTION_TO_DOG;

const AI_STATUSES = ["ok", "no_keys", "bad_key"] as const;
export type AiStatus = (typeof AI_STATUSES)[number];

export type Signal =
  | { kind: "typing"; text: string }
  | { kind: "sent"; text: string }
  | { kind: "house"; inside: boolean; awayMs: number }
  | { kind: "bubble_seen" }
  | { kind: "user_return" }
  | { kind: "user_away" }
  | { kind: "interaction"; type: "poke" | "pet" | "throw" };

export type Reaction = { emotion?: Emotion; action?: BrainAction; utterance?: string };
export type BrainMessage = ({ type: "reaction" } & Reaction) | { type: "status"; ai: AiStatus };
export type Outgoing =
  | { type: "hello"; token: string }
  | { type: "signal"; signal: Signal }
  | { type: "set_key"; name: "typesafe" | "gemini"; value: string }
  | { type: "clear_history" };

const includes = <T extends string>(list: readonly T[], x: unknown): x is T => list.includes(x as T);

export function parseBrainMessage(raw: unknown): BrainMessage | null {
  let m: unknown;
  try { m = typeof raw === "string" ? JSON.parse(raw) : null; } catch { return null; }
  if (!m || typeof m !== "object") return null;
  const o = m as Record<string, unknown>;
  if (o.v !== PROTOCOL_VERSION) return null;
  if (o.type === "status") return includes(AI_STATUSES, o.ai) ? { type: "status", ai: o.ai } : null;
  if (o.type !== "reaction") return null;
  // 모르는 어휘는 그 항목만 버린다: 두뇌가 먼저 어휘를 늘려도 화면이 멈추지 않게
  const r: { type: "reaction" } & Reaction = { type: "reaction" };
  if (includes(EMOTIONS, o.emotion)) r.emotion = o.emotion;
  if (typeof o.action === "string" && o.action in ACTION_TO_DOG) r.action = o.action as BrainAction;
  if (typeof o.utterance === "string") r.utterance = o.utterance;
  return r;
}

export function outgoing(msg: Outgoing): string {
  return JSON.stringify({ v: PROTOCOL_VERSION, ...msg });
}

// 접속할 때마다 보낼 현재 상태. 연결이 끊긴 사이 바뀐 집·자리 상태를 두뇌가 놓치지 않게 항상 둘 다 보낸다.
// 두뇌는 이미 아는 상태면 무시한다 (docs/brain-protocol.md)
export function stateSignals(s: { inHouse: boolean; houseAwayMs: number; userActive: boolean }): Signal[] {
  return [
    { kind: "house", inside: s.inHouse, awayMs: s.inHouse ? 0 : s.houseAwayMs },
    { kind: s.userActive ? "user_return" : "user_away" },
  ];
}

// AI 상태를 사용자에게 알릴 문구. 두뇌는 상태만 알리고 보여주는 방법은 화면이 정한다 (프로토콜)
export function statusText(ai: AiStatus | null): string | null {
  if (ai === "no_keys") return "트레이 아이콘 → 설정에서 키를 넣어 주세요";
  if (ai === "bad_key") return "키를 확인해 주세요 (트레이 아이콘 → 설정)";
  return null;
}
