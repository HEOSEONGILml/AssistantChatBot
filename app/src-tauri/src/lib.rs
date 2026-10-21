use tauri::{Manager, RunEvent, menu::{Menu, MenuItem}, tray::TrayIconBuilder};

mod brain;

#[tauri::command] fn brain_endpoint() -> Result<brain::Endpoint, String> { brain::endpoint() }
#[tauri::command] fn brain_start(state: tauri::State<brain::BrainProcess>) -> Result<(), String> { brain::ensure_running(&state) }

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(brain::BrainProcess(std::sync::Mutex::new(None)))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .setup(|app| {
            let settings_i = MenuItem::with_id(app, "settings", "설정", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&settings_i, &quit_i])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("TamagotchiChatBot")
                .menu(&menu)
                .show_menu_on_left_click(true)
                .on_menu_event(|app, event| match event.id.as_ref() {
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
        .invoke_handler(tauri::generate_handler![brain_endpoint, brain_start])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            // 앱이 끝나면 이 앱이 띄운 백엔드도 끈다
            if let RunEvent::Exit = event { brain::stop(&app.state::<brain::BrainProcess>()); }
        });
}
