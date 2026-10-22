// 설정 탭(13·10): 계정, 화면 기록 스위치, 권한 모드. 값은 다이제스트 6절. 입력칸은 없다.
import type { Outgoing } from "../shared/protocol";
import type { State } from "../shared/state";
import { PERMISSION_MODES } from "../shared/settings";
import { h, switchButton } from "./dom";

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
      h("p", { class: "set-foot" }, "새로 맡기는 작업부터 적용돼요")));
  return out;
}
