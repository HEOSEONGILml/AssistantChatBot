use crate::geom::Rect;
use windows::Win32::Foundation::{HWND, POINT, RECT};
use windows::Win32::Graphics::Dwm::{DwmGetWindowAttribute, DWMWA_CLOAKED, DWMWA_EXTENDED_FRAME_BOUNDS};
use windows::Win32::System::SystemInformation::GetTickCount;
use windows::Win32::UI::Input::KeyboardAndMouse::{GetLastInputInfo, LASTINPUTINFO};
use windows::Win32::UI::WindowsAndMessaging::{GetCursorPos, GetWindow, IsIconic, IsWindowVisible, GW_HWNDPREV};

/// 우리 창보다 z-순서가 위이고, 보이며, 최소화·cloaked가 아닌 최상위 창들의 영역
pub fn windows_above(own: HWND) -> Vec<Rect> {
    let mut out = Vec::new();
    unsafe {
        let mut h = GetWindow(own, GW_HWNDPREV);
        while let Ok(w) = h {
            if w.is_invalid() { break; }
            let mut cloaked = 0u32;
            let _ = DwmGetWindowAttribute(w, DWMWA_CLOAKED, &mut cloaked as *mut _ as _, 4);
            if IsWindowVisible(w).as_bool() && !IsIconic(w).as_bool() && cloaked == 0 {
                let mut r = RECT::default();
                if DwmGetWindowAttribute(w, DWMWA_EXTENDED_FRAME_BOUNDS, &mut r as *mut _ as _, std::mem::size_of::<RECT>() as u32).is_ok() {
                    out.push(Rect { left: r.left, top: r.top, right: r.right, bottom: r.bottom });
                }
            }
            h = GetWindow(w, GW_HWNDPREV);
        }
    }
    out
}

pub fn cursor() -> (i32, i32) {
    let mut p = POINT::default();
    unsafe { let _ = GetCursorPos(&mut p); }
    (p.x, p.y)
}

pub fn idle_ms() -> u32 {
    unsafe {
        let mut li = LASTINPUTINFO { cbSize: std::mem::size_of::<LASTINPUTINFO>() as u32, dwTime: 0 };
        let _ = GetLastInputInfo(&mut li);
        GetTickCount().wrapping_sub(li.dwTime)
    }
}
