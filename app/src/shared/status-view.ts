// 설정 창 상태·로그 탭에 보여 줄 줄을 만드는 순수 로직 (두뇌 스펙 v2 3.1). 화면 그리기는 settings-page.ts가 한다.
import type { BrainState, Judgement } from "./brain-protocol";

export type Row = { label: string; value: number; note?: string }; // value: 막대 길이 (0~1)
export type Section = { title: string; rows: Row[] };

const MOODS = ["심심함", "졸림", "들뜸", "시무룩", "분노", "궁금함", "놀람", "무서움", "행복"];
const HABITS: Record<string, string> = { poke: "찌르기", pet: "쓰다듬기", throw: "던지기", typing: "타이핑" };
const MOVES: Record<string, string> = { rest: "쉬기", sleep: "잠", roam: "돌아다니기", approach: "사용자 곁으로", play: "놀기", explore: "구경하기" };
export const REACTION_NAMES: Record<string, string> = { bored: "지루함", sleepy: "하품", excited: "신남", sad: "서운함", annoyed: "짜증", curious: "궁금함", surprised: "놀람", scared: "무서움", happy: "행복", none: "없음" };
export const ACTION_NAMES: Record<string, string> = { stand: "서기", sit: "앉기", lie_down: "엎드리기", sleep: "잠", beg: "조르기", bark: "짖기", none: "없음" };

const f2 = (x: number) => x.toFixed(2);
const signed = (x: number) => (x >= 0 ? "+" : "") + f2(x);

export function stateSections(s: BrainState): Section[] {
  const p = s.dog.personality;
  const total = Object.values(s.movement.weights).reduce((a, b) => a + b, 0) || 1;
  return [
    { title: "기분", rows: MOODS.map((d) => ({ label: d, value: s.dog.mood[d] })) },
    { title: "관계·말수", rows: [
      { label: "친밀도", value: s.dog.intimacy },
      // 말수는 말할 확률에 더하는 로짓 보정값이라 막대는 0~1로 눌러 보여 준다
      { label: "말수", value: 1 / (1 + Math.exp(-s.talkativeness)), note: `로짓 ${signed(s.talkativeness)}` },
    ] },
    { title: "성격 (기준값 / 기질)", rows: MOODS.map((d) => ({ label: d, value: p.baseline[d], note: `기질 ${f2(p.temperament[d])}` })) },
    { title: "민감도·변덕", rows: [...MOODS.map((d) => ({ label: d, value: p.sensitivity[d] })), { label: "변덕", value: p.whim }] },
    { title: "습관화", rows: Object.entries(HABITS).map(([k, name]) => ({ label: name, value: s.dog.habit[k] ?? 0 })) },
    { title: "평소 움직임 경향", rows: [
      ...Object.entries(MOVES).map(([k, name]) => ({ label: name, value: (s.movement.weights[k] ?? 0) / total })),
      { label: "달리기 비율", value: s.movement.run },
      { label: "머무는 시간 배율", value: Math.min(1, s.movement.idle_scale / 2), note: `×${f2(s.movement.idle_scale)}` },
    ] },
  ];
}

const clock = (ts: number) => new Date(ts * 1000).toTimeString().slice(0, 8);
const dist = (d: Record<string, number>, names: Record<string, string>) =>
  Object.entries(d).map(([k, v]) => `${names[k] ?? k} ${f2(v)}`).join(" ");
const event = (e: { 종류: string; 맥락?: Record<string, unknown> }) =>
  e.맥락 ? `${e.종류}(${Object.entries(e.맥락).map(([k, v]) => `${k} ${v}`).join(", ")})` : e.종류;

export function judgementLines(j: Judgement): string[] {
  const lines = [`${clock(j.ts)} · ${j.events.map(event).join(", ")}`];
  if (j.error) return [...lines, `  ${j.error}`];
  if (!j.jev || !j.model || !j.picked) return lines;
  if (j.jev.change) lines.push(`  변화  Jev ${dist(j.jev.change, {})}`);
  lines.push(`  반응  ${REACTION_NAMES[j.picked.reaction] ?? j.picked.reaction}${j.picked.reaction === "none" ? "" : " (가장 크게 오른 기분)"}`);
  lines.push(`  동작  Jev ${dist(j.jev.action, ACTION_NAMES)} → 보정 ${dist(j.model.action, ACTION_NAMES)} → ${ACTION_NAMES[j.picked.action] ?? j.picked.action}`);
  const said = j.picked.speak ? (j.utterance ? `말함: ${j.utterance}` : "말함") : "안 말함";
  lines.push(`  말하기  Jev ${f2(j.jev.speak)} → 최종 ${f2(j.model.speak)} → ${said}`);
  const change = Object.entries(j.mood_change ?? {});
  if (change.length) lines.push(`  기분  ${change.map(([k, v]) => `${k} ${signed(v)}`).join(", ")}`);
  return lines;
}
