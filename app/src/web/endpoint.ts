// 웹 모드 두뇌는 페이지와 같은 출처에서 WebSocket(/ws)과 hello 토큰(/token)을 낸다 (0017)
export function brainUrls(loc: { protocol: string; host: string }): { ws: string; token: string } {
  return { ws: `${loc.protocol === "https:" ? "wss" : "ws"}://${loc.host}/ws`, token: "/token" };
}
