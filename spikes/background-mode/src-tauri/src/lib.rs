mod desktop;
mod geom;
mod hook;
mod occlusion;

use tauri::Manager;

#[tauri::command]
fn spike_mode() -> String { std::env::var("SPIKE_MODE").unwrap_or_default() }

#[tauri::command]
fn wallpaper_bytes() -> Result<tauri::ipc::Response, String> {
    let path = desktop::wallpaper_path().ok_or("no wallpaper path")?;
    let bytes = std::fs::read(&path).map_err(|e| format!("{path}: {e}"))?;
    Ok(tauri::ipc::Response::new(bytes))
}

#[tauri::command]
fn attach_to_desktop(window: tauri::WebviewWindow) -> Result<String, String> {
    let raw = window.hwnd().map_err(|e| e.to_string())?;
    let hwnd = windows::Win32::Foundation::HWND(raw.0 as _);
    if desktop::attach(hwnd) { Ok("attached".into()) } else { Err("WorkerW not found or SetParent failed".into()) }
}

#[tauri::command]
fn attach_color_key(window: tauri::WebviewWindow) -> Result<String, String> {
    let raw = window.hwnd().map_err(|e| e.to_string())?;
    let hwnd = windows::Win32::Foundation::HWND(raw.0 as _);
    // 시도 2: 최상위 창일 때 색상 키를 먼저 설정하고 나서 붙인다
    let key = desktop::set_color_key(hwnd);
    if !desktop::attach(hwnd) { return Err("attach failed".into()); }
    Ok(format!("color_key_before={}, attached", key))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let win = app.get_webview_window("main").expect("main window");
            if let Some(mon) = win.primary_monitor()? {
                win.set_position(*mon.position())?;
                win.set_size(*mon.size())?;
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![attach_to_desktop, attach_color_key, wallpaper_bytes, spike_mode])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
