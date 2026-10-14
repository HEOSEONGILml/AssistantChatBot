import type { Reaction, Signal } from "../shared/types";

// 두뇌(서브 프로젝트 2) 전까지 몸체가 동작하는지 보기 위한 가짜 두뇌
export function stubReact(s: Signal): Reaction | null {
  if (s.kind === "sent") return { action: "bark", utterance: "멍! (아직 생각하는 법을 배우는 중이에요)" };
  if (s.kind === "typing") return { action: "idle_sit" };
  return null;
}
