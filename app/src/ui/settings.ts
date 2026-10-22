// 설정 탭(13·10): 계정, 화면 기록 스위치, 권한 모드, 먼저 말 걸기 Jev 키. 값은 다이제스트 6절.
// Jev 키 입력칸은 양식처럼 입력 중에 다시 그리지 않는다(panel.ts formKey)
import type { Outgoing } from "../shared/protocol";
import type { State } from "../shared/state";
import { PERMISSION_MODES } from "../shared/settings";
import { bytesText } from "../shared/forms";
import { h, switchButton } from "./dom";
import { openConfirm } from "./panel";

type Send = (m: Outgoing) => unknown;

function account(s: State, send: Send): HTMLElement {
  if (s.loggedIn === false) {
    return h("section", { class: "set-sec set-account" },
      h("div", { class: "set-main" },
        h("span", { class: "set-label" }, "계정"),
        h("span", { class: "set-line" }, h("span", { class: "dot dot-off", "aria-hidden": "true" }), "로그인 안 됨"),
        h("span", { class: "set-note" }, "Claude Code 구독 계정으로 로그인해야 일을 할 수 있어요")),
      h("button", { type: "button", class: "btn-primary btn-login", disabled: !s.connected || s.loggingIn, onClick: () => send({ type: "login" }) },
        s.loggingIn ? "로그인하는 중…" : "로그인"));
  }
  return h("section", { class: "set-sec set-account" },
    h("div", { class: "set-main" },
      h("span", { class: "set-label" }, "계정"),
      h("span", { class: "set-line" }, h("span", { class: "dot dot-on", "aria-hidden": "true" }),
        s.loggedIn === null ? "확인하는 중…" : "로그인됨 · Claude Code 구독")),
    s.loggedIn === null ? null
      : h("button", { type: "button", class: "btn-secondary btn-logout", disabled: !s.connected, onClick: () => send({ type: "logout" }) }, "로그아웃"));
}

export function settingsBody(s: State, send: Send): Node[] {
  const st = s.settings;
  const out: Node[] = [account(s, send)];
  if (!st) return [...out, h("p", { class: "empty" }, "불러오는 중…")];
  out.push(
    h("section", { class: "set-sec set-rec" },
      h("div", { class: "set-main" },
        h("span", { class: "set-line" }, "화면 기록 ", h("span", { class: "set-sub" }, "screenpipe")),
        h("span", { class: "set-note" }, "끄면 “아까 본 그거”를 찾지 못해요")),
      switchButton({
        on: st.recording, label: "화면 기록", disabled: !s.connected,
        onToggle: () => send({ type: "set_recording", enabled: !st.recording }),
      })),
    recordingFolder(s, send),
    h("fieldset", { class: "set-sec set-modes" },
      h("legend", { class: "sr-only" }, "권한 모드"),
      ...PERMISSION_MODES.map((m) => h("label", { class: m.value === st.permissionMode ? "mode mode-on" : "mode" },
        h("input", {
          type: "radio", name: "permission-mode", value: m.value, checked: m.value === st.permissionMode, disabled: !s.connected,
          onChange: () => send({ type: "set_permission_mode", mode: m.value }),
        }),
        h("span", { class: "mode-text" },
          h("span", { class: "mode-title" }, m.title, " ", h("span", { class: "set-sub" }, m.en)),
          h("span", { class: m.warn ? "mode-desc mode-warn" : "mode-desc" }, m.desc)))),
      h("p", { class: "set-foot" }, "새로 맡기는 작업부터 적용돼요")),
    jevKey(s, send));
  return out;
}

// 기록 폴더 줄(13): 용량·경로와 [비우기]. [비우기]는 25번 확인을 거친다. 끊겼으면 막는다
function recordingFolder(s: State, send: Send): HTMLElement {
  const st = s.settings!;
  const size = bytesText(st.recordingBytes);
  const ask = (e: Event) => {
    const root = (e.currentTarget as HTMLElement).closest(".panel, .big") as HTMLElement | null;
    if (!root) return;
    openConfirm(root, undefined, {
      title: "화면 기록을 모두 비울까요?",
      body: ["기록 폴더의 ", h("b", {}, size), "가 지워져요. 지금까지 본 화면을 찾지 못하게 돼요. 되돌릴 수 없어요. 화면 기록은 켜진 그대로 이어서 쌓여요."],
      action: "비우기",
      run: () => send({ type: "clear_recording" }),
    });
  };
  return h("section", { class: "set-sec set-folder" },
    h("div", { class: "set-main" },
      h("span", { class: "set-note" }, "기록 폴더 · ", h("b", { class: "set-size" }, size), " · 이틀 지난 기록은 저절로 지워져요"),
      h("span", { class: "set-path", title: st.recordingDir }, st.recordingDir)),
    h("button", { type: "button", class: "btn-secondary btn-clear", disabled: !s.connected, onClick: ask }, "비우기"));
}

let jevDraft = ""; // Jev 키 입력 글. 다시 그려도 남는다. 로그에 찍지 않는다

// 먼저 말 걸기 칸: Jev API 키 비밀번호 입력 + [저장]. 저장돼 있으면 "입력됨". 빈 값 저장은 키 지우기.
// 보내기에 성공하면 입력칸을 비운다(못 보냈으면 글을 둔다)
function jevKey(s: State, send: Send): HTMLElement {
  const input = h("input", {
    id: "jev-key", class: "set-jev-input", type: "password", autocomplete: "off", spellcheck: "false", disabled: !s.connected,
    onInput: (e) => { jevDraft = (e.target as HTMLInputElement).value; },
  }) as HTMLInputElement;
  input.value = jevDraft;
  // 다시 그릴 때(열쇠가 바뀜) 옛 입력칸에 커서가 있었으면 새 입력칸에 초점과 선택 범위를 되돌린다.
  // 이 함수는 옛 입력칸을 치우기 전에 불리므로 옛 칸의 초점·커서를 여기서 읽을 수 있다
  const old = document.getElementById("jev-key") as HTMLInputElement | null;
  if (old && old === document.activeElement) {
    const [start, end] = [old.selectionStart, old.selectionEnd];
    queueMicrotask(() => {
      if (!input.isConnected) return;
      input.focus();
      if (start !== null && end !== null) input.setSelectionRange(start, end);
    });
  }
  const save = (e: Event) => {
    e.preventDefault();
    if (send({ type: "set_jev_key", key: input.value }) === false) return;
    jevDraft = "";
    input.value = "";
  };
  return h("section", { class: "set-sec set-jev" },
    h("span", { class: "set-label" }, "먼저 말 걸기"),
    h("span", { class: "set-line" },
      h("label", { for: "jev-key" }, "Jev API 키"),
      ...(s.settings?.jevKeySet ? [h("span", { class: "dot dot-on", "aria-hidden": "true" }), h("span", { class: "set-sub" }, "입력됨")] : [])),
    h("form", { class: "set-jev-form", onSubmit: save },
      input,
      h("button", { type: "submit", class: "btn-secondary btn-save", disabled: !s.connected }, "저장")));
}
