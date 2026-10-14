# 서브 프로젝트 0: 배경 모드 스파이크 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이 PC(Windows 10 Pro 19045)에서 Tauri 창을 바탕화면 아이콘 뒤에 붙이기, 배경 모드 클릭 감지, 가림 판정, 바탕화면 노출·마지막 입력 감지가 되는지 확인하고 결과를 문서로 남긴다.

**Architecture:** 최소 Tauri 2 앱(vanilla TypeScript)에 Rust 명령과 이벤트를 붙여 질문 하나당 기능 하나씩 시험한다. 프론트엔드는 움직이는 "강아지" 사각형과 디버그 로그만 그린다. 판정은 사람이 눈으로 확인하고, 순수 계산(사각형 교차)만 단위 테스트한다.

**Tech Stack:** Tauri 2, Rust(stable-msvc), `windows` 크레이트, TypeScript(vanilla), npm

**Spec:** [`docs/superpowers/specs/2026-10-14-windows-desktop-pet-design.md`](../specs/2026-10-14-windows-desktop-pet-design.md) 8절

## Global Constraints

- **스파이크 코드는 버린다.** 코드는 `spike/background-mode` 브랜치의 `spikes/background-mode/`에만 두고 다른 브랜치로 머지하지 않는다. 결과 문서(`docs/spikes/background-mode.md`)만 `docs/harness-setup` 브랜치에 커밋한다.
- 대상은 주 모니터 하나다.
- 쓰기 전에 Tauri와 `windows` 크레이트 API를 Context7로 확인한다(CLAUDE.md 5절). 아래 Rust 코드는 `windows` 0.61 기준이다. Tauri가 쓰는 버전과 다르면 Task 1에서 맞추고, import 경로는 컴파일러 오류를 보고 고친다.
- 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`를 붙인다.

## Review Focus

1. **DPI 배율**: 마우스 훅 좌표는 물리 픽셀이고 웹뷰 좌표는 CSS 픽셀이다. 배율 125%·150%에서도 강아지 클릭 판정이 맞아야 한다 → Task 3에서 `devicePixelRatio`로 변환하고, 배율을 바꿔 수동 확인한다.
2. **바탕화면 아이콘 동작 방해**: 훅을 건 뒤에도 아이콘 클릭·더블클릭·드래그 선택이 평소처럼 되어야 한다 → Task 3 수동 확인 항목.
3. **탐색기 재시작**: `explorer.exe`가 재시작되면 WorkerW가 새로 만들어져 붙인 창이 사라질 수 있다 → Task 2 수동 확인 항목에 넣고 결과를 기록한다.
4. **"바탕화면 보기"(Win+D)**: 모든 창 최소화 시 배경 모드 창이 계속 보이고, 노출 감지가 "바탕화면 노출"로 나와야 한다 → Task 4 수동 확인 항목.
5. **작업 표시줄과 겹침**: 말풍선 영역이 작업 표시줄 아래에 있으면 가려진 것으로 판정되어야 한다 → Task 4 수동 확인 항목.

---

## 파일 구조

```
spikes/background-mode/            # create-tauri-app vanilla-ts로 생성
├── index.html                     # 강아지 사각형 + 디버그 로그
├── src/main.ts                    # 명령 호출, 이벤트 수신, 히트 테스트
├── src/styles.css                 # 투명 배경
└── src-tauri/
    ├── Cargo.toml                 # windows 크레이트 추가
    ├── tauri.conf.json            # 투명·프레임 없음·작업 표시줄 숨김
    └── src/
        ├── lib.rs                 # 명령 등록, setup에서 창 크기와 훅 시작
        ├── geom.rs                # Rect, 교차 판정 (단위 테스트 대상)
        ├── desktop.rs             # WorkerW 찾기·붙이기, 노출·마지막 입력
        ├── hook.rs                # 저수준 마우스 훅 스레드
        └── occlusion.rs           # 영역 가림 판정
docs/spikes/background-mode.md     # 결과 문서 (docs 브랜치)
```

---

### Task 1: 개발 환경과 스파이크 앱 뼈대

**Files:**
- Create: `spikes/background-mode/` 전체 (스캐폴딩)
- Modify: `spikes/background-mode/src-tauri/tauri.conf.json`
- Modify: `spikes/background-mode/src-tauri/src/lib.rs`
- Modify: `spikes/background-mode/src/styles.css`, `index.html`, `src/main.ts`

**Interfaces:**
- Produces: 주 모니터 전체를 덮는 투명 창 `main`. 화면에 "강아지" 사각형(`#dog`, 80×60 CSS px)이 바닥선을 따라 좌우로 움직인다. `log(msg: string)` 함수가 `#log`에 줄을 추가한다.

