mod token_bound;
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_mobile_core::init())
        .run(tauri::generate_context!())
        .expect("dreamtalk host initialization failed");
}
