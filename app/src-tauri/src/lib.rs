use tauri::{Manager, RunEvent, menu::{Menu, MenuItem}, tray::TrayIconBuilder};

mod backend;

#[tauri::command] fn backend_endpoint() -> Result<backend::Endpoint, String> { backend::endpoint() }
#[tauri::command] fn backend_start(state: tauri::State<backend::BackendProcess>) -> Result<(), String> { backend::ensure_running(&state) }

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(backend::BackendProcess(std::sync::Mutex::new(None)))
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let quit_i = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&quit_i])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("TamagotchiChatBot")
                .menu(&menu)
                .show_menu_on_left_click(true)
                .on_menu_event(|app, event| if event.id.as_ref() == "quit" { app.exit(0) })
                .build(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            // 상세 창은 닫기 버튼을 눌러도 숨기기만 한다(다시 열 때 같은 창을 쓴다)
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "detail" { api.prevent_close(); let _ = window.hide(); }
            }
        })
        .invoke_handler(tauri::generate_handler![backend_endpoint, backend_start])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            // 앱이 끝나면 이 앱이 띄운 백엔드도 프로세스 트리째 끈다
            if let RunEvent::Exit = event { backend::stop(&app.state::<backend::BackendProcess>()); }
        });
}
