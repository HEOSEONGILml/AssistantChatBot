// 웹 모드 두뇌와의 WebSocket 연결 하나. 같은 출처에서 토큰을 받아 hello하고, 끊기면 2초마다 다시 접속한다.
// 다른 탭이 연결을 가져가면(4002) 다시 접속하지 않는다: 두 탭이 서로를 끝없이 밀어내 대답이 엉뚱한 탭으로 간다 (2026-10-20)
// PC 앱(brain-link.ts)과 달리 두뇌를 띄우지 않는다: 웹 모드 두뇌가 이 페이지를 내보내고 있다 (0017)
import { outgoing, parseBrainMessage, type BrainMessage, type Outgoing } from "../shared/brain-protocol";
import { brainUrls } from "./endpoint";

const RETRY_MS = 2000;
const CLOSE_REPLACED = 4002;

export const retryAfterClose = (code: number) => code !== CLOSE_REPLACED;

type Handlers = { onMessage(m: BrainMessage): void; onOpen(): void; onClose(replaced: boolean): void };

export function connectWebBrain(h: Handlers): { send(msg: Outgoing): boolean } {
  let ws: WebSocket | null = null;
  const urls = brainUrls(location);

  const attempt = async () => {
    let token: string;
    try {
      token = (await (await fetch(urls.token, { cache: "no-store" })).json()).token;
    } catch {
      setTimeout(attempt, RETRY_MS);
      return;
    }
    const sock = new WebSocket(urls.ws);
    sock.onopen = () => { ws = sock; sock.send(outgoing({ type: "hello", token })); h.onOpen(); };
    sock.onmessage = (e) => { const m = parseBrainMessage(e.data); if (m) h.onMessage(m); };
    sock.onclose = (e) => {
      const retry = retryAfterClose(e.code);
      if (ws === sock) { ws = null; h.onClose(!retry); }
      if (retry) setTimeout(attempt, RETRY_MS);
    };
  };

  attempt();
  return {
    send(msg) {
      if (!ws || ws.readyState !== WebSocket.OPEN) return false;
      ws.send(outgoing(msg));
      return true;
    },
  };
}
