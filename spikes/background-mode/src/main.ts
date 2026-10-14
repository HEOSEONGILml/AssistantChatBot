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
