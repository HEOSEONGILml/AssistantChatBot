// 설정 탭의 권한 모드 선택지. 문구는 다이제스트 6절.
import type { PermissionMode } from "./protocol";

export type ModeOption = { value: PermissionMode; title: string; en: string; desc: string; warn?: boolean };

export const PERMISSION_MODES: ModeOption[] = [
  { value: "default", title: "매번 묻기", en: "Manual", desc: "파일 수정·명령 실행 전에 매번 물어요" },
  { value: "acceptEdits", title: "수정은 바로", en: "Accept edits", desc: "파일 수정은 바로, 그 밖의 명령은 물어요" },
  { value: "plan", title: "계획만", en: "Plan", desc: "살펴보고 계획만 세워요. 바꾸지 않아요" },
  { value: "auto", title: "자동", en: "Auto", desc: "묻지 않고 진행해요. 실행 전에 안전 검사를 해요" },
  { value: "bypassPermissions", title: "묻지 않음", en: "Bypass permissions", desc: "아무것도 묻지 않아요. 격리된 환경에서만 쓰세요", warn: true },
];
