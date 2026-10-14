use crate::geom::Rect;
use windows::core::BOOL;
use windows::Win32::Foundation::{HWND, LPARAM, RECT};
use windows::Win32::Graphics::Dwm::{DwmGetWindowAttribute, DWMWA_CLOAKED, DWMWA_EXTENDED_FRAME_BOUNDS};
use windows::Win32::UI::WindowsAndMessaging::{EnumWindows, GetClassNameW, IsIconic, IsWindowVisible};

struct Ctx { region: Rect, own: HWND, hits: Vec<String> }

const IGNORED: [&str; 2] = ["Progman", "WorkerW"];

unsafe extern "system" fn visit(hwnd: HWND, lparam: LPARAM) -> BOOL {
    unsafe {
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
}

pub fn covering_windows(region: Rect, own: HWND) -> Vec<String> {
    let mut ctx = Ctx { region, own, hits: Vec::new() };
    unsafe { let _ = EnumWindows(Some(visit), LPARAM(&mut ctx as *mut Ctx as isize)); }
    ctx.hits
}
