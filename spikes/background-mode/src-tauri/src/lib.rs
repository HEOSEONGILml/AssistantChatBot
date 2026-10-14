mod desktop;
mod geom;
mod hook;
mod occlusion;

use tauri::Manager;

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
        .invoke_handler(tauri::generate_handler![])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