- [ ] **Step 1: 스파이크 브랜치 만들기**

```bash
cd /c/Users/lab2ai/TamagotchiChatBot
git checkout -b spike/background-mode
```

- [ ] **Step 2: Rust 설치 (stable-msvc)**

VS 2019 C++ 빌드 도구는 이미 있다. rustup만 설치한다.

```powershell
Invoke-WebRequest https://win.rustup.rs/x86_64 -OutFile "$env:TEMP\rustup-init.exe"
& "$env:TEMP\rustup-init.exe" -y --default-toolchain stable-msvc
```

새 셸에서 확인한다.

Run: `cargo --version; rustc --version`
Expected: 두 버전 문자열이 출력된다.

- [ ] **Step 3: Tauri 앱 생성**

```bash
mkdir -p spikes && cd spikes
npm create tauri-app@latest background-mode -- -m npm -t vanilla-ts --identifier com.tamagotchi.spike -y
cd background-mode && npm install
```

Expected: `spikes/background-mode/src-tauri/` 와 `src/main.ts` 가 생긴다. 플래그가 바뀌어 대화형 질문이 나오면 TypeScript / npm / Vanilla / TypeScript를 고른다.

- [ ] **Step 4: Tauri가 쓰는 `windows` 버전 확인 후 의존성 추가**

```bash
cd src-tauri && cargo tree -i windows --depth 0 2>/dev/null | head -3
```

출력된 버전(예: `windows v0.61.x`)과 같은 메이저·마이너로 `Cargo.toml`의 `[dependencies]`에 추가한다. 출력이 없으면 `0.61`을 쓴다.

```toml
windows = { version = "0.61", features = [
  "Win32_Foundation",
  "Win32_UI_WindowsAndMessaging",
  "Win32_UI_Input_KeyboardAndMouse",
  "Win32_System_SystemInformation",
  "Win32_Graphics_Dwm",
] }
```

- [ ] **Step 5: 창 설정**

`src-tauri/tauri.conf.json`의 `app.windows[0]`을 다음으로 바꾼다.

```json
{
  "label": "main",
  "title": "spike",
  "transparent": true,
  "decorations": false,
  "skipTaskbar": true,
  "resizable": false,
  "shadow": false,
  "width": 800,
  "height": 600
}
```

- [ ] **Step 6: 창을 주 모니터 전체로 키우기**

`src-tauri/src/lib.rs`의 `run()`을 다음으로 바꾼다. (스캐폴딩의 `greet` 명령은 지운다.)

```rust
mod desktop;
mod geom;
mod hook;
mod occlusion;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let win = app.get_webview_window("main").expect("main window");
            if let Some(mon) = win.primary_monitor()? {
                win.set_position(*mon.position())?;
                win.set_size(*mon.size())?;
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

이 단계에서 아직 없는 모듈 파일 네 개를 빈 파일로 만든다: `src/desktop.rs`, `src/geom.rs`, `src/hook.rs`, `src/occlusion.rs`.

- [ ] **Step 7: 프론트엔드를 강아지 사각형과 로그로 교체**

`index.html`의 `<body>` 안을 다음으로 바꾼다.

```html
<div id="dog"></div>
<div id="bubble">말풍선</div>
<div id="panel">
  <button id="btn-attach">배경에 붙이기</button>
  <button id="btn-occluded">말풍선 가림?</button>
  <button id="btn-status">노출/입력 상태</button>
  <pre id="log"></pre>
