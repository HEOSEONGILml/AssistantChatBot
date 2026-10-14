import { invoke } from "@tauri-apps/api/core";
import { emit, listen } from "@tauri-apps/api/event";
import { getCurrentWindow, primaryMonitor } from "@tauri-apps/api/window";
import { frameAt, type Manifest } from "./body/sprite";
import { newDog, step, playAction, toggleHouse, currentAnimation, type Dog, type World } from "./body/dog";
import { showBubble, tickBubble, type Bubble } from "./body/bubble";
import { physToCss, cssBoxToPhys, boxContains, type Box } from "./body/coords";
import { drawHouse, HOUSE_PX } from "./body/house";
import type { Reaction, Signal } from "./shared/types";
import { stubReact } from "./body/stub-brain";
import { register, unregister } from "@tauri-apps/plugin-global-shortcut";
import { loadSettings, type Settings } from "./shared/settings";
import "./styles.css";

const canvas = document.getElementById("stage") as HTMLCanvasElement;
const ctx = canvas.getContext("2d")!;
const bubbleEl = document.getElementById("bubble")!;
const win = getCurrentWindow();

const HOUSE_SCALE = 3;
const ACTION_MS = 2500; // 잠정값: 한 동작을 보여 주는 시간
const USER_ACTIVE_IDLE_MS = 60_000; // 잠정값: 마지막 입력 후 1분이 지나면 자리를 비운 것으로 본다

