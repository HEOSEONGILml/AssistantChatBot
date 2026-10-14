import type { DogAction } from "../body/sprite";

export type Reaction = { emotion?: string; action?: DogAction; utterance?: string };

export type Signal =
  | { kind: "typing"; text: string }
  | { kind: "sent"; text: string }
  | { kind: "house"; inside: boolean; awayMs: number }
  | { kind: "bubble_seen" }
  | { kind: "user_return" }
  | { kind: "user_away" }
  | { kind: "interaction"; type: "poke" | "pet" | "throw" };
