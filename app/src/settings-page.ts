import { emit, listen } from "@tauri-apps/api/event";
import { loadSettings, saveSettings, type Settings } from "./shared/settings";
import type { AiStatus, BrainLog, BrainState } from "./shared/brain-protocol";
import { judgementLines, stateSections } from "./shared/status-view";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const msg = $("msg");
const KEYS = ["typesafe", "gemini"] as const;

const AI_STATE_TEXT: Record<AiStatus, string> = { ok: "정상", no_keys: "키를 넣어 주세요", bad_key: "키를 확인해 주세요" };
let aiStatus: AiStatus | null = null;
listen<AiStatus | null>("brain-status", (e) => {
  aiStatus = e.payload;
  $("ai-state").textContent = aiStatus ? AI_STATE_TEXT[aiStatus] : "두뇌에 연결되지 않음";
});

async function init() {
  const s = await loadSettings();
  ($("rest") as HTMLInputElement).checked = s.rest;
  ($("hideHouseWhenInside") as HTMLInputElement).checked = s.hideHouseWhenInside;
  ($("inputShortcut") as HTMLInputElement).value = s.inputShortcut;
  ($("houseShortcut") as HTMLInputElement).value = s.houseShortcut;
  await emit("brain-status-request");
}

$("save").addEventListener("click", async () => {
  msg.textContent = "";
  const s: Settings = {
    rest: ($("rest") as HTMLInputElement).checked,
    hideHouseWhenInside: ($("hideHouseWhenInside") as HTMLInputElement).checked,
    inputShortcut: ($("inputShortcut") as HTMLInputElement).value.trim(),
    houseShortcut: ($("houseShortcut") as HTMLInputElement).value.trim(),
  };
  try {
    const keys = KEYS.filter((k) => ($(k) as HTMLInputElement).value.trim());
    // 키는 두뇌가 보관한다. 두뇌에 연결되지 않았으면 보내지 못하므로 입력값을 그대로 둔다
    if (keys.length && aiStatus === null) throw new Error("두뇌에 연결되지 않아 키를 저장하지 못했어요");
    for (const k of keys) {
      await emit("brain-set-key", { name: k, value: ($(k) as HTMLInputElement).value.trim() });
      ($(k) as HTMLInputElement).value = "";
    }
    await saveSettings(s);
    await emit("settings-changed", s);
    msg.textContent = "저장했습니다.";
  } catch (e) {
    msg.textContent = `저장 실패: ${e}`;
  }
});

$("clear-history").addEventListener("click", async () => {
  if (!confirm("대화 기록을 모두 지울까요? 되돌릴 수 없어요.")) return;
  if (aiStatus === null) { msg.textContent = "두뇌에 연결되지 않아 지우지 못했어요"; return; }
  await emit("brain-clear-history");
  msg.textContent = "대화 기록을 지웠습니다.";
});

// 초기화: 강아지가 새 성격으로 다시 태어나고 기록도 지운다. 앱 설정과 API 키는 남는다
$("reset").addEventListener("click", async () => {
  if (!confirm("강아지를 초기화할까요? 지금 강아지의 성격·기분·친밀도와 대화 기록이 모두 사라지고 새 강아지가 태어나요. 되돌릴 수 없어요.")) return;
  if (aiStatus === null) { msg.textContent = "두뇌에 연결되지 않아 초기화하지 못했어요"; return; }
  await emit("brain-reset");
  msg.textContent = "새 강아지가 태어났습니다.";
});

// 상태·로그 탭 (두뇌 스펙 v2 3.1): 열려 있는 동안 2초마다 두뇌에 조회한다. 캐릭터 창이 두뇌와 이어 준다
type Tab = "settings" | "status" | "log";
let tab: Tab = "settings";
const tabButtons = document.querySelectorAll<HTMLButtonElement>("nav button");
const showTab = (t: Tab) => {
  tab = t;
  tabButtons.forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  for (const name of ["settings", "status", "log"] as const) $(`tab-${name}`).hidden = name !== t;
  refresh();
};
tabButtons.forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab as Tab)));
const refresh = () => {
  if (tab === "status") emit("brain-state-request");
  if (tab === "log") emit("brain-log-request");
  if (tab !== "settings" && aiStatus === null) $(`tab-${tab}`).innerHTML = '<p class="muted">두뇌에 연결되지 않음</p>';
};
setInterval(refresh, 2000);

const NL = "\n";
const escapeHtml = (t: string) => t.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
listen<BrainState>("brain-state", (e) => {
  if (tab !== "status") return;
  $("tab-status").innerHTML = stateSections(e.payload).map((sec) =>
    `<div class="section"><h3>${sec.title}</h3>` + sec.rows.map((r) =>
      `<div class="row"><span>${r.label}</span><div class="bar"><div style="width:${Math.round(Math.max(0, Math.min(1, r.value)) * 100)}%"></div></div>` +
      `<span class="num">${r.value.toFixed(2)}${r.note ? " · " + r.note : ""}</span></div>`).join("") + "</div>").join("");
});
listen<BrainLog>("brain-log", (e) => {
  if (tab !== "log") return;
  const judgements = [...e.payload.judgements].reverse().map((j) => judgementLines(j).join(NL)).join(NL + NL);
  $("tab-log").innerHTML =
    `<div class="section"><h3>판단 (최근 것부터)</h3><pre>${escapeHtml(judgements || "아직 판단이 없습니다")}</pre></div>` +
    `<div class="section"><h3>이벤트 기록 (최근 것부터)</h3><pre>${escapeHtml([...e.payload.events].reverse().join(NL))}</pre></div>` +
    `<div class="section"><h3>두뇌 실행 로그 (마지막 30줄)</h3><pre class="muted">${escapeHtml(e.payload.brain_log.join(NL))}</pre></div>`;
});

// 단축키 등록이 실패하면 강아지 화면이 이전 값으로 되돌려 저장한다. 화면의 값도 다시 읽는다
listen<string>("shortcut-error", async (e) => { await init(); msg.textContent = e.payload; });
init();
