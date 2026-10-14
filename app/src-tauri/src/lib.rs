use tauri::{Emitter, Manager, menu::{Menu, MenuItem}, tray::TrayIconBuilder};

mod geom;
mod keys;
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

#[tauri::command] fn key_set(name: String, value: String) -> Result<(), String> { keys::set(&name, &value) }
#[tauri::command] fn key_has(name: String) -> Result<bool, String> { keys::has(&name) }
#[tauri::command] fn key_delete(name: String) -> Result<(), String> { keys::delete(&name) }

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .setup(|app| {
            let win = app.get_webview_window("character").expect("character window");
            if let Some(mon) = win.primary_monitor()? {
                win.set_position(*mon.position())?;
                win.set_size(*mon.size())?;
            }

            let house_i = MenuItem::with_id(app, "house", "강아지 집에 넣기/꺼내기", true, None::<&str>)?;
            let settings_i = MenuItem::with_id(app, "settings", "설정", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&house_i, &settings_i, &quit_i])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("TamagotchiChatBot")
                .menu(&menu)
                .show_menu_on_left_click(true)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "house" => { let _ = app.emit_to("character", "toggle-house", ()); }
                    "settings" => {
                        if let Some(w) = app.get_webview_window("settings") { let _ = w.show(); let _ = w.set_focus(); }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            // 설정 창은 닫기 버튼을 눌러도 숨기기만 한다
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "settings" { api.prevent_close(); let _ = window.hide(); }
            }
        })
        .invoke_handler(tauri::generate_handler![region_covered, cursor_pos, idle_ms, key_set, key_has, key_delete])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
