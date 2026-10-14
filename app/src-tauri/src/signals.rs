use windows::Win32::Foundation::POINT;
use windows::Win32::System::SystemInformation::GetTickCount;
use windows::Win32::UI::Input::KeyboardAndMouse::{GetAsyncKeyState, GetLastInputInfo, LASTINPUTINFO, VK_LBUTTON};
use windows::Win32::UI::WindowsAndMessaging::GetCursorPos;

pub fn cursor() -> (i32, i32) {
    let mut p = POINT::default();
    unsafe { let _ = GetCursorPos(&mut p); }
    (p.x, p.y)
}

/// 마우스 왼쪽 버튼이 지금 눌려 있는지 (다른 창 위에서의 클릭도 감지된다)
pub fn left_down() -> bool {
    unsafe { (GetAsyncKeyState(VK_LBUTTON.0 as i32) as u16 & 0x8000) != 0 }
}

pub fn idle_ms() -> u32 {
    unsafe {
        let mut li = LASTINPUTINFO { cbSize: std::mem::size_of::<LASTINPUTINFO>() as u32, dwTime: 0 };
        let _ = GetLastInputInfo(&mut li);
        GetTickCount().wrapping_sub(li.dwTime)
    }
}

use windows::core::BOOL;
use windows::Win32::Foundation::{HWND, LPARAM, RECT};
use windows::Win32::Graphics::Dwm::{DwmGetWindowAttribute, DWMWA_CLOAKED, DWMWA_EXTENDED_FRAME_BOUNDS};
use windows::Win32::UI::WindowsAndMessaging::{
    EnumWindows, GetClassNameW, GetForegroundWindow, GetWindowLongPtrW, GetWindowTextLengthW, GetWindowThreadProcessId,
    IsIconic, IsWindowVisible, GWL_EXSTYLE, WS_EX_TOOLWINDOW,
};

/// 강아지가 반응할 창 하나. 위치·크기(물리 px)와 사용 중인지만 담는다. 제목·내용은 읽지 않는다.
#[derive(serde::Serialize)]
pub struct WinInfo { pub id: isize, pub left: i32, pub top: i32, pub right: i32, pub bottom: i32, pub active: bool }

const MIN_SIZE: i32 = 200; // 너무 작은 창(팝업·알림 등)은 뺀다
const IGNORED_CLASSES: [&str; 4] = ["Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"];

struct Ctx { own_pid: u32, fg: HWND, out: Vec<WinInfo> }

unsafe extern "system" fn visit(hwnd: HWND, lparam: LPARAM) -> BOOL {
    unsafe {
        let ctx = &mut *(lparam.0 as *mut Ctx);
        if !IsWindowVisible(hwnd).as_bool() || IsIconic(hwnd).as_bool() { return BOOL(1); }
        // 작업 표시줄에 안 나오는 보조 창과 제목 없는 내부 창은 뺀다 (제목 길이만 보고 내용은 읽지 않는다)
        if (GetWindowLongPtrW(hwnd, GWL_EXSTYLE) as u32) & WS_EX_TOOLWINDOW.0 != 0 { return BOOL(1); }
        if GetWindowTextLengthW(hwnd) == 0 { return BOOL(1); }
        let mut pid = 0u32;
        GetWindowThreadProcessId(hwnd, Some(&mut pid));
        if pid == ctx.own_pid { return BOOL(1); }
        let mut cloaked = 0u32;
        let _ = DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, &mut cloaked as *mut _ as _, 4);
        if cloaked != 0 { return BOOL(1); }
        let mut buf = [0u16; 64];
        let n = GetClassNameW(hwnd, &mut buf);
        if IGNORED_CLASSES.contains(&String::from_utf16_lossy(&buf[..n as usize]).as_str()) { return BOOL(1); }
        let mut r = RECT::default();
        if DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, &mut r as *mut _ as _, std::mem::size_of::<RECT>() as u32).is_err() { return BOOL(1); }
        if r.right - r.left < MIN_SIZE || r.bottom - r.top < MIN_SIZE { return BOOL(1); }
        ctx.out.push(WinInfo { id: hwnd.0 as isize, left: r.left, top: r.top, right: r.right, bottom: r.bottom, active: hwnd == ctx.fg });
        BOOL(1)
    }
}

/// 보이는 최상위 창 목록 (위에 있는 창부터)
pub fn windows() -> Vec<WinInfo> {
    let mut ctx = Ctx { own_pid: std::process::id(), fg: unsafe { GetForegroundWindow() }, out: Vec::new() };
    unsafe { let _ = EnumWindows(Some(visit), LPARAM(&mut ctx as *mut Ctx as isize)); }
    ctx.out
}
