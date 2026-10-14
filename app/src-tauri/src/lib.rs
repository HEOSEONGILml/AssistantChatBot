use tauri::Manager;

mod geom;
mod signals;

#[tauri::command]
fn region_covered(window: tauri::WebviewWindow, region: geom::Rect) -> Result<bool, String> {
    let raw = window.hwnd().map_err(|e| e.to_string())?;
    let above = signals::windows_above(windows::Win32::Foundation::HWND(raw.0 as _));
    Ok(geom::covered(&region, &above))
}

#[tauri::command]
fn cursor_pos() -> (i32, i32) { signals::cursor() }

#[tauri::command]
fn idle_ms() -> u32 { signals::idle_ms() }

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let win = app.get_webview_window("character").expect("character window");
            if let Some(mon) = win.primary_monitor()? {
                win.set_position(*mon.position())?;
                win.set_size(*mon.size())?;
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![region_covered, cursor_pos, idle_ms])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
