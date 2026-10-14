use windows::core::{w, BOOL, PCWSTR};
use windows::Win32::Foundation::{HWND, LPARAM, WPARAM};
use windows::Win32::UI::WindowsAndMessaging::{
    EnumWindows, FindWindowExW, FindWindowW, SendMessageTimeoutW, SetParent, SMTO_NORMAL,
};

// 아이콘(SHELLDLL_DefView)을 가진 최상위 창의 바로 다음 WorkerW가 아이콘 뒤 레이어다.
unsafe extern "system" fn find_worker(hwnd: HWND, lparam: LPARAM) -> BOOL {
    unsafe {
        if FindWindowExW(Some(hwnd), None, w!("SHELLDLL_DefView"), PCWSTR::null()).is_ok() {
            if let Ok(worker) = FindWindowExW(None, Some(hwnd), w!("WorkerW"), PCWSTR::null()) {
                *(lparam.0 as *mut HWND) = worker;
            }
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

use windows::Win32::Foundation::COLORREF;
use windows::Win32::UI::WindowsAndMessaging::{
    GetWindowLongPtrW, SetLayeredWindowAttributes, SetWindowLongPtrW, GWL_EXSTYLE, LWA_COLORKEY, WS_EX_LAYERED,
};

// 가설 1 검증: 자식 창에서 알파 투명이 안 되면, 마젠타(#FF00FF)를 색상 키로 투명 처리한다.
pub fn set_color_key(hwnd: HWND) -> bool {
    unsafe {
        let ex = GetWindowLongPtrW(hwnd, GWL_EXSTYLE);
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED.0 as isize);
        SetLayeredWindowAttributes(hwnd, COLORREF(0x00FF00FF), 0, LWA_COLORKEY).is_ok()
    }
}

use windows::Win32::UI::WindowsAndMessaging::{SystemParametersInfoW, SPI_GETDESKWALLPAPER, SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS};

// 가설 2 검증: 현재 배경화면 파일 경로
pub fn wallpaper_path() -> Option<String> {
    let mut buf = [0u16; 1024];
    unsafe {
        SystemParametersInfoW(SPI_GETDESKWALLPAPER, buf.len() as u32, Some(buf.as_mut_ptr() as _), SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS(0)).ok()?;
    }
    let n = buf.iter().position(|&c| c == 0).unwrap_or(0);
    if n == 0 { None } else { Some(String::from_utf16_lossy(&buf[..n])) }
}

use windows::Win32::UI::WindowsAndMessaging::{GetClassNameW, GetForegroundWindow};

pub fn foreground_class() -> String {
    unsafe {
        let mut buf = [0u16; 256];
        let n = GetClassNameW(GetForegroundWindow(), &mut buf);
        String::from_utf16_lossy(&buf[..n as usize])
    }
}

use windows::Win32::System::SystemInformation::GetTickCount;
use windows::Win32::UI::Input::KeyboardAndMouse::{GetLastInputInfo, LASTINPUTINFO};

pub fn idle_ms() -> u32 {
    unsafe {
        let mut li = LASTINPUTINFO { cbSize: std::mem::size_of::<LASTINPUTINFO>() as u32, dwTime: 0 };
        let _ = GetLastInputInfo(&mut li);
        GetTickCount().wrapping_sub(li.dwTime)
    }
}