</div>
<script type="module" src="/src/main.ts"></script>
```

`src/styles.css` 전체를 다음으로 바꾼다.

```css
html, body { margin: 0; background: transparent; overflow: hidden; width: 100vw; height: 100vh; }
#dog { position: absolute; width: 80px; height: 60px; background: #c8843a; border-radius: 12px; bottom: 80px; left: 0; }
#bubble { position: absolute; padding: 6px 10px; background: #fff; border: 2px solid #333; border-radius: 10px; font: 14px sans-serif; }
#panel { position: absolute; top: 20px; left: 20px; background: rgba(255,255,255,0.9); padding: 8px; font: 12px monospace; }
#log { max-height: 240px; overflow: auto; margin: 6px 0 0; }
```

`src/main.ts` 전체를 다음으로 바꾼다.

```ts
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
```

- [ ] **Step 8: 실행 확인**

Run: `npm run tauri dev` (spikes/background-mode에서)
Expected: 바탕화면 위에 갈색 사각형이 좌우로 움직이고, 말풍선이 따라다니며, 사각형 밖은 투명해서 뒤가 보인다. 로그 첫 줄에 `dpr=`가 찍힌다. 창 테두리·제목 표시줄·작업 표시줄 버튼이 없다.

- [ ] **Step 9: Commit**

```bash
cd /c/Users/lab2ai/TamagotchiChatBot
git add spikes/background-mode
git commit -m "spike: 배경 모드 스파이크 앱 뼈대"
```

---

### Task 2: 질문 1 — 아이콘 뒤 레이어(WorkerW)에 붙이기

**Files:**
- Modify: `spikes/background-mode/src-tauri/src/desktop.rs`
- Modify: `spikes/background-mode/src-tauri/src/lib.rs`
- Modify: `spikes/background-mode/src/main.ts`

**Interfaces:**
- Consumes: Task 1의 `main` 창, `log()`
- Produces: Rust `desktop::find_desktop_worker() -> Option<HWND>`, `desktop::attach(child: HWND) -> bool`, Tauri 명령 `attach_to_desktop() -> Result<String, String>`

- [ ] **Step 1: WorkerW 찾기와 붙이기 구현**

`src-tauri/src/desktop.rs`:

```rust
use windows::core::{w, BOOL, PCWSTR};
use windows::Win32::Foundation::{HWND, LPARAM, WPARAM};
use windows::Win32::UI::WindowsAndMessaging::{
    EnumWindows, FindWindowExW, FindWindowW, SendMessageTimeoutW, SetParent, SMTO_NORMAL,
};

// 아이콘(SHELLDLL_DefView)을 가진 최상위 창의 바로 다음 WorkerW가 아이콘 뒤 레이어다.
unsafe extern "system" fn find_worker(hwnd: HWND, lparam: LPARAM) -> BOOL {
    if FindWindowExW(Some(hwnd), None, w!("SHELLDLL_DefView"), PCWSTR::null()).is_ok() {
        if let Ok(worker) = FindWindowExW(None, Some(hwnd), w!("WorkerW"), PCWSTR::null()) {
            *(lparam.0 as *mut HWND) = worker;
        }
    }
    BOOL(1)
}

pub fn find_desktop_worker() -> Option<HWND> {
    unsafe {
        let progman = FindWindowW(w!("Progman"), PCWSTR::null()).ok()?;
        // 0x052C: Progman에게 아이콘 뒤 WorkerW를 만들라고 요청하는 비공개 메시지
        let mut result = 0usize;
        let _ = SendMessageTimeoutW(progman, 0x052C, WPARAM(0), LPARAM(0), SMTO_NORMAL, 1000, Some(&mut result));
        let mut worker = HWND::default();
        let _ = EnumWindows(Some(find_worker), LPARAM(&mut worker as *mut HWND as isize));
        if worker.is_invalid() { None } else { Some(worker) }
    }
}

