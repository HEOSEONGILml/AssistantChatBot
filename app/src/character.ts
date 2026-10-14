import { invoke } from "@tauri-apps/api/core";
import { emit, listen } from "@tauri-apps/api/event";
import { getCurrentWindow, primaryMonitor } from "@tauri-apps/api/window";
import { register, unregister } from "@tauri-apps/plugin-global-shortcut";
import { frameAt, opaqueTop, type Manifest } from "./body/sprite";
import { newDog, step, playAction, toggleHouse, currentAnimation, type Dog, type World } from "./body/dog";
import { showBubble, tickBubble, type Bubble } from "./body/bubble";
import { physToCss, cssBoxToPhys, boxContains, type Box } from "./body/coords";
import { drawHouse, HOUSE_PX, drawChatIcon, CHAT_PX } from "./body/house";
import { stubReact } from "./body/stub-brain";
import { loadSettings, saveSettings, shortcutFallback, type Settings } from "./shared/settings";
import type { Reaction, Signal } from "./shared/types";
import "./styles.css";

const canvas = document.getElementById("stage") as HTMLCanvasElement;
const ctx = canvas.getContext("2d")!;
const bubbleEl = document.getElementById("bubble")!;
const win = getCurrentWindow();

const HOUSE_SCALE = 3;
const ICON_GAP = 10;
const BUBBLE_GAP = 10;               // 말풍선 아래 꼬리(7px)와 강아지 머리 사이 여유 (CSS px)                 // 집과 말풍선 아이콘 사이 (CSS px)
const ACTION_MS = 2500;              // 잠정값: 한 동작을 보여 주는 시간
const USER_ACTIVE_IDLE_MS = 60_000;  // 잠정값: 마지막 입력 후 1분이 지나면 자리를 비운 것으로 본다
const WALK_SPEED = 70, RUN_SPEED = 180; // 잠정값: CSS px/초

