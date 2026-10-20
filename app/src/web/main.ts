// 웹 프로토타입 화면 (웹 프로토타입 스펙, 0017). 브라우저 창 안이 강아지의 세계다.
// 몸 로직(body/*)과 프로토콜은 PC 앱과 같다. 그리기는 character.ts와 같은 방식을 따로 둔다(프로토타입 빚, 스펙 6절).
import { frameAt, opaqueTop, sheetImage, type Manifest } from "../body/sprite";
import { newDog, step, playAction, toggleHouse, currentAnimation, grab, holdAt, release, poke, type Dog, type World, DEFAULT_MOVEMENT, listenTo, type Movement } from "../body/dog";
import { newPetting, feedPetting } from "../body/petting";
import { showBubble, tickBubble, type Bubble } from "../body/bubble";
import { boxContains, type Box } from "../body/coords";
import { drawHouse, HOUSE_PX, drawChatIcon, CHAT_PX, drawGearIcon, GEAR_PX } from "../body/house";
import { ACTION_TO_DOG, type AiStatus, type BrainLog, type BrainMessage, type BrainState, type EventContext, type EventKind } from "../shared/brain-protocol";
import { stateSections, judgementLines } from "../shared/status-view";
import { newTyping, feedTyping, tickTyping, quietDue, impactOf } from "../body/events";
import { EMOTES, MOOD_IDS, REACTION_MS, faceMood, moodStyle, reactionHop, type MoodId, type ReactionId } from "../body/mood-style";
import { connectWebBrain } from "./link";
import { newPresence, noteInput, setHidden, idleMs, AWAY_MS } from "./presence";
import { loadPrefs, savePrefs, type Prefs } from "./prefs";
import "../styles.css";
import "./web.css";

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const canvas = $<HTMLCanvasElement>("stage");
const ctx = canvas.getContext("2d")!;
const bubbleEl = $("bubble");
const talkbar = $("talkbar"), talk = $<HTMLInputElement>("talk"), panel = $("panel");

const HOUSE_SCALE = 3, ICON_GAP = 10, BUBBLE_GAP = 10, MARGIN = 16;
const TALK_W = 380, TALK_GAP = 8; // PC 입력창(tauri.conf.json input 380×56)처럼 집 위에 작게 뜬다
const ACTION_MS = 2500, WALK_SPEED = 70, RUN_SPEED = 180, PET_MS = 2000; // character.ts와 같은 값
const DRAG_START_PX = 6, THROW_SAMPLE_MS = 80;

// 웹의 AI 상태 안내 (PC 문구는 트레이를 가리킨다)
const statusText = (ai: AiStatus | null) =>
  ai === "no_keys" ? "톱니바퀴 → 설정에서 키를 넣어 주세요" : ai === "bad_key" ? "키를 확인해 주세요 (톱니바퀴 → 설정)" : null;

