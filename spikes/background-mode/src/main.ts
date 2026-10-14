import { listen } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";
const dog = document.getElementById("dog")!;
const bubble = document.getElementById("bubble")!;
const logEl = document.getElementById("log")!;

export function log(msg: string) {
  logEl.textContent = `${new Date().toLocaleTimeString()} ${msg}\n` + logEl.textContent;
}

let x = 600;
let dir = 1;
let frozen = false;
let lowBubble = false;
function tick() {
  if (!frozen) x += dir * 2;
  if (x < 0 || x > window.innerWidth - 80) dir *= -1;
  dog.style.left = `${x}px`;
  const r = dog.getBoundingClientRect();
  bubble.style.left = `${r.left}px`;
  bubble.style.top = lowBubble ? `${window.innerHeight - 30}px` : `${r.top - 40}px`;
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
log(`dpr=${window.devicePixelRatio} size=${window.innerWidth}x${window.innerHeight}`);

document.getElementById("btn-attach")!.addEventListener("click", async () => {
  try { log(`attach: ${await invoke<string>("attach_to_desktop")}`); }
  catch (e) { log(`attach error: ${e}`); }
});

document.getElementById("btn-attach-key")!.addEventListener("click", async () => {
  document.body.style.background = "#ff00ff";
  try { log(`attach-key: ${await invoke<string>("attach_color_key")}`); }
  catch (e) { log(`attach-key error: ${e}`); }
});

document.getElementById("btn-attach-wp")!.addEventListener("click", async () => {
  try {
    const buf = await invoke<ArrayBuffer>("wallpaper_bytes");
    const url = URL.createObjectURL(new Blob([buf]));
    document.body.style.background = `url(${url}) center / cover no-repeat`;
    log(`wallpaper ${buf.byteLength} bytes`);
    log(`attach-wp: ${await invoke<string>("attach_to_desktop")}`);
  } catch (e) { log(`attach-wp error: ${e}`); }
});

// 스파이크 자동 실행: SPIKE_MODE 환경 변수로 버튼 클릭을 대신한다
invoke<string>("spike_mode").then((mode) => {
  if (mode) log(`auto mode=${mode}`);
  if (mode.startsWith("overlay")) { startOverlay(); mode = mode.replace("overlay", ""); }
  if (mode.endsWith("-low")) { lowBubble = true; mode = mode.replace("-low", ""); }
  if (mode.endsWith("-freeze")) { frozen = true; mode = mode.replace("-freeze", ""); }
  const btn = (mode as string) === "" ? undefined : { attach: "btn-attach", wp: "btn-attach-wp", key: "btn-attach-key" }[mode as "attach" | "wp" | "key"];
  if (btn) setTimeout(() => document.getElementById(btn)!.click(), 1500);
});

type Click = { x: number; y: number; foreground: string };
listen<Click>("desktop-click", (e) => {
  const dpr = window.devicePixelRatio;
  const cx = e.payload.x / dpr;
  const cy = e.payload.y / dpr;
  const r = dog.getBoundingClientRect();
  const onDog = cx >= r.left && cx < r.right && cy >= r.top && cy < r.bottom;
  log(`click phys=(${e.payload.x},${e.payload.y}) css=(${cx.toFixed(0)},${cy.toFixed(0)}) fg=${e.payload.foreground} onDog=${onDog}`);
});

async function probe() {
  const dpr = window.devicePixelRatio;
  const b = bubble.getBoundingClientRect();
  const region = { left: Math.round(b.left * dpr), top: Math.round(b.top * dpr), right: Math.round(b.right * dpr), bottom: Math.round(b.bottom * dpr) };
  try {
    const covered = await invoke<string[]>("region_covered_by", { region });
    const s = await invoke<{ foreground: string; desktop_exposed: boolean; idle_ms: number }>("desktop_status");
    log(`bubble covered=${covered.length > 0} by=[${covered.join(",")}] fg=${s.foreground} exposed=${s.desktop_exposed} idle=${s.idle_ms}ms`);
  } catch (e) { log(`probe error: ${e}`); }
}
setInterval(probe, 3000);

async function startOverlay() {
  await invoke("set_overlay", { enabled: true });
  let through = true;
  setInterval(async () => {
    const [px, py] = await invoke<[number, number]>("cursor_pos");
    const dpr = window.devicePixelRatio;
    const r = dog.getBoundingClientRect();
    const over = px / dpr >= r.left && px / dpr < r.right && py / dpr >= r.top && py / dpr < r.bottom;
    if (over === through) {
      through = !over;
      await invoke("set_click_through", { through });
    }
  }, 50);
  dog.addEventListener("click", () => { log("overlay: dog clicked"); invoke("desktop_status"); });
  log("overlay mode");
}