pub fn attach(child: HWND) -> bool {
    match find_desktop_worker() {
        Some(worker) => unsafe { SetParent(child, Some(worker)).is_ok() },
        None => false,
    }
}
```

- [ ] **Step 2: 컴파일 확인**

Run: `cargo build` (src-tauri에서)
Expected: 성공. 실패하면 오류 메시지대로 import 경로·인자 형태를 고친다(예: `BOOL` 위치, `Option<HWND>` 여부). 고친 내용은 Task 6 문서의 "주의점"에 적는다.

- [ ] **Step 3: Tauri 명령 등록**

`src-tauri/src/lib.rs`에 명령을 추가하고 `generate_handler!`에 넣는다.

```rust
#[tauri::command]
fn attach_to_desktop(window: tauri::WebviewWindow) -> Result<String, String> {
    let raw = window.hwnd().map_err(|e| e.to_string())?;
    let hwnd = windows::Win32::Foundation::HWND(raw.0 as _);
    if desktop::attach(hwnd) { Ok("attached".into()) } else { Err("WorkerW not found or SetParent failed".into()) }
}
```

```rust
.invoke_handler(tauri::generate_handler![attach_to_desktop])
```

- [ ] **Step 4: 버튼 연결**

`src/main.ts` 맨 위와 끝에 추가한다.

```ts
import { invoke } from "@tauri-apps/api/core";
```

```ts
document.getElementById("btn-attach")!.addEventListener("click", async () => {
  try { log(`attach: ${await invoke<string>("attach_to_desktop")}`); }
  catch (e) { log(`attach error: ${e}`); }
});
```

- [ ] **Step 5: 수동 확인 (질문 1)**

Run: `npm run tauri dev` → "배경에 붙이기" 클릭
확인하고 결과를 메모한다 (Task 6에서 문서화):
1. 로그에 `attach: attached`가 찍히는가?
2. 사각형이 바탕화면 아이콘 **뒤**에 그려지는가? (아이콘이 사각형 위에 보임)
3. 다른 창(메모장 등)을 열면 사각형이 그 창 **뒤**에 가려지는가?
4. 투명 영역이 검게 변하지 않고 배경화면이 그대로 보이는가? 애니메이션이 계속 움직이는가?
5. 사각형 위치가 붙이기 전과 같은가? (어긋나면 어느 방향으로 얼마나인지)
6. 작업 관리자에서 `explorer.exe`를 다시 시작한 뒤 사각형이 보이는가? 사라지면 "붙이기"를 다시 눌러 복구되는가?

참고: 붙인 뒤에는 디버그 패널 버튼도 아이콘 뒤라 클릭이 안 될 수 있다. 그 경우 다음 Task부터는 앱을 다시 실행해 붙이기 전에 다른 버튼을 누르거나, Task 3의 훅 로그로 확인한다.

- [ ] **Step 6: Commit**

```bash
git add spikes/background-mode
git commit -m "spike: WorkerW에 창 붙이기"
```

---

### Task 3: 질문 2 — 배경 모드 클릭 감지 (저수준 마우스 훅)

**Files:**
- Modify: `spikes/background-mode/src-tauri/src/geom.rs`
- Modify: `spikes/background-mode/src-tauri/src/hook.rs`
- Modify: `spikes/background-mode/src-tauri/src/lib.rs`
- Modify: `spikes/background-mode/src/main.ts`

**Interfaces:**
- Consumes: Task 2의 붙이기
- Produces: `geom::Rect { left, top, right, bottom: i32 }`, `Rect::contains(x, y) -> bool`, `Rect::intersects(&Rect) -> bool`; 훅 이벤트 `desktop-click` 페이로드 `{ x: i32, y: i32, foreground: String }` (물리 픽셀, 전경 창 클래스 이름)

- [ ] **Step 1: 사각형 계산 테스트 작성**

`src-tauri/src/geom.rs`:

```rust
#[derive(Clone, Copy, Debug, PartialEq, serde::Deserialize)]
pub struct Rect { pub left: i32, pub top: i32, pub right: i32, pub bottom: i32 }

#[cfg(test)]
mod tests {
    use super::*;
    const R: Rect = Rect { left: 10, top: 10, right: 20, bottom: 20 };

    #[test]
    fn contains_inside_and_edges() {
        assert!(R.contains(10, 10));
        assert!(R.contains(19, 19));
        assert!(!R.contains(20, 20)); // right/bottom 은 포함하지 않는다
        assert!(!R.contains(9, 15));
    }

    #[test]
    fn intersects_overlap_and_touching() {
        assert!(R.intersects(&Rect { left: 15, top: 15, right: 30, bottom: 30 }));
        assert!(!R.intersects(&Rect { left: 20, top: 10, right: 30, bottom: 20 })); // 맞닿기만 함
        assert!(!R.intersects(&Rect { left: 0, top: 0, right: 5, bottom: 5 }));
    }
}
```

- [ ] **Step 2: 실패 확인**

Run: `cargo test geom` (src-tauri에서)
Expected: FAIL — `no method named contains`

- [ ] **Step 3: 구현**

`geom.rs`의 `struct` 아래에 추가한다.

```rust
impl Rect {
    pub fn contains(&self, x: i32, y: i32) -> bool {
        x >= self.left && x < self.right && y >= self.top && y < self.bottom
    }
    pub fn intersects(&self, o: &Rect) -> bool {
        self.left < o.right && o.left < self.right && self.top < o.bottom && o.top < self.bottom
    }
}
```

- [ ] **Step 4: 통과 확인**

Run: `cargo test geom`
Expected: 2 passed

- [ ] **Step 5: 마우스 훅 구현**

`src-tauri/src/hook.rs`:

```rust
use std::sync::OnceLock;
use tauri::{AppHandle, Emitter};
use windows::Win32::Foundation::{LPARAM, LRESULT, WPARAM};
use windows::Win32::UI::WindowsAndMessaging::{
    CallNextHookEx, GetMessageW, SetWindowsHookExW, MSG, MSLLHOOKSTRUCT, WH_MOUSE_LL, WM_LBUTTONDOWN,
};