async function main() {
  const manifest: Manifest = await (await fetch("/sprites/dog/manifest.json")).json();
  type Frame = { canvas: HTMLCanvasElement; top: number };
  const frames = new Map<string, Frame>();
  const loadSheet = (src: string) => {
    const sheet = new Image();
    sheet.onload = () => {
      const full = document.createElement("canvas");
      full.width = sheet.width; full.height = sheet.height;
      const fctx = full.getContext("2d")!;
      fctx.drawImage(sheet, 0, 0);
      const alpha = fctx.getImageData(0, 0, sheet.width, sheet.height).data;
      for (const a of Object.values(manifest.animations)) {
        for (let i = 0; i < a.frames; i++) {
          const r = { sx: ((a.col ?? 0) + i) * manifest.frameWidth, sy: a.row * manifest.frameHeight, sw: manifest.frameWidth, sh: manifest.frameHeight };
          const c = document.createElement("canvas");
          c.width = r.sw; c.height = r.sh;
          c.getContext("2d")!.drawImage(full, r.sx, r.sy, r.sw, r.sh, 0, 0, r.sw, r.sh);
          frames.set(`${src}|${r.sx},${r.sy}`, { canvas: c, top: opaqueTop(alpha, sheet.width, r) });
        }
      }
    };
    sheet.src = src;
  };
  for (const src of new Set(MOOD_IDS.map((id) => sheetImage(manifest, id)))) loadSheet(src);
  let headTop = 0;

  const dogW = manifest.frameWidth * manifest.scale, dogH = manifest.frameHeight * manifest.scale;
  const houseW = HOUSE_PX.width * HOUSE_SCALE, houseH = HOUSE_PX.height * HOUSE_SCALE;
  const chatW = CHAT_PX.width * HOUSE_SCALE, chatH = CHAT_PX.height * HOUSE_SCALE;
  const gearW = GEAR_PX.width * HOUSE_SCALE, gearH = GEAR_PX.height * HOUSE_SCALE;
  // 세계 = 브라우저 창. 입력창은 집 위에 떠 있어 세계를 줄이지 않는다
  let houseBox: Box, chatBox: Box, gearBox: Box, world: World;
  const layout = () => {
    canvas.width = window.innerWidth; canvas.height = window.innerHeight;
    ctx.imageSmoothingEnabled = false;
    const h = window.innerHeight;
    houseBox = { left: window.innerWidth - houseW - 40, top: h - houseH - MARGIN, width: houseW, height: houseH };
    chatBox = { left: houseBox.left - chatW - ICON_GAP, top: h - chatH - MARGIN - 4, width: chatW, height: chatH };
    gearBox = { left: chatBox.left - gearW - ICON_GAP, top: h - gearH - MARGIN - 4, width: gearW, height: gearH };
    world = { width: window.innerWidth, height: h - MARGIN, dogWidth: dogW, dogHeight: dogH,
      houseX: houseBox.left + houseW / 2 - dogW / 2, houseY: h - MARGIN - dogH, walkSpeed: WALK_SPEED, runSpeed: RUN_SPEED };
    // 입력창: 집 오른쪽 끝에 맞춰 집 위에 (PC placeAbove와 같은 규칙), 화면 밖으로 나가지 않게
    const talkW = Math.min(TALK_W, window.innerWidth - 2 * MARGIN);
    talkbar.style.width = `${talkW}px`;
    talkbar.style.left = `${Math.max(MARGIN, houseBox.left + houseW - talkW)}px`;
    talkbar.style.bottom = `${h - houseBox.top + TALK_GAP}px`;
  };
  layout();
  window.addEventListener("resize", layout);

  let dog: Dog = newDog(window.innerWidth / 3, world!.height - dogH);
  let bubble: Bubble = null;
  let prefs: Prefs = loadPrefs(localStorage);
  let dogHouseSince: number | null = null;
  let cursor: { x: number; y: number } | null = null;
  let petting = newPetting();
  let lastClick: { x: number; y: number; t: number } | null = null;
  let press: { x: number; y: number; offX: number; offY: number; samples: { x: number; y: number; t: number }[] } | null = null;
  let last = performance.now(), animStart = last, lastAnim = currentAnimation(dog);

  const dogBox = (): Box => ({ left: dog.x, top: dog.y, width: dogW, height: dogH });
  const houseVisible = () => !(prefs.hideHouseWhenInside && dog.mode === "in_house");
  const home = () => dog.mode === "in_house" || dog.mode === "to_house";
  const overIcons = (p: { x: number; y: number }) =>
    houseVisible() && (boxContains(houseBox, p) || boxContains(chatBox, p) || boxContains(gearBox, p));

  // ---- 두뇌 ----
  let aiStatus: AiStatus | null = null;
  let movement: Movement = DEFAULT_MOVEMENT;
  let mood: MoodId = "calm";
  let shownReaction: { id: ReactionId; at: number } | null = null;
  const say = (text: string) => { bubble = showBubble(text); bubbleEl.textContent = text; };
  const setStatus = (s: AiStatus | null) => { aiStatus = s; $("ai-state").textContent = s === null ? "두뇌에 연결되지 않음" : s === "ok" ? "정상" : statusText(s)!; };
  const onBrain = (m: BrainMessage) => {
    if (m.type === "movement") { movement = m.movement; mood = m.mood; return; }
    if (m.type === "state") { renderState(m.state); return; }
    if (m.type === "log") { renderLog(m.log); return; }
    if (m.type === "status") { setStatus(m.ai); const t = statusText(m.ai); if (t && !home()) say(t); return; }
    if (home()) return; // 집에서는 완전히 조용 (vision)
    if (m.reaction) shownReaction = { id: m.reaction, at: Date.now() };
    if (m.action) dog = playAction(dog, ACTION_TO_DOG[m.action], Date.now(), ACTION_MS);
    if (m.utterance) { say(m.utterance); sendEvent("dog_spoke", { text: m.utterance }); }
  };
  const brain = connectWebBrain({ onMessage: onBrain, onOpen: () => {}, onClose: () => setStatus(null) });
  setStatus(null);

  let lastEventAt = Date.now();
  const sendEvent = (kind: EventKind, context: EventContext = {}) => {
    if (home() && kind !== "house_in" && kind !== "house_out") return;
    lastEventAt = Date.now();
    brain.send({ type: "event", kind, context });
  };

  // ---- 집, 입력줄, 설정 패널 ----
  const showTalk = (on: boolean) => {
    talkbar.hidden = !on;
    if (on) talk.focus();
  };
  const doToggleHouse = () => {
    const before = dog.mode;
    dog = toggleHouse(dog, Date.now());
    if (before === "in_house") sendEvent("house_out", { away_seconds: Math.round((Date.now() - (dogHouseSince ?? Date.now())) / 1000) });
    if (dog.mode === "to_house") { bubble = null; bubbleEl.hidden = true; showTalk(false); }
  };
  const toggleTalk = () => { if (!home()) showTalk(talkbar.hidden !== false); };

  let typing = newTyping();
  talk.addEventListener("input", () => {
    const starting = !typing.text;
    const r = feedTyping(typing, talk.value, Date.now());
    if (starting || r.fire) dog = listenTo(dog, world, world.houseX + dogW / 2, world.houseY, Date.now(), Math.random); // 듣는 자세
    typing = r.state;
    if (r.fire) sendEvent("typing", { text: typing.text });
  });
  talk.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") { showTalk(false); return; }
    if (ev.key !== "Enter" || ev.isComposing || !talk.value.trim()) return;
    typing = newTyping();
    sendEvent("message", { text: talk.value.trim() });
    talk.value = "";
  });

  // 설정 패널: 열려 있는 동안 상태·로그 탭은 2초마다 두뇌에 조회한다
  type Tab = "settings" | "status" | "log";
  let tab: Tab = "settings";
  const tabButtons = panel.querySelectorAll<HTMLButtonElement>("nav button");
  const showTab = (t: Tab) => {
    tab = t;
    tabButtons.forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
    for (const name of ["settings", "status", "log"] as const) $(`tab-${name}`).hidden = name !== t;
    refreshPanel();
  };
  tabButtons.forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab as Tab)));
  const refreshPanel = () => {
    if (panel.hidden) return;
    if (tab === "status") brain.send({ type: "get_state" });
    if (tab === "log") brain.send({ type: "get_log" });
  };
  setInterval(refreshPanel, 2000);
  const NL = "\n";
  const renderState = (s: BrainState) => {
    if (tab !== "status") return;
    $("tab-status").querySelector("pre")!.textContent = stateSections(s).map((sec) =>
      `[${sec.title}]` + NL + sec.rows.map((r) => `${r.label.padEnd(8)} ${r.value.toFixed(2)}${r.note ? " · " + r.note : ""}`).join(NL)).join(NL + NL);
  };
  const renderLog = (l: BrainLog) => {
    if (tab !== "log") return;
    const js = [...l.judgements].reverse().map((j) => judgementLines(j).join(NL)).join(NL + NL);
    $("tab-log").querySelector("pre")!.textContent = `[판단, 최근 것부터]${NL}${js || "아직 판단이 없습니다"}${NL}${NL}[이벤트 기록]${NL}${[...l.events].reverse().join(NL)}`;
  };
  const msg = $("msg");
  const openPanel = () => {
    panel.hidden = false;
    $<HTMLInputElement>("rest").checked = prefs.rest;
    $<HTMLInputElement>("hideHouseWhenInside").checked = prefs.hideHouseWhenInside;
    refreshPanel();
  };
  $("panel-close").addEventListener("click", () => { panel.hidden = true; });
  for (const k of ["rest", "hideHouseWhenInside"] as const) {
    $<HTMLInputElement>(k).addEventListener("change", (e) => {
      const on = (e.target as HTMLInputElement).checked;
      prefs = k === "rest" ? { ...prefs, rest: on } : { ...prefs, hideHouseWhenInside: on };
      savePrefs(localStorage, prefs);
    });
  }
  $("save-keys").addEventListener("click", () => {
    let sent = 0;
    for (const name of ["typesafe", "gemini"] as const) {
      const input = $<HTMLInputElement>(name);
      if (input.value.trim() && brain.send({ type: "set_key", name, value: input.value.trim() })) sent++;
      input.value = "";
    }
    msg.textContent = sent ? "키를 보냈습니다." : aiStatus === null ? "두뇌에 연결되지 않았어요" : "새 키를 입력해 주세요";
  });
  $("clear-history").addEventListener("click", () => {
    if (!confirm("대화 기록을 모두 지울까요? 되돌릴 수 없어요.")) return;
    msg.textContent = brain.send({ type: "clear_history" }) ? "대화 기록을 지웠습니다." : "두뇌에 연결되지 않아 지우지 못했어요";
  });
  $("reset").addEventListener("click", () => {
    if (!confirm("강아지를 초기화할까요? 기분과 대화 기록이 모두 사라지고 처음 상태로 돌아가요.")) return;
    msg.textContent = brain.send({ type: "reset" }) ? "새 강아지가 태어났습니다." : "두뇌에 연결되지 않아 초기화하지 못했어요";
  });

  // ---- 자리 비움 (웹: 이 페이지 안 입력과 탭 숨김) ----
  let presence = newPresence(Date.now());
  let userActive = true, awayMs = 0;
  for (const ev of ["pointermove", "pointerdown", "keydown", "wheel"]) {
    window.addEventListener(ev, () => { presence = noteInput(presence, Date.now()); }, { passive: true });
  }
  document.addEventListener("visibilitychange", () => { presence = setHidden(presence, document.hidden, Date.now()); });
  setInterval(() => {
    const idle = idleMs(presence, Date.now());
    const active = idle < AWAY_MS;
    if (!active) awayMs = idle;
    if (active && !userActive) sendEvent("returned", { away_seconds: Math.round(awayMs / 1000) });
    userActive = active;
  }, 1000);
  // 타이핑 멈춤과 조용함은 시간이 지나야 알 수 있어 주기적으로 본다
  setInterval(() => {
    const now = Date.now();
    const r = tickTyping(typing, now);
    typing = r.state;
    if (r.fire) sendEvent("typing", { text: typing.text });
    if (quietDue(lastEventAt, now, userActive)) sendEvent("quiet", { seconds: Math.round((now - lastEventAt) / 1000) });
  }, 100);

  // ---- 몸 상호작용: 짧게 누르면 찌르기, 끌면 잡기, 놓으면 던지기, 누르지 않고 문지르면 쓰다듬기 ----
  canvas.addEventListener("pointermove", (ev) => {
    const p = { x: ev.clientX, y: ev.clientY };
    cursor = p;
    canvas.style.cursor = overIcons(p) || (dog.mode !== "in_house" && boxContains(dogBox(), p)) ? "pointer" : "default";
    const overDog = dog.mode !== "in_house" && boxContains(dogBox(), p);
    const pr = feedPetting(petting, p.x, Date.now(), overDog && !press);
    petting = pr.state;
    if (pr.petted && !["pounce", "to_house", "in_house", "from_house", "held", "thrown"].includes(dog.mode)) {
      dog = playAction(dog, "beg", Date.now(), PET_MS);
      sendEvent("pet", { seconds: Math.round(pr.seconds * 10) / 10 });
    }
    if (!press) return;
    const now = performance.now();
    press.samples = [...press.samples.filter((q) => now - q.t < THROW_SAMPLE_MS), { x: p.x, y: p.y, t: now }];
    if (dog.mode !== "held" && Math.hypot(p.x - press.x, p.y - press.y) > DRAG_START_PX) { dog = grab(dog); bubble = null; }
    if (dog.mode === "held") dog = holdAt(dog, p.x - press.offX, p.y - press.offY, world);
  });
  canvas.addEventListener("pointerleave", () => { cursor = null; });
  canvas.addEventListener("pointerdown", (ev) => {
    const p = { x: ev.clientX, y: ev.clientY };
    if (overIcons(p)) return;
    if (dog.mode === "in_house" || !boxContains(dogBox(), p)) { lastClick = { x: p.x, y: p.y, t: Date.now() }; return; }
    const b = dogBox();
    press = { x: p.x, y: p.y, offX: p.x - b.left, offY: p.y - b.top, samples: [{ x: p.x, y: p.y, t: performance.now() }] };
    canvas.setPointerCapture(ev.pointerId);
  });
  canvas.addEventListener("pointerup", (ev) => {
    if (!press) return;
    canvas.releasePointerCapture(ev.pointerId);
    if (dog.mode === "held") {
      const first = press.samples[0], lastS = press.samples[press.samples.length - 1];
      const dtS = Math.max((lastS.t - first.t) / 1000, 0.016);
      dog = release(dog, (lastS.x - first.x) / dtS, (lastS.y - first.y) / dtS, Date.now());
    } else {
      dog = poke(dog, Date.now());
      sendEvent("poke");
    }
    press = null;
  });
  canvas.addEventListener("click", (ev) => {
    const p = { x: ev.clientX, y: ev.clientY };
    if (!houseVisible()) return;
    if (boxContains(houseBox, p)) doToggleHouse();
    else if (boxContains(chatBox, p)) toggleTalk();
    else if (boxContains(gearBox, p)) (panel.hidden ? openPanel() : (panel.hidden = true));
  });

  // ---- 그리기 (character.ts와 같은 방식) ----
  const tintCache = new Map<HTMLCanvasElement, Map<string, HTMLCanvasElement>>();
  const tinted = (src: HTMLCanvasElement, color: string): HTMLCanvasElement => {
    let byColor = tintCache.get(src);
    if (!byColor) { byColor = new Map(); tintCache.set(src, byColor); }
    let c = byColor.get(color);
    if (!c) {
      c = document.createElement("canvas");
      c.width = src.width; c.height = src.height;
      const g = c.getContext("2d")!;
      g.drawImage(src, 0, 0);
      g.globalCompositeOperation = "source-atop";
      g.fillStyle = color;
      g.fillRect(0, 0, c.width, c.height);
      byColor.set(color, c);
    }
    return c;
  };
  const facingLeft = manifest.facing === "left";

  const frame = (now: number) => {
    const dt = Math.min(now - last, 250);
    last = now;
    const wasInside = dog.mode === "in_house", wasThrown = dog.mode === "thrown";
    dog = step(dog, world, Date.now(), dt, { cursor, userIdleMs: idleMs(presence, Date.now()), windows: [], rest: prefs.rest, movement,
      click: lastClick ? { x: lastClick.x, y: lastClick.y, ageMs: Date.now() - lastClick.t } : null, rand: Math.random });
    if (!wasInside && dog.mode === "in_house") { dogHouseSince = dog.houseSince; sendEvent("house_in"); }
    if (wasThrown && dog.mode !== "thrown") {
      sendEvent("throw", { impact: impactOf(dog.impact), bounces: dog.bounces, flight_seconds: Math.round((Date.now() - dog.thrownAt) / 100) / 10 });
    }
    const anim = currentAnimation(dog);
    if (anim !== lastAnim) { animStart = now; lastAnim = anim; }

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (houseVisible()) {
      drawHouse(ctx, houseBox.left, houseBox.top, HOUSE_SCALE);
      drawChatIcon(ctx, chatBox.left, chatBox.top, HOUSE_SCALE, !talkbar.hidden);
      drawGearIcon(ctx, gearBox.left, gearBox.top, HOUSE_SCALE);
    }
    if (dog.mode !== "in_house") {
      const style = moodStyle(mood);
      const f = frameAt(manifest, anim, (now - animStart) * style.speed);
      const nowMs = Date.now();
      const react = shownReaction && nowMs - shownReaction.at < REACTION_MS ? shownReaction : null;
      const face = sheetImage(manifest, faceMood(mood, react ? react.id : null));
      const fr = frames.get(`${face}|${f.sx},${f.sy}`) ?? frames.get(`${manifest.image}|${f.sx},${f.sy}`);
      const b = dogBox();
      const hopR = react ? reactionHop(react.id, nowMs - react.at) : 0;
      const moving = dog.mode === "walk_to" || dog.mode === "follow" || dog.mode === "hunt";
      const bounce = moving && style.bounce ? Math.abs(Math.sin(now / 90)) * style.bounce : 0;
      const jitter = style.jitter ? (Math.random() * 2 - 1) * style.jitter : 0;
      const left = Math.round(b.left + jitter), top = Math.round(b.top - dog.hop - hopR - bounce + style.offsetY);
      const flip = facingLeft ? dog.dir === 1 : dog.dir === -1;
      ctx.save();
      if (style.tilt) { ctx.translate(left + dogW / 2, top + dogH); ctx.rotate(dog.dir === 1 ? style.tilt : -style.tilt); ctx.translate(-(left + dogW / 2), -(top + dogH)); }
      if (flip) { ctx.translate(left + dogW, 0); ctx.scale(-1, 1); ctx.translate(-left, 0); }
      if (fr) ctx.drawImage(style.tint ? tinted(fr.canvas, style.tint) : fr.canvas, left, top, dogW, dogH);
      else { ctx.fillStyle = "#c8843a"; ctx.fillRect(left, top, dogW, dogH); }
      ctx.restore();
      headTop = fr ? fr.top * manifest.scale : 0;
      if (react) {
        ctx.font = "20px 'Segoe UI Emoji', 'Apple Color Emoji', sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(EMOTES[react.id], left + dogW / 2, top + headTop - 4);
      }
    }
    const t = tickBubble(bubble, Date.now(), dt, userActive && !document.hidden);
    bubble = t.bubble;
    bubbleEl.hidden = !bubble || dog.mode === "in_house";
    if (bubble) {
      const b = dogBox();
      const bw = bubbleEl.offsetWidth, bh = bubbleEl.offsetHeight;
      bubbleEl.style.left = `${Math.max(0, Math.min(b.left + dogW / 2 - bw / 2, window.innerWidth - bw))}px`;
      bubbleEl.style.top = `${Math.max(0, b.top - dog.hop + headTop - bh - BUBBLE_GAP)}px`;
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

main();
