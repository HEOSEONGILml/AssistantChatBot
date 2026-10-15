// 두뇌 프로토콜 v3 (docs/brain-protocol.md). 두뇌가 정한 어휘를 이 화면의 몸체 동작에 대응시킨다.
import type { DogAction } from "../body/sprite";
import { MOVES, type Move, type Movement } from "../body/dog";
import { MOOD_IDS, type MoodId } from "../body/mood-style";

export const PROTOCOL_VERSION = 3;

export const EVENT_KINDS = ["typing", "message", "dog_spoke", "quiet", "returned", "house_in", "house_out", "poke", "pet", "throw"] as const;
export type EventKind = (typeof EVENT_KINDS)[number];
export type EventContext = Record<string, string | number>;

// 반응 = 가장 크게 오른 기분의 표출 (기분 8개 스펙). 평온(calm)은 반응이 아니라 기분 상태에만 쓴다
const REACTIONS = ["bored", "sleepy", "excited", "sad", "annoyed", "curious", "surprised", "scared"] as const;
export type BrainReaction = (typeof REACTIONS)[number];

export const ACTION_TO_DOG = {
  stand: "idle_stand", sit: "idle_sit", lie_down: "idle_lay", sleep: "sleep", beg: "beg", bark: "bark",
} as const satisfies Record<string, DogAction>;
export type BrainAction = keyof typeof ACTION_TO_DOG;

const AI_STATUSES = ["ok", "no_keys", "bad_key"] as const;
export type AiStatus = (typeof AI_STATUSES)[number];

export type Reaction = { reaction?: BrainReaction; action?: BrainAction; utterance?: string };

// 설정 창 상태·로그 탭용 조회 결과 (두뇌 스펙 v2 3.1). 보기만 하므로 모양만 가볍게 확인한다
export type BrainState = {
  dog: {
    personality: { baseline: Record<string, number>; sensitivity: Record<string, number>; whim: number; temperament: Record<string, number> };
    mood: Record<string, number>; intimacy: number; habit: Record<string, number>;
  };
  talkativeness: number;
  movement: { weights: Record<string, number>; run: number; idle_scale: number };
};
export type Judgement = {
  ts: number;
  events: { 종류: string; 맥락?: Record<string, unknown> }[];
  jev?: { action: Record<string, number>; speak: number; change?: Record<string, number> };
  model?: { action: Record<string, number>; speak: number };
  picked?: { reaction: string; action: string; speak: boolean };
  mood_change?: Record<string, number>;
  utterance?: string;
  error?: string;
};
export type BrainLog = { judgements: Judgement[]; events: string[]; brain_log: string[] };

export type BrainMessage =
  | ({ type: "reaction" } & Reaction)
  | { type: "status"; ai: AiStatus }
  | { type: "movement"; movement: Movement; mood: MoodId }
  | { type: "state"; state: BrainState }
  | { type: "log"; log: BrainLog };
export type Outgoing =
  | { type: "hello"; token: string }
  | { type: "event"; kind: EventKind; context: EventContext }
  | { type: "set_key"; name: "typesafe" | "gemini"; value: string }
  | { type: "clear_history" }
  | { type: "get_state" }
  | { type: "get_log" };

const includes = <T extends string>(list: readonly T[], x: unknown): x is T => list.includes(x as T);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

function parseMovement(o: Record<string, unknown>): Movement | null {
  const w = o.weights;
  if (!w || typeof w !== "object") return null;
  const weights = {} as Record<Move, number>;
  for (const m of MOVES) {
    const v = (w as Record<string, unknown>)[m];
    if (!finite(v) || v < 0) return null;
    weights[m] = v;
  }
  if (!finite(o.run) || o.run < 0 || o.run > 1 || !finite(o.idle_scale) || o.idle_scale <= 0) return null;
  return { weights, run: o.run, idleScale: o.idle_scale };
}

export function parseBrainMessage(raw: unknown): BrainMessage | null {
  let m: unknown;
  try { m = typeof raw === "string" ? JSON.parse(raw) : null; } catch { return null; }
  if (!m || typeof m !== "object") return null;
  const o = m as Record<string, unknown>;
  if (o.v !== PROTOCOL_VERSION) return null;
  if (o.type === "status") return includes(AI_STATUSES, o.ai) ? { type: "status", ai: o.ai } : null;
  if (o.type === "movement") {
    const mv = parseMovement(o);
    return mv ? { type: "movement", movement: mv, mood: includes(MOOD_IDS, o.mood) ? o.mood : "calm" } : null;
  }
  if (o.type === "state") {
    const dog = o.dog as Record<string, unknown> | undefined;
    if (!dog || typeof dog !== "object" || !dog.mood || !dog.personality || !finite(o.talkativeness) || !o.movement) return null;
    return { type: "state", state: { dog: o.dog, talkativeness: o.talkativeness, movement: o.movement } as BrainState };
  }
  if (o.type === "log") {
    if (!Array.isArray(o.judgements) || !Array.isArray(o.events) || !Array.isArray(o.brain_log)) return null;
    return { type: "log", log: { judgements: o.judgements, events: o.events, brain_log: o.brain_log } as BrainLog };
  }
  if (o.type !== "reaction") return null;
  // 모르는 어휘는 그 항목만 버린다: 두뇌가 먼저 어휘를 늘려도 화면이 멈추지 않게
  const r: { type: "reaction" } & Reaction = { type: "reaction" };
  if (includes(REACTIONS, o.reaction)) r.reaction = o.reaction;
  if (typeof o.action === "string" && o.action in ACTION_TO_DOG) r.action = o.action as BrainAction;
  if (typeof o.utterance === "string") r.utterance = o.utterance;
  return r;
}

export function outgoing(msg: Outgoing): string {
  return JSON.stringify({ v: PROTOCOL_VERSION, ...msg });
}

// AI 상태를 사용자에게 알릴 문구. 두뇌는 상태만 알리고 보여주는 방법은 화면이 정한다 (프로토콜)
export function statusText(ai: AiStatus | null): string | null {
  if (ai === "no_keys") return "트레이 아이콘 → 설정에서 키를 넣어 주세요";
  if (ai === "bad_key") return "키를 확인해 주세요 (트레이 아이콘 → 설정)";
  return null;
}