static APP: OnceLock<AppHandle> = OnceLock::new();

#[derive(Clone, serde::Serialize)]
struct Click { x: i32, y: i32, foreground: String }

unsafe extern "system" fn mouse_proc(code: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if code >= 0 && wparam.0 as u32 == WM_LBUTTONDOWN {
        let info = &*(lparam.0 as *const MSLLHOOKSTRUCT);
        if let Some(app) = APP.get() {
            let _ = app.emit("desktop-click", Click { x: info.pt.x, y: info.pt.y, foreground: crate::desktop::foreground_class() });
        }
    }
    // 클릭을 가로채지 않고 항상 다음 훅으로 넘긴다 (아이콘 동작 유지)
    CallNextHookEx(None, code, wparam, lparam)
}

pub fn start(app: AppHandle) {
    let _ = APP.set(app);
    std::thread::spawn(|| unsafe {
        let _hook = SetWindowsHookExW(WH_MOUSE_LL, Some(mouse_proc), None, 0).expect("SetWindowsHookExW");
        let mut msg = MSG::default();
        // 저수준 훅은 이 스레드에 메시지 루프가 있어야 호출된다
        while GetMessageW(&mut msg, None, 0, 0).as_bool() {}
    });
}
```

`desktop.rs`에 전경 창 클래스 함수를 추가한다.

```rust
use windows::Win32::UI::WindowsAndMessaging::{GetClassNameW, GetForegroundWindow};

pub fn foreground_class() -> String {
    unsafe {
        let mut buf = [0u16; 256];
        let n = GetClassNameW(GetForegroundWindow(), &mut buf);
        String::from_utf16_lossy(&buf[..n as usize])
    }
}
```

`lib.rs`의 `setup` 끝(`Ok(())` 앞)에 추가한다.

```rust
hook::start(app.handle().clone());
```

- [ ] **Step 6: 프론트엔드에서 강아지 영역 판정**

`src/main.ts`에 추가한다. 훅 좌표는 물리 픽셀이므로 `devicePixelRatio`로 CSS 픽셀로 바꾼다(창이 주 모니터 원점에 있다는 전제).

```ts
import { listen } from "@tauri-apps/api/event";

type Click = { x: number; y: number; foreground: string };
listen<Click>("desktop-click", (e) => {
  const dpr = window.devicePixelRatio;
  const cx = e.payload.x / dpr;
  const cy = e.payload.y / dpr;
  const r = dog.getBoundingClientRect();
  const onDog = cx >= r.left && cx < r.right && cy >= r.top && cy < r.bottom;
  log(`click phys=(${e.payload.x},${e.payload.y}) css=(${cx.toFixed(0)},${cy.toFixed(0)}) fg=${e.payload.foreground} onDog=${onDog}`);
});
```

- [ ] **Step 7: 수동 확인 (질문 2)**

Run: `npm run tauri dev` → "배경에 붙이기" → 바탕화면이 보이게 둔다
확인하고 결과를 메모한다:
1. 사각형을 클릭하면 `onDog=true`, 빈 바탕화면을 클릭하면 `onDog=false`가 찍히는가?
2. 바탕화면을 클릭했을 때 `fg=`가 `Progman` 또는 `WorkerW`인가? 다른 창을 클릭했을 때는 그 창의 클래스인가? (→ "바탕화면이 보이는 상태에서의 클릭"만 골라낼 수 있는지)
3. 아이콘 클릭·더블클릭으로 실행·드래그 선택이 평소대로 되는가?
4. Windows 디스플레이 배율을 100% → 125%(또는 150%)로 바꾸고 앱을 다시 실행했을 때도 1번이 맞는가?
5. 훅 때문에 마우스가 느려지는 느낌이 있는가?

- [ ] **Step 8: Commit**

```bash
git add spikes/background-mode
git commit -m "spike: 저수준 마우스 훅으로 배경 모드 클릭 감지"
```

---

### Task 4: 질문 3·4 — 말풍선 가림 판정, 바탕화면 노출, 마지막 입력

**Files:**
- Modify: `spikes/background-mode/src-tauri/src/occlusion.rs`
- Modify: `spikes/background-mode/src-tauri/src/desktop.rs`
- Modify: `spikes/background-mode/src-tauri/src/lib.rs`
- Modify: `spikes/background-mode/src/main.ts`

**Interfaces:**
- Consumes: `geom::Rect`, `desktop::foreground_class()`
- Produces: `occlusion::covering_windows(region: Rect, own: HWND) -> Vec<String>` (영역을 덮는 창들의 클래스 이름), `desktop::idle_ms() -> u32`, Tauri 명령 `region_covered_by(region: Rect) -> Result<Vec<String>, String>`, `desktop_status() -> Status { foreground: String, desktop_exposed: bool, idle_ms: u32 }`

- [ ] **Step 1: 가림 판정 구현**

`src-tauri/src/occlusion.rs`. 배경 모드 창은 아이콘 뒤에 있으므로, 보이는 최상위 창 가운데 영역과 겹치는 것이 있으면 가려진 것이다. 최소화된 창과 숨겨진(cloaked) 창은 제외한다. Windows 10 창 테두리의 보이지 않는 그림자를 빼려고 `DWMWA_EXTENDED_FRAME_BOUNDS`를 쓴다.

```rust
use crate::geom::Rect;
use windows::core::BOOL;
use windows::Win32::Foundation::{HWND, LPARAM, RECT};
use windows::Win32::Graphics::Dwm::{DwmGetWindowAttribute, DWMWA_CLOAKED, DWMWA_EXTENDED_FRAME_BOUNDS};
use windows::Win32::UI::WindowsAndMessaging::{EnumWindows, GetClassNameW, IsIconic, IsWindowVisible};

