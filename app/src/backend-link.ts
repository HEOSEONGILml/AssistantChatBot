// 백엔드와의 WebSocket 연결 하나. 끊기거나 접속하지 못하면 백엔드를 띄우고(이미 떠 있으면 그대로) 다시 접속한다.
// 다시 접속하는 간격은 2초에서 두 배씩 30초까지 늘고, 붙으면 2초로 돌아간다.
import { invoke } from "@tauri-apps/api/core";
import { outgoing, parseBackendMessage, type BackendMessage, type Outgoing } from "./shared/protocol";
import { nextDelay, noRetry, RETRY_MIN_MS } from "./shared/backoff";

type Handlers = { onMessage(m: BackendMessage): void; onOpen(): void; onClose(): void };

export function connectBackend(h: Handlers): { send(msg: Outgoing): boolean } {
  let ws: WebSocket | null = null;
  let delay = RETRY_MIN_MS;

  const retry = () => {
    invoke("backend_start").catch((e) => console.warn("백엔드 실행 실패", e));
    setTimeout(attempt, delay);
    delay = nextDelay(delay);
  };

  const attempt = async () => {
    let ep: { port: number; token: string };
    try { ep = await invoke("backend_endpoint"); } catch { retry(); return; }
    const sock = new WebSocket(`ws://127.0.0.1:${ep.port}`);
    sock.onopen = () => { ws = sock; delay = RETRY_MIN_MS; sock.send(outgoing({ type: "hello", token: ep.token })); h.onOpen(); };
    sock.onmessage = (e) => { const m = parseBackendMessage(e.data); if (m) h.onMessage(m); };
    sock.onclose = (e) => {
      if (ws === sock) { ws = null; h.onClose(); }
      // 백엔드가 일부러 닫았다(토큰·교체·버전): 다시 띄워도 소용없다
      if (noRetry(e.code)) { console.warn("백엔드가 연결을 닫음", e.code); return; }
      retry();
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
