// 주 창 자리(강아지 위치·끌기·패널 자리)와 큰 창 열기. 자리 계산은 shared/placement.ts.
import {
  PhysicalPosition, PhysicalSize, Window, availableMonitors, getCurrentWindow, primaryMonitor, type Monitor,
} from "@tauri-apps/api/window";
import { DOG, clampDog, contains, initialDog, layout, type Layout, type Point, type Rect, type Size } from "./shared/placement";

const SAVED = "dogPosition"; // localStorage: 강아지 왼쪽 위의 화면 좌표(물리 px)

let dog: Point | null = null; // 강아지 왼쪽 위, 물리 px. 켤 때 저장한 자리에서 읽는다
let home: Monitor | null = null; // 강아지가 놓인 모니터. 끄는 중에 모니터 밖으로 나가면 이 모니터를 쓴다
let panel: Size | null = null; // 열린 패널 크기(논리 px)
let onLayout: (l: Layout) => void = () => {};

let applied = ""; // 마지막으로 성공한 창 사각형(물리 px)
let appliedSize = "";
let dirty = false; // 아직 적용하지 않은 요청이 있다
let running: Promise<void> | null = null;

let dragFrom: { dog: Point; k: number } | null = null;

const workArea = (m: Monitor): Rect => {
  const { position: p, size: s } = m.workArea;
  return { x: p.x, y: p.y, width: s.width, height: s.height };
};
const frame = (m: Monitor): Rect => ({ x: m.position.x, y: m.position.y, width: m.size.width, height: m.size.height });
const toLogical = (r: Rect, k: number): Rect => ({ x: r.x / k, y: r.y / k, width: r.width / k, height: r.height / k });

// 창 안 강아지·패널 자리를 받을 곳. 창을 놓은 뒤마다 부른다
export function onPlaced(fn: (l: Layout) => void): void { onLayout = fn; }

// 패널 크기(닫혔으면 null)를 바꾸고 창을 다시 놓는다.
// 호출이 겹치면 차례로 하나씩 하고, 밀린 요청 가운데 가장 최근 것만 적용한다
export function placeWindow(panelSize: Size | null): Promise<void> {
  panel = panelSize;
  return schedule();
}

function schedule(): Promise<void> {
  dirty = true;
  running ??= (async () => {
    try {
      while (dirty) {
        dirty = false;
        try { await place(); } catch (e) { console.warn("창 배치 실패", e); }
      }
    } finally { running = null; }
  })();
  return running;
}

// 저장한 자리가 어느 모니터 작업 영역 안이면 쓰고, 아니면 주 모니터 오른쪽 아래(처음 자리)
async function restore(ms: Monitor[]): Promise<void> {
  let saved: Point | null = null;
  try {
    const v = JSON.parse(localStorage.getItem(SAVED) ?? "null");
    if (Number.isFinite(v?.x) && Number.isFinite(v?.y)) saved = { x: v.x, y: v.y };
  } catch { /* 망가진 값은 버린다 */ }
  const m = saved && ms.find((m) => contains(workArea(m), saved));
  if (saved && m) { home = m; dog = pull(m, saved); return; }
  home = (await primaryMonitor()) ?? ms[0] ?? null;
  if (!home) return;
  const k = home.scaleFactor;
  const p = initialDog(toLogical(workArea(home), k));
  dog = { x: Math.round(p.x * k), y: Math.round(p.y * k) };
}

// 강아지를 모니터 m의 작업 영역 안으로 당긴다(물리 px)
function pull(m: Monitor, p: Point): Point {
  const k = m.scaleFactor;
  const c = clampDog(toLogical(workArea(m), k), { x: p.x / k, y: p.y / k });
  return { x: Math.round(c.x * k), y: Math.round(c.y * k) };
}

// 강아지가 놓인 모니터: 강아지 가운데가 들어 있는 모니터, 없으면 지금까지의 모니터
function monitorOf(ms: Monitor[], p: Point): Monitor | null {
  const k = home?.scaleFactor ?? 1;
  const center = { x: p.x + (DOG.width * k) / 2, y: p.y + (DOG.height * k) / 2 };
  return ms.find((m) => contains(frame(m), center)) ?? home;
}

async function place(): Promise<void> {
  const ms = await availableMonitors();
  if (!dog) await restore(ms);
  if (!dog) return;
  home = monitorOf(ms, dog);
  if (!home) return;
  const k = home.scaleFactor;
  const l = layout(toLogical(workArea(home), k), { x: dog.x / k, y: dog.y / k }, panel);
  const r = l.window;
  const pos = new PhysicalPosition(Math.round(r.x * k), Math.round(r.y * k));
  const w = Math.round(r.width * k);
  const hh = Math.round(r.height * k);
  const key = `${pos.x},${pos.y},${w}x${hh}`;
  if (key !== applied) {
    const win = getCurrentWindow();
    const size = `${w}x${hh}`;
    if (size === appliedSize) await win.setPosition(pos); // 끄는 중에는 자리만 바뀐다
    else {
      const cur = await win.innerSize();
      // 커질 때는 위치를 먼저 옮긴다. 크기부터 바꾸면 잠깐 작업 영역 밖으로 넘친다
      if (w > cur.width || hh > cur.height) {
        await win.setPosition(pos);
        await win.setSize(new PhysicalSize(w, hh));
      } else {
        await win.setSize(new PhysicalSize(w, hh));
        await win.setPosition(pos);
      }
      appliedSize = size;
    }
    applied = key;
  }
  onLayout(l);
}

// --- 끌기 ---
// 끌기 시작: 지금 강아지 자리와 그 모니터 배율을 기억한다
export function beginDrag(): void {
  if (dog) dragFrom = { dog, k: home?.scaleFactor ?? 1 };
}

// 누른 곳에서 움직인 거리(화면 좌표, CSS px)만큼 강아지를 옮긴다
export function dragBy(dx: number, dy: number): void {
  if (!dragFrom) return;
  const { dog: d, k } = dragFrom;
  dog = { x: d.x + Math.round(dx * k), y: d.y + Math.round(dy * k) };
  schedule();
}

// 놓으면 강아지가 놓인 모니터의 작업 영역 안으로 당기고 저장한다
export async function endDrag(): Promise<void> {
  if (!dragFrom) return;
  dragFrom = null;
  try {
    const m = monitorOf(await availableMonitors(), dog!);
    if (m) { home = m; dog = pull(m, dog!); }
  } catch (e) { console.warn("모니터 읽기 실패", e); }
  try { localStorage.setItem(SAVED, JSON.stringify(dog)); } catch (e) { console.warn("강아지 자리 저장 실패", e); }
  await schedule();
}

// 큰 창을 보이고 앞으로 가져온다. 그릴 상태는 주 창이 big-state로 넘긴다
export async function showBig(): Promise<void> {
  const win = await Window.getByLabel("big");
  if (!win) return;
  await win.show();
  await win.setFocus();
}