async function main() {
  const manifest: Manifest = await (await fetch("/sprites/dog/manifest.json")).json();
  const sheet = new Image();
  let sheetOk = false;
  sheet.onload = () => (sheetOk = true);
  sheet.src = manifest.image;

  const mon = await primaryMonitor();
  const scale = mon?.scaleFactor ?? window.devicePixelRatio;
  const origin = await win.outerPosition();
  // 바닥선: 작업 영역 아래쪽 (CSS px)
  const workBottom = mon ? (mon.workArea.position.y + mon.workArea.size.height - origin.y) / scale : window.innerHeight;

  const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; ctx.imageSmoothingEnabled = false; };
  resize();
  window.addEventListener("resize", resize);

  const dogW = manifest.frameWidth * manifest.scale;
  const dogH = manifest.frameHeight * manifest.scale;
  const houseW = HOUSE_PX.width * HOUSE_SCALE;
  const houseH = HOUSE_PX.height * HOUSE_SCALE;
  const world: World = { floorWidth: window.innerWidth, dogWidth: dogW, houseX: window.innerWidth - houseW - 40, speed: 60 };
  const houseBox: Box = { left: world.houseX, top: workBottom - houseH, width: houseW, height: houseH };

  let dog: Dog = newDog(100);
  let bubble: Bubble = null;
  let hideHouseWhenInside = false; // Task 10에서 설정과 연결
  let dogHouseSince: number | null = null;
  let last = performance.now();
  let animStart = last;
  let lastAnim = currentAnimation(dog);

  const dogBox = (): Box => ({ left: dog.x, top: workBottom - dogH, width: dogW, height: dogH });

  const doToggleHouse = () => {
    const before = dog.mode;
    dog = toggleHouse(dog, Date.now());
    if (before === "in_house") emit("signal", { kind: "house", inside: false, awayMs: Date.now() - (dogHouseSince ?? Date.now()) });
    if (dog.mode === "to_house") { bubble = null; bubbleEl.hidden = true; }
  };

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

  // 클릭 통과: 커서가 강아지·집 위에 있을 때만 클릭을 받는다
  let through = true;
  await win.setIgnoreCursorEvents(true);
  setInterval(async () => {
    const [px, py] = await invoke<[number, number]>("cursor_pos");
    const p = physToCss({ x: px, y: py }, origin, scale);
    const overDog = dog.mode !== "in_house" && boxContains(dogBox(), p);
    const overHouse = !(hideHouseWhenInside && dog.mode === "in_house") && boxContains(houseBox, p);
    const over = overDog || overHouse;
    if (over === through) { through = !over; await win.setIgnoreCursorEvents(through); }
  }, 50);

  canvas.addEventListener("click", (ev) => {
    const p = { x: ev.clientX, y: ev.clientY };
    if (boxContains(houseBox, p)) return doToggleHouse();
    if (boxContains(dogBox(), p)) {
      emit("open-input", cssBoxToPhys(houseBox, origin, scale));
    }
  });

  // 사용자가 자리에 있는지: 마지막 입력 후 USER_ACTIVE_IDLE_MS 이내면 자리에 있다고 본다.
  // 오버레이는 항상 보이므로 가림 판정 대신 이것으로 말풍선 "봤다" 시간을 센다 (vision 2026-10-14 개정).
  let userActive = true;
  setInterval(async () => {
    const active = (await invoke<number>("idle_ms")) < USER_ACTIVE_IDLE_MS;
    if (active !== userActive) emit("signal", { kind: active ? "user_return" : "user_away" });
    userActive = active;
  }, 1000);

  // 시트의 강아지가 바라보는 방향과 걷는 방향이 다르면 좌우를 뒤집는다
  const facingLeft = manifest.facing === "left";

  const frame = (now: number) => {
    const dt = now - last;
    last = now;
    const wasInside = dog.mode === "in_house";
    dog = step(dog, world, Date.now(), dt);
    if (!wasInside && dog.mode === "in_house") { dogHouseSince = dog.houseSince; emit("signal", { kind: "house", inside: true, awayMs: 0 }); }

    const anim = currentAnimation(dog);
    if (anim !== lastAnim) { animStart = now; lastAnim = anim; }

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!(hideHouseWhenInside && dog.mode === "in_house")) drawHouse(ctx, houseBox.left, houseBox.top, HOUSE_SCALE);
    if (dog.mode !== "in_house") {
      const f = frameAt(manifest, anim, now - animStart);
      const b = dogBox();
      const flip = facingLeft ? dog.dir === 1 : dog.dir === -1;
      ctx.save();
      if (flip) { ctx.translate(b.left + dogW, 0); ctx.scale(-1, 1); ctx.translate(-b.left, 0); }
      if (sheetOk) ctx.drawImage(sheet, f.sx, f.sy, f.sw, f.sh, b.left, b.top, dogW, dogH);
      else { ctx.fillStyle = "#c8843a"; ctx.fillRect(b.left, b.top, dogW, dogH); }
      ctx.restore();
    }

    const t = tickBubble(bubble, Date.now(), dt, userActive);
    bubble = t.bubble;
    if (t.justSeen) emit("signal", { kind: "bubble_seen" });
    bubbleEl.hidden = !bubble || dog.mode === "in_house";
    if (bubble) {
      const b = dogBox();
      bubbleEl.style.left = `${Math.min(b.left, window.innerWidth - 240)}px`;
      bubbleEl.style.top = `${b.top - bubbleEl.offsetHeight - 8}px`;
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);

  // 전역 단축키: 설정에서 읽어 등록하고, 설정이 바뀌면 다시 등록한다
  let active: Settings | null = null;

  async function applyShortcuts(s: Settings) {
    const prev = active;
    if (prev) { await unregister(prev.inputShortcut).catch(() => {}); await unregister(prev.houseShortcut).catch(() => {}); }
    try {
      await register(s.inputShortcut, (e) => {
        if (e.state !== "Pressed" || dog.mode === "in_house") return;
        emit("open-input", cssBoxToPhys(houseBox, origin, scale));
      });
      await register(s.houseShortcut, (e) => { if (e.state === "Pressed") doToggleHouse(); });
      active = s;
    } catch (err) {
      await unregister(s.inputShortcut).catch(() => {});
      await unregister(s.houseShortcut).catch(() => {});
      emit("shortcut-error", `단축키 등록 실패: ${err}. 이전 단축키를 유지합니다.`);
      if (prev && prev !== s) await applyShortcuts(prev);
    }
  }

  const s0 = await loadSettings();
  hideHouseWhenInside = s0.hideHouseWhenInside;
  await applyShortcuts(s0);
  listen<Settings>("settings-changed", async (e) => {
    hideHouseWhenInside = e.payload.hideHouseWhenInside;
    await applyShortcuts(e.payload);
  });

  // 첫 실행 안내: 키가 없으면 돌아다니기만 하고 안내 말풍선
  const hasKeys = (await invoke<boolean>("key_has", { name: "typesafe" })) && (await invoke<boolean>("key_has", { name: "gemini" }));
  if (!hasKeys) { bubble = showBubble("트레이 아이콘 → 설정에서 키를 넣어 주세요"); bubbleEl.textContent = bubble!.text; }
}

main();