struct Ctx { region: Rect, own: HWND, hits: Vec<String> }

const IGNORED: [&str; 2] = ["Progman", "WorkerW"];

unsafe extern "system" fn visit(hwnd: HWND, lparam: LPARAM) -> BOOL {
    let ctx = &mut *(lparam.0 as *mut Ctx);
    if hwnd == ctx.own || !IsWindowVisible(hwnd).as_bool() || IsIconic(hwnd).as_bool() {
        return BOOL(1);
    }
    let mut cloaked = 0u32;
    let _ = DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, &mut cloaked as *mut _ as _, 4);
    if cloaked != 0 { return BOOL(1); }

    let mut buf = [0u16; 256];
    let n = GetClassNameW(hwnd, &mut buf);
    let class = String::from_utf16_lossy(&buf[..n as usize]);
    if IGNORED.contains(&class.as_str()) { return BOOL(1); }

    let mut r = RECT::default();
    if DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, &mut r as *mut _ as _, std::mem::size_of::<RECT>() as u32).is_ok() {
        let w = Rect { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
        if w.intersects(&ctx.region) { ctx.hits.push(class); }
    }
    BOOL(1)
}

pub fn covering_windows(region: Rect, own: HWND) -> Vec<String> {
    let mut ctx = Ctx { region, own, hits: Vec::new() };
    unsafe { let _ = EnumWindows(Some(visit), LPARAM(&mut ctx as *mut Ctx as isize)); }
    ctx.hits
}
```

- [ ] **Step 2: 노출·마지막 입력 구현**

`desktop.rs`에 추가한다.

```rust
use windows::Win32::System::SystemInformation::GetTickCount;
use windows::Win32::UI::Input::KeyboardAndMouse::{GetLastInputInfo, LASTINPUTINFO};

pub fn idle_ms() -> u32 {
    unsafe {
        let mut li = LASTINPUTINFO { cbSize: std::mem::size_of::<LASTINPUTINFO>() as u32, dwTime: 0 };
        let _ = GetLastInputInfo(&mut li);
        GetTickCount().wrapping_sub(li.dwTime)
    }
}
```

- [ ] **Step 3: 명령 등록**

`lib.rs`에 추가하고 `generate_handler![attach_to_desktop, region_covered_by, desktop_status]`로 바꾼다.

```rust
#[tauri::command]
fn region_covered_by(window: tauri::WebviewWindow, region: geom::Rect) -> Result<Vec<String>, String> {
    let raw = window.hwnd().map_err(|e| e.to_string())?;
    Ok(occlusion::covering_windows(region, windows::Win32::Foundation::HWND(raw.0 as _)))
}

#[derive(serde::Serialize)]
struct Status { foreground: String, desktop_exposed: bool, idle_ms: u32 }

