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
    unsafe {
        if code >= 0 && wparam.0 as u32 == WM_LBUTTONDOWN {
            let info = &*(lparam.0 as *const MSLLHOOKSTRUCT);
            if let Some(app) = APP.get() {
                let _ = app.emit("desktop-click", Click { x: info.pt.x, y: info.pt.y, foreground: crate::desktop::foreground_class() });
            }
        }
        // 클릭을 가로채지 않고 항상 다음 훅으로 넘긴다 (아이콘 동작 유지)
        CallNextHookEx(None, code, wparam, lparam)
    }
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
