// 상세 창(12): 주 창이 보내 준 세션 하나의 대화를 크게 그린다. 말하기·멈추기는 주 창에 넘겨 백엔드로 보낸다.
import "./ui/styles.css";
import { emitTo, listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import type { Entry, Outgoing, Session } from "./shared/protocol";
import { STATE_TEXT, type Activity, type View } from "./shared/state";
import { clockText } from "./shared/forms";
import { renderConversation } from "./ui/conversation";
import { h, svg } from "./ui/dom";

const SOURCE_TEXT: Record<Session["source"], string> = { user: "내 요청", schedule: "스케줄", chat: "대화" };
const STOP_ICON = `<svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2" fill="#B42318"/></svg>`;

const root = document.getElementById("detail")!;
const headSlot = h("div", { class: "detail-head-slot" });
const convHost = h("div", { class: "conv-host" });
root.replaceChildren(headSlot, convHost);

let sessionId: number | null = null;
let title = "";
let connected = false; // 주 창이 백엔드에 붙어 있는지 (detail-data에 함께 온다)

const toMain = (event: string, payload: unknown) =>
  emitTo("main", event, payload).catch((e) => console.warn("주 창에 보내기 실패", e));

// 대화 화면은 say만 보낸다. 끊겼으면 false: 입력 글을 지우지 않고 선택지도 막지 않는다
const send = (m: Outgoing) => {
  if (!connected) return false;
  if (m.type === "say") toMain("detail-say", { sessionId: m.session_id, text: m.text });
  return true;
};
const go = (v: View) => toMain("detail-go", v);

function setTitle(t: string) {
  if (t === title) return;
  title = t;
  document.title = t;
  getCurrentWindow().setTitle(t).catch((e) => console.warn("제목 바꾸기 실패", e));
}

function head(t: Session): HTMLElement {
  const live = t.state === "working" || t.state === "waiting";
  return h("div", { class: "detail-head" },
    h("div", { class: "detail-head-main" },
      h("h1", {}, t.title),
      h("div", { class: "detail-sub" },
        h("span", { class: `detail-src src-${t.source}` }, SOURCE_TEXT[t.source]),
        h("span", {}, `${clockText(t.created_at)} 시작 · `, h("span", { class: t.state === "waiting" ? "sub-ask" : "" }, STATE_TEXT[t.state])))),
    live ? h("button", { type: "button", class: "detail-stop", onClick: () => toMain("detail-stop", { sessionId: t.id }) }, svg(STOP_ICON), "멈추기") : null);
}

// 보고 있으면(창이 앞에 있으면) 주 창에 알려 seen을 보내게 한다
function seenIfFocused() {
  if (sessionId !== null && document.hasFocus()) toMain("detail-seen", { sessionId });
}

function draw(session: Session, entries: Entry[], activity: Activity | undefined) {
  setTitle(`작업 — ${session.title}`);
  headSlot.replaceChildren(head(session));
  renderConversation(convHost, { session, entries, activity, height: 0, compact: false }, send, go);
  seenIfFocused();
}

window.addEventListener("focus", seenIfFocused);

Promise.all([
  listen<number>("detail-open", (e) => {
    if (sessionId === e.payload) return;
    sessionId = e.payload;
    setTitle("작업");
    headSlot.replaceChildren();
    convHost.replaceChildren(h("p", { class: "empty" }, "불러오는 중…"));
  }),
  // 주 창이 못 보냈다고 알리면 입력칸이 비어 있을 때 글을 되돌린다
  listen<string>("detail-send-failed", (e) => {
    const area = convHost.querySelector("textarea");
    if (area && !area.value) { area.value = e.payload; area.dispatchEvent(new Event("input")); }
  }),
  listen<{ session: Session; entries: Entry[]; connected: boolean; activity?: Activity }>("detail-data", (e) => {
    const { session, entries, activity } = e.payload;
    connected = e.payload.connected;
    if (sessionId !== null && session.id !== sessionId) return;
    sessionId = session.id;
    draw(session, entries, activity);
  }),
]).then(() => toMain("detail-ready", null));
