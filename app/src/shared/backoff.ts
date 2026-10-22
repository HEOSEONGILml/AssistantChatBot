// 백엔드 다시 접속 간격과 다시 접속하지 않을 닫힘 코드. 값은 잠정값(근거: 처음엔 빨리, 오래 안 붙으면 부담을 줄인다)
export const RETRY_MIN_MS = 2000;
export const RETRY_MAX_MS = 30000;

export const nextDelay = (ms: number): number => Math.min(ms * 2, RETRY_MAX_MS);

// 4001 토큰 틀림, 4002 다른 화면이 교체, 4003 프로토콜 버전 다름 (docs/backend-protocol.md)
export const noRetry = (code: number): boolean => code >= 4001 && code <= 4003;
