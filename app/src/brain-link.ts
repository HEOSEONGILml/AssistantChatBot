// 두뇌와의 WebSocket 연결 하나. 끊기거나 접속하지 못하면 두뇌를 띄우고(이미 떠 있으면 그대로) 다시 접속한다.
import { invoke } from "@tauri-apps/api/core";
import { outgoing, parseBrainMessage, type BrainMessage, type Outgoing } from "./shared/brain-protocol";

const RETRY_MS = 2000; // 잠정값: 다시 접속하는 간격 (두뇌 스펙 9절)

type Handlers = { onMessage(m: BrainMessage): void; onOpen(): void; onClose(): void };

export function connectBrain(h: Handlers): { send(msg: Outgoing): boolean } {
  let ws: WebSocket | null = null;

  const retry = () => {
    invoke("brain_start").catch((e) => console.warn("두뇌 실행 실패", e));
    setTimeout(attempt, RETRY_MS);
  };

  const attempt = async () => {
    let ep: { port: number; token: string };
    try { ep = await invoke("brain_endpoint"); } catch { retry(); return; }
    const sock = new WebSocket(`ws://127.0.0.1:${ep.port}`);
    sock.onopen = () => { ws = sock; sock.send(outgoing({ type: "hello", token: ep.token })); h.onOpen(); };
    sock.onmessage = (e) => { const m = parseBrainMessage(e.data); if (m) h.onMessage(m); };
    sock.onclose = () => {
      if (ws === sock) { ws = null; h.onClose(); }
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
