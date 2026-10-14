import { invoke } from "@tauri-apps/api/core";
const dog = document.getElementById("dog")!;
const bubble = document.getElementById("bubble")!;
const logEl = document.getElementById("log")!;

export function log(msg: string) {
  logEl.textContent = `${new Date().toLocaleTimeString()} ${msg}\n` + logEl.textContent;
}

let x = 0;
let dir = 1;
function tick() {
  x += dir * 2;
  if (x < 0 || x > window.innerWidth - 80) dir *= -1;
  dog.style.left = `${x}px`;
  const r = dog.getBoundingClientRect();
  bubble.style.left = `${r.left}px`;
  bubble.style.top = `${r.top - 40}px`;
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
  const btn = { attach: "btn-attach", wp: "btn-attach-wp", key: "btn-attach-key" }[mode as "attach" | "wp" | "key"];
  if (btn) setTimeout(() => document.getElementById(btn)!.click(), 1500);
});