#[tauri::command]
fn desktop_status() -> Status {
    let fg = desktop::foreground_class();
    Status { desktop_exposed: fg == "Progman" || fg == "WorkerW", foreground: fg, idle_ms: desktop::idle_ms() }
}
```

- [ ] **Step 4: 프론트엔드에서 주기적으로 기록**

`src/main.ts`에 추가한다. 붙인 뒤에는 버튼을 누를 수 없으므로 3초마다 자동으로 로그를 남긴다. 말풍선 영역은 CSS 픽셀 → 물리 픽셀로 바꿔 넘긴다.

```ts
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
```

- [ ] **Step 5: 수동 확인 (질문 3·4)**

Run: `npm run tauri dev` → "배경에 붙이기"
확인하고 결과를 메모한다:
1. 말풍선 위에 아무 창도 없을 때 `covered=false`인가?
2. 메모장 창을 말풍선 위로 옮기면 `covered=true by=[Notepad]`인가? 옆으로 치우면 다시 `false`인가?
3. 강아지가 걸어가다 작업 표시줄 근처에 있을 때 `Shell_TrayWnd`가 덮는 창으로 나오는가? (Review Focus 5)
4. 항상 덮는 것으로 잘못 나오는 창이 있는가? (있으면 클래스 이름을 기록 — 본 구현에서 제외 목록에 넣을 후보)
5. Win+D를 누르면 `exposed=true`이고 강아지가 계속 보이는가? 다른 창을 클릭하면 `exposed=false`인가? (Review Focus 4)
6. 마우스·키보드를 10초 이상 건드리지 않으면 `idle`이 10000 이상으로 커지고, 움직이면 작게 돌아가는가?

- [ ] **Step 6: Commit**

```bash
git add spikes/background-mode
git commit -m "spike: 말풍선 가림, 바탕화면 노출, 마지막 입력 감지"
```

---

### Task 5: 오버레이 모드 확인 (대조군)

배경 모드와 비교하기 위해 같은 앱에서 오버레이 모드의 핵심 동작도 한 번 확인한다. 본 구현에서 오버레이 클릭 통과 방식을 정할 근거가 된다.

**Files:**
- Modify: `spikes/background-mode/src-tauri/src/lib.rs`
- Modify: `spikes/background-mode/src/main.ts`

**Interfaces:**
- Consumes: `desktop-click` 이벤트, `Rect`
- Produces: Tauri 명령 `set_overlay(enabled: bool)`. 커서 위치에 따라 클릭 통과를 켜고 끄는 프론트엔드 루프.

- [ ] **Step 1: 오버레이 명령 추가**

`lib.rs`에 추가하고 `generate_handler!`에 `set_overlay`를 넣는다.

```rust
#[tauri::command]
fn set_overlay(window: tauri::WebviewWindow, enabled: bool) -> Result<(), String> {
    window.set_always_on_top(enabled).map_err(|e| e.to_string())?;
    window.set_ignore_cursor_events(enabled).map_err(|e| e.to_string())
}

#[tauri::command]
fn set_click_through(window: tauri::WebviewWindow, through: bool) -> Result<(), String> {
    window.set_ignore_cursor_events(through).map_err(|e| e.to_string())
}
```

`generate_handler![attach_to_desktop, region_covered_by, desktop_status, set_overlay, set_click_through]`

- [ ] **Step 2: 커서가 강아지 위에 있을 때만 클릭 받기**

클릭 통과 중에는 웹뷰가 마우스 이동을 받지 못하므로, Task 3의 훅 대신 Rust 쪽 커서 위치를 폴링한다. `desktop.rs`에 추가한다.

```rust
use windows::Win32::Foundation::POINT;
use windows::Win32::UI::WindowsAndMessaging::GetCursorPos;

pub fn cursor() -> (i32, i32) {
    let mut p = POINT::default();
    unsafe { let _ = GetCursorPos(&mut p); }
    (p.x, p.y)
}
```

`lib.rs`에 명령을 추가하고 `generate_handler!`에 `cursor_pos`를 넣는다.

```rust
#[tauri::command]
fn cursor_pos() -> (i32, i32) { desktop::cursor() }
```

`src/main.ts`에 추가한다. URL에 `?overlay`가 있으면 오버레이 모드로 시작한다.

```ts
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
  dog.addEventListener("click", () => log("overlay: dog clicked"));
  log("overlay mode");
}
if (location.search.includes("overlay")) startOverlay();
```

`tauri.conf.json`의 창 `url`을 잠시 `index.html?overlay`로 바꿔 실행한다. 확인 후 원래대로 돌린다.

- [ ] **Step 3: 수동 확인**

Run: `npm run tauri dev`
1. 강아지가 다른 창들 위에 보이는가?
2. 강아지 밖을 클릭하면 아래 창이 클릭되는가(통과)?
3. 강아지를 클릭하면 `overlay: dog clicked`가 찍히는가?
4. 50ms 폴링 때 CPU 사용률은 어느 정도인가? (작업 관리자에서 확인)

- [ ] **Step 4: Commit**

```bash
git add spikes/background-mode
git commit -m "spike: 오버레이 모드 클릭 통과 대조 확인"
```

---

### Task 6: 결과 문서화

**Files:**
- Create: `docs/spikes/background-mode.md` (`docs/harness-setup` 브랜치)
- Modify: `README.md` (문서 지도에 링크가 이미 있음 — 확인만)
- Modify: `docs/superpowers/specs/2026-10-14-windows-desktop-pet-design.md` (결과에 따라 8절 상태만 갱신)

**Interfaces:**
- Consumes: Task 2~5에서 메모한 결과

- [ ] **Step 1: docs 브랜치로 이동**

```bash
git checkout docs/harness-setup
```

스파이크 코드는 `spike/background-mode` 브랜치에 남고 이 브랜치에는 들어오지 않는다.

- [ ] **Step 2: 결과 문서 작성**

`docs/spikes/background-mode.md`를 다음 틀로 쓴다. 각 칸은 메모한 실제 결과로 채운다. 결과를 모르는 칸이 남으면 해당 Task로 돌아가 확인한다.

```markdown
# 배경 모드 스파이크 결과

