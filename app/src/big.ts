// 큰 창(12): 주 창이 넘겨 준 상태(big-state)를 그린다. 큰 창은 백엔드에 따로 붙지 않는다(백엔드는 화면 연결을 하나만 받는다).
// 화면을 바꾸면 big-go, 보낼 메시지는 big-send로 주 창에 맡긴다. 주 창이 못 보냈으면 big-send-failed가 온다.
import "./ui/styles.css";
import { emitTo, listen } from "@tauri-apps/api/event";
import { answered, pruneAnswered } from "./shared/entries";
import type { Outgoing } from "./shared/protocol";
import { fromSnapshot, needsSeen, type Snapshot, type State, type View } from "./shared/state";
import { renderBig } from "./ui/big";
import { clearDraft } from "./ui/schedule";

const root = document.getElementById("big")!;
let state: State | null = null;

const toMain = (event: string, payload: unknown) =>
  emitTo("main", event, payload).catch((e) => console.warn("주 창에 보내기 실패", e));

// 끊겼으면 false: 입력 글을 지우지 않고 선택지도 막지 않는다. 보낸 뒤 실패는 big-send-failed로 온다
const send = (m: Outgoing) => {
  if (!state?.connected) return false;
  toMain("big-send", m);
  return true;
};
// [고치기]로 여는 수정 화면은 남은 적던 값 없이 등록 확인 값으로 채운다 (주 창 go와 같음)
const go = (v: View) => {
  if (v.proposal) clearDraft();
  toMain("big-go", v);
};

// 보고 있는(창이 앞에 있는) 끝난 세션은 seen. 같은 세션을 두 번 보내지 않는 것은 주 창이 맡는다
function seenIfFocused() {
  const v = state?.view;
  if (!state || !v || !document.hasFocus()) return;
  if ((v.screen === "task" || v.screen === "schedule") && v.sessionId !== undefined && needsSeen(state, v.sessionId)) {
    toMain("big-send", { type: "seen", session_id: v.sessionId });
  }
}

window.addEventListener("focus", seenIfFocused);

Promise.all([
  listen<Snapshot>("big-state", (e) => {
    const s = fromSnapshot(e.payload);
    state = s;
    if (!s.connected) answered.clear();
    pruneAnswered(answered, (id) => s.sessions.get(id)?.state === "waiting");
    renderBig(root, s, send, go);
    seenIfFocused();
  }),
  // 주 창이 못 보낸 말은 입력칸이 비어 있을 때 되돌린다
  listen<Outgoing>("big-send-failed", (e) => {
    const m = e.payload;
    if (m.type !== "say") return;
    const area = root.querySelector<HTMLTextAreaElement>(".conv-input");
    if (area && !area.value) { area.value = m.text; area.dispatchEvent(new Event("input")); }
  }),
]).then(() => toMain("big-ready", null));
