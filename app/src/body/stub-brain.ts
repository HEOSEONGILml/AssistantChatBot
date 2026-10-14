import type { Reaction, Signal } from "../shared/types";

// 두뇌(서브 프로젝트 2) 전까지 쓰는 임시 두뇌. 감정·동작·발화 판단은 Jev의 몫이므로 여기서 정하지 않는다.
// 메시지를 보냈을 때 몸체(말풍선)가 동작하는지 보이도록 안내 문구만 띄운다.
export function stubReact(s: Signal): Reaction | null {
  if (s.kind === "sent") return { utterance: "(아직 두뇌가 연결되지 않았어요)" };
  return null;
}