async function main() {
  const manifest: Manifest = await (await fetch("/sprites/dog/manifest.json")).json();
  // 프레임을 한 칸씩 잘라 따로 보관한다. 시트에서 바로 늘려 그리면 1.5배 같은 배율에서
  // 바로 위 칸의 픽셀이 섞여 칸 위쪽에 희미한 줄이 생긴다. 칸마다 그림이 시작되는 높이도 함께 잰다.
  type Frame = { canvas: HTMLCanvasElement; top: number };
  const frames = new Map<string, Frame>();
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
        frames.set(`${r.sx},${r.sy}`, { canvas: c, top: opaqueTop(alpha, sheet.width, r) });
      }
    }
  };
  sheet.src = manifest.image;
  let headTop = 0; // 지금 그린 프레임에서 그림이 시작되는 높이 (CSS px, 강아지 칸 위쪽 기준)

  const mon = await primaryMonitor();
  const scale = mon?.scaleFactor ?? window.devicePixelRatio;
  const origin = await win.outerPosition();
  // 강아지가 다닐 수 있는 영역: 작업 영역(작업 표시줄 제외)을 캐릭터 층의 CSS 좌표로
  const area = mon
    ? {
        left: (mon.workArea.position.x - origin.x) / scale,
        top: (mon.workArea.position.y - origin.y) / scale,
        width: mon.workArea.size.width / scale,
        height: mon.workArea.size.height / scale,
      }
    : { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight };

  const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; ctx.imageSmoothingEnabled = false; };
  resize();
  window.addEventListener("resize", resize);

  const dogW = manifest.frameWidth * manifest.scale;
  const dogH = manifest.frameHeight * manifest.scale;
  const houseW = HOUSE_PX.width * HOUSE_SCALE, houseH = HOUSE_PX.height * HOUSE_SCALE;
  const chatW = CHAT_PX.width * HOUSE_SCALE, chatH = CHAT_PX.height * HOUSE_SCALE;
  // 집과 말풍선 아이콘: 작업 영역 오른쪽 아래 (CSS 좌표)
  const houseBox: Box = { left: area.left + area.width - houseW - 40, top: area.top + area.height - houseH, width: houseW, height: houseH };
  const chatBox: Box = { left: houseBox.left - chatW - ICON_GAP, top: area.top + area.height - chatH - 4, width: chatW, height: chatH };
  // 강아지 좌표는 작업 영역 기준(dog.ts). 집 앞에 선 위치도 같은 기준으로
  const world: World = {
    width: area.width, height: area.height, dogWidth: dogW, dogHeight: dogH,
    houseX: houseBox.left - area.left + houseW / 2 - dogW / 2, houseY: area.height - dogH,
    walkSpeed: WALK_SPEED, runSpeed: RUN_SPEED,
  };

  let dog: Dog = newDog(area.width / 3, area.height - dogH);
  let bubble: Bubble = null;
  let hideHouseWhenInside = false;
  let dogHouseSince: number | null = null;
  let inputOpen = false;
  let userActive = true, userIdleMs = 0;
  let cursorCss: { x: number; y: number } | null = null;
  let last = performance.now();
  let animStart = last;
  let lastAnim = currentAnimation(dog);

  const dogBox = (): Box => ({ left: area.left + dog.x, top: area.top + dog.y, width: dogW, height: dogH });
  const houseVisible = () => !(hideHouseWhenInside && dog.mode === "in_house");

  const doToggleHouse = () => {
    const before = dog.mode;
    dog = toggleHouse(dog, Date.now());
    if (before === "in_house") emit("signal", { kind: "house", inside: false, awayMs: Date.now() - (dogHouseSince ?? Date.now()) });
    if (dog.mode === "to_house") { bubble = null; bubbleEl.hidden = true; }
  };
  // 입력창은 강아지 위치와 상관없이 집 위에 뜬다 (vision)
  const toggleInput = () => emit("toggle-input", cssBoxToPhys(houseBox, origin, scale));

  listen<Reaction>("reaction", (e) => {
    if (dog.mode === "in_house" || dog.mode === "to_house") return; // 집에서는 완전히 조용 (vision)
    if (e.payload.action) dog = playAction(dog, e.payload.action, Date.now(), ACTION_MS);
    if (e.payload.utterance) { bubble = showBubble(e.payload.utterance); bubbleEl.textContent = e.payload.utterance; }
  });
  listen<Signal>("signal", (e) => {
    const r = stubReact(e.payload);
    if (r) emit("reaction", r);
  });
  listen("toggle-house", doToggleHouse);
  listen<boolean>("input-visibility", (e) => (inputOpen = e.payload));

  // 클릭 통과: 커서가 집·말풍선 아이콘·강아지 위에 있을 때만 클릭을 받는다.
  // 강아지 클릭은 말걸기가 아니다(vision). 쓰다듬기·찌르기 같은 상호작용 자리로 받아 둔다.
  let through = true;
  await win.setIgnoreCursorEvents(true);
  setInterval(async () => {
    const [px, py] = await invoke<[number, number]>("cursor_pos");
    const p = physToCss({ x: px, y: py }, origin, scale);
    cursorCss = { x: p.x - area.left, y: p.y - area.top };
    const over =
      (houseVisible() && (boxContains(houseBox, p) || boxContains(chatBox, p))) ||
      (dog.mode !== "in_house" && boxContains(dogBox(), p));
    if (over === through) { through = !over; await win.setIgnoreCursorEvents(through); }
  }, 50);

  canvas.addEventListener("click", (ev) => {
    const p = { x: ev.clientX, y: ev.clientY };
    if (houseVisible() && boxContains(houseBox, p)) return doToggleHouse();
    if (houseVisible() && boxContains(chatBox, p)) return toggleInput();
  });

  // 사용자가 자리에 있는지: 말풍선 "봤다" 판정과 강아지 잠들기에 쓴다
  setInterval(async () => {
    userIdleMs = await invoke<number>("idle_ms");
    const active = userIdleMs < USER_ACTIVE_IDLE_MS;
    if (active !== userActive) emit("signal", { kind: active ? "user_return" : "user_away" });
    userActive = active;
  }, 1000);

  // 시트의 강아지가 바라보는 방향과 걷는 방향이 다르면 좌우를 뒤집는다
  const facingLeft = manifest.facing === "left";

  const frame = (now: number) => {
    const dt = Math.min(now - last, 250); // 절전 복귀 등으로 dt가 튀어도 순간이동하지 않게
    last = now;
    const wasInside = dog.mode === "in_house";
    dog = step(dog, world, Date.now(), dt, { cursor: cursorCss, userIdleMs, rand: Math.random });
    if (!wasInside && dog.mode === "in_house") { dogHouseSince = dog.houseSince; emit("signal", { kind: "house", inside: true, awayMs: 0 }); }

    const anim = currentAnimation(dog);
    if (anim !== lastAnim) { animStart = now; lastAnim = anim; }

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (houseVisible()) {
      drawHouse(ctx, houseBox.left, houseBox.top, HOUSE_SCALE);
      drawChatIcon(ctx, chatBox.left, chatBox.top, HOUSE_SCALE, inputOpen);
    }
    if (dog.mode !== "in_house") {
      const f = frameAt(manifest, anim, now - animStart);
      const fr = frames.get(`${f.sx},${f.sy}`);
      const b = dogBox();
      const left = Math.round(b.left), top = Math.round(b.top); // 픽셀아트가 번지지 않게 정수 좌표에 그린다
      const flip = facingLeft ? dog.dir === 1 : dog.dir === -1;
      ctx.save();
      if (flip) { ctx.translate(left + dogW, 0); ctx.scale(-1, 1); ctx.translate(-left, 0); }
      if (fr) ctx.drawImage(fr.canvas, left, top, dogW, dogH);
      else { ctx.fillStyle = "#c8843a"; ctx.fillRect(left, top, dogW, dogH); }
      ctx.restore();
      headTop = fr ? fr.top * manifest.scale : 0;
    }

    const t = tickBubble(bubble, Date.now(), dt, userActive);
    bubble = t.bubble;
    if (t.justSeen) emit("signal", { kind: "bubble_seen" });
    bubbleEl.hidden = !bubble || dog.mode === "in_house";
    if (bubble) {
      const b = dogBox();
      // 강아지 머리 위 가운데에 맞추고(꼬리가 강아지를 가리킴) 화면 밖으로 나가지 않게 한다
      const bw = bubbleEl.offsetWidth, bh = bubbleEl.offsetHeight;
      bubbleEl.style.left = `${Math.max(0, Math.min(b.left + dogW / 2 - bw / 2, window.innerWidth - bw))}px`;
      bubbleEl.style.top = `${Math.max(0, b.top + headTop - bh - BUBBLE_GAP)}px`;
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);

  // 전역 단축키. 등록은 한 번에 하나씩(직렬) 처리한다: 저장을 빠르게 두 번 하면 등록이 엉키기 때문이다.
  let active: Settings | null = null;
  let queue: Promise<void> = Promise.resolve();

  async function tryRegister(s: Settings): Promise<boolean> {
    try {
      await register(s.inputShortcut, (e) => { if (e.state === "Pressed") toggleInput(); });
      await register(s.houseShortcut, (e) => { if (e.state === "Pressed") doToggleHouse(); });
      return true;
    } catch {
      await unregister(s.inputShortcut).catch(() => {});
      await unregister(s.houseShortcut).catch(() => {});
      return false;
    }
  }

  async function applyShortcuts(s: Settings) {
    const prev = active;
    if (prev) { await unregister(prev.inputShortcut).catch(() => {}); await unregister(prev.houseShortcut).catch(() => {}); }
    if (await tryRegister(s)) { active = s; return; }
    // 실패한 단축키는 저장하지 않는다: 이전 값(앱 시작 때는 기본값)으로 되돌려 다시 등록하고 저장한다
    const fallback = shortcutFallback(s, prev);
    if (await tryRegister(fallback)) active = fallback;
    await saveSettings(fallback);
    const msg = `단축키 등록 실패 (${s.inputShortcut}, ${s.houseShortcut}). ${prev ? "이전" : "기본"} 단축키로 되돌렸어요.`;
    emit("shortcut-error", msg);
    if (!prev) { bubble = showBubble(msg); bubbleEl.textContent = msg; }
  }
  const enqueue = (s: Settings) => (queue = queue.then(() => applyShortcuts(s)).catch(() => {}));

  const s0 = await loadSettings();
  hideHouseWhenInside = s0.hideHouseWhenInside;
  await enqueue(s0);
  listen<Settings>("settings-changed", (e) => {
    hideHouseWhenInside = e.payload.hideHouseWhenInside;
    enqueue(e.payload);
  });

  // 첫 실행 안내: 키가 없으면 돌아다니기만 하고 안내 말풍선. 자격 증명 저장소 오류도 "키 없음"으로 본다
  const has = (name: string) => invoke<boolean>("key_has", { name }).catch(() => false);
  if (!((await has("typesafe")) && (await has("gemini")))) {
    bubble = showBubble("트레이 아이콘 → 설정에서 키를 넣어 주세요");
    bubbleEl.textContent = bubble!.text;
  }
}

main();
