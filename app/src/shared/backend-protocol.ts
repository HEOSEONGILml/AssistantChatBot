// 백엔드 프로토콜 v5 (docs/backend-protocol.md). 조수 설계 전의 최소 규약이다.
export const PROTOCOL_VERSION = 5;

const AI_STATUSES = ["ok", "no_keys"] as const;
export type AiStatus = (typeof AI_STATUSES)[number];

export type BackendMessage = { type: "status"; ai: AiStatus };
export type Outgoing =
  | { type: "hello"; token: string }
  | { type: "message"; text: string }
  | { type: "set_key"; name: "typesafe" | "gemini"; value: string };

export function parseBackendMessage(raw: unknown): BackendMessage | null {
  let m: unknown;
  try { m = typeof raw === "string" ? JSON.parse(raw) : null; } catch { return null; }
  if (!m || typeof m !== "object") return null;
  const o = m as Record<string, unknown>;
  if (o.v !== PROTOCOL_VERSION) return null;
  if (o.type === "status" && AI_STATUSES.includes(o.ai as AiStatus)) return { type: "status", ai: o.ai as AiStatus };
  return null;
}

export function outgoing(msg: Outgoing): string {
  return JSON.stringify({ v: PROTOCOL_VERSION, ...msg });
}
