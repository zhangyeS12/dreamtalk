//! Official Tauri lifecycle components; startup registration requires a UI action.
use serde::{Deserialize, Serialize};
use std::{
    path::PathBuf,
    sync::{
        atomic::{AtomicU64, Ordering},
        Mutex,
    },
};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, TrayIconBuilder, TrayIconEvent},
    Manager, State,
};
use tauri_plugin_autostart::ManagerExt;

#[derive(Clone, Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Preferences {
    pub close_to_tray: bool,
}

pub struct BackgroundState {
    path: PathBuf,
    preferences: Mutex<Preferences>,
    sequence: AtomicU64,
}
impl BackgroundState {
    pub fn load(app_data: &std::path::Path) -> Self {
        let path = app_data.join("config").join("desktop-background.json");
        let preferences = std::fs::read(&path)
            .ok()
            .and_then(|bytes| serde_json::from_slice(&bytes).ok())
            .unwrap_or_default();
        Self {
            path,
            preferences: Mutex::new(preferences),
            sequence: AtomicU64::new(0),
        }
    }
    pub fn closes_to_tray(&self) -> bool {
        self.preferences
            .lock()
            .map(|p| p.close_to_tray)
            .unwrap_or(false)
    }
}
#[derive(Serialize)]
pub struct BackgroundStatus {
    pub autostart: bool,
    pub close_to_tray: bool,
    pub window_visible: bool,
}
pub fn show_main(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}
#[tauri::command]
pub fn desktop_background_status(
    app: tauri::AppHandle,
    state: State<'_, BackgroundState>,
) -> Result<BackgroundStatus, String> {
    Ok(BackgroundStatus {
        autostart: app
            .autolaunch()
            .is_enabled()
            .map_err(|_| "autostart_status_failed")?,
        close_to_tray: state.closes_to_tray(),
        window_visible: app
            .get_webview_window("main")
            .and_then(|w| w.is_visible().ok())
            .unwrap_or(false),
    })
}
#[tauri::command]
pub fn configure_desktop_background(
    app: tauri::AppHandle,
    state: State<'_, BackgroundState>,
    autostart: bool,
    close_to_tray: bool,
) -> Result<BackgroundStatus, String> {
    let mut current = state
        .preferences
        .lock()
        .map_err(|_| "background_settings_unavailable")?;
    let manager = app.autolaunch();
    let previous = manager
        .is_enabled()
        .map_err(|_| "autostart_status_failed")?;
    if previous != autostart {
        if autostart {
            manager.enable()
        } else {
            manager.disable()
        }
        .map_err(|_| "autostart_update_failed")?;
    }
    let updated = Preferences { close_to_tray };
    let save = (|| -> Result<(), Box<dyn std::error::Error>> {
        std::fs::create_dir_all(state.path.parent().ok_or("background_path_invalid")?)?;
        let temporary = state.path.with_extension("tmp");
        std::fs::write(&temporary, serde_json::to_vec(&updated)?)?;
        std::fs::rename(temporary, &state.path)?;
        Ok(())
    })();
    if save.is_err() {
        if previous != autostart {
            let rollback = if previous {
                manager.enable()
            } else {
                manager.disable()
            };
            if rollback.is_err() {
                return Err("background_settings_partial_update".into());
            }
        }
        return Err("background_settings_save_failed".into());
    }
    *current = updated;
    drop(current);
    desktop_background_status(app, state)
}
pub fn install_tray(app: &tauri::App) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "打开 dreamtalk", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出并停止后台运行", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &quit])?;
    let mut tray = TrayIconBuilder::with_id("dreamtalk-background")
        .tooltip("dreamtalk · 右键可彻底退出")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => show_main(app),
            "quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if matches!(
                event,
                TrayIconEvent::DoubleClick {
                    button: MouseButton::Left,
                    ..
                }
            ) {
                show_main(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() {
        tray = tray.icon(icon.clone());
    }
    tray.build(app)?;
    Ok(())
}

#[tauri::command]
pub async fn report_desktop_presence(
    app: tauri::AppHandle,
    world_id: Option<String>,
    visible: bool,
) -> Result<bool, String> {
    let supervisor = app.state::<crate::SharedSupervisor>().inner().clone();
    let connection = supervisor
        .lock()
        .await
        .connection()
        .map_err(|_| "core_not_ready")?;
    let window_visible = app
        .get_webview_window("main")
        .is_some_and(|w| w.is_visible().unwrap_or(false) && w.is_focused().unwrap_or(false));
    let sequence = app
        .state::<BackgroundState>()
        .sequence
        .fetch_add(1, Ordering::SeqCst)
        + 1;
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(2))
        .build()
        .map_err(|_| "presence_update_failed")?;
    client
        .post(format!("{}/api/v1/session-visibility", connection.endpoint))
        .bearer_auth(connection.bearer_token())
        .json(&serde_json::json!({
            "world_id": world_id, "visible": visible && window_visible, "sequence": sequence,
        }))
        .send()
        .await
        .map_err(|_| "presence_update_failed")?
        .error_for_status()
        .map_err(|_| "presence_update_failed")?;
    Ok(visible && window_visible)
}

pub fn hide_presence(app: &tauri::AppHandle) {
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        let _ = report_desktop_presence(app, None, false).await;
    });
}