- 날짜: 2026-10-14
- 환경: Windows 10 Pro 19045.6466, Tauri <버전>, windows 크레이트 <버전>, 디스플레이 배율 <확인한 값들>
- 코드: `spike/background-mode` 브랜치 `spikes/background-mode/` (버림. 머지하지 않음)

## 요약

| 질문 | 결과 | 한 줄 설명 |
|---|---|---|
| 1. 아이콘 뒤 레이어에 붙이기 | 된다 / 안 된다 / 조건부 | |
| 2. 배경 모드 클릭 감지 | | |
| 3. 말풍선 가림 판정 | | |
| 4. 바탕화면 노출·마지막 입력 | | |
| (대조) 오버레이 클릭 통과 | | |

## 질문별 상세

### 1. 아이콘 뒤 레이어에 붙이기
- 사용한 API: `FindWindowW("Progman")`, `SendMessageTimeoutW(0x052C)`, `EnumWindows` + `FindWindowExW("SHELLDLL_DefView")`, `SetParent`
- 확인 결과: (Task 2 Step 5의 1~6번)
- 주의점: (탐색기 재시작, 좌표 어긋남, 컴파일하며 고친 API 형태 등)

### 2. 배경 모드 클릭 감지
- 사용한 API: `SetWindowsHookExW(WH_MOUSE_LL)`, `GetForegroundWindow` + `GetClassNameW`
- 확인 결과: (Task 3 Step 7의 1~5번, 배율별)
- 주의점:

### 3. 말풍선 가림 판정
- 사용한 API: `EnumWindows`, `IsWindowVisible`, `IsIconic`, `DwmGetWindowAttribute(DWMWA_CLOAKED, DWMWA_EXTENDED_FRAME_BOUNDS)`
- 확인 결과: (Task 4 Step 5의 1~4번)
- 제외해야 할 창 클래스:

### 4. 바탕화면 노출·마지막 입력
- 사용한 API: `GetForegroundWindow` 클래스 비교, `GetLastInputInfo` + `GetTickCount`
- 확인 결과: (Task 4 Step 5의 5~6번)

### 대조: 오버레이 모드
- 확인 결과: (Task 5 Step 3)

## 본 구현에 주는 결론

- 배경 모드 설계(스펙 3.2절)를 그대로 갈 수 있는가, 바꿔야 하는가:
- 몸체 계획에 반영할 것:
```

- [ ] **Step 3: 스펙 8절에 결과 링크 추가**

`docs/superpowers/specs/2026-10-14-windows-desktop-pet-design.md` 8절 끝에 한 줄 추가한다.

```markdown
**결과**: [docs/spikes/background-mode.md](../../spikes/background-mode.md)
```

- [ ] **Step 4: 실패한 질문이 있으면 사용자에게 보고**

스펙 8절의 "실패 시"에 해당하면(질문 1 또는 2가 "안 된다"), 문서를 커밋한 뒤 몸체 계획으로 넘어가지 말고 사용자와 대안을 정한다. 정한 결과는 새 결정 기록(`docs/decisions/0009-...`)으로 남긴다.

- [ ] **Step 5: Commit**

```bash
git add docs/spikes/background-mode.md docs/superpowers/specs/2026-10-14-windows-desktop-pet-design.md
git commit -m "docs: 배경 모드 스파이크 결과"
```
