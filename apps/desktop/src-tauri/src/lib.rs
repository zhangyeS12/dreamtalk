pub mod supervisor;

use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    time::Duration,
};
use supervisor::{event, CoreConnection, CoreSupervisor, LaunchConfig};
use tauri::{Manager, RunEvent, State};
use tokio::sync::Mutex;

type SharedSupervisor = Arc<Mutex<CoreSupervisor>>;

#[tauri::command]
async fn core_connection(
    supervisor: State<'_, SharedSupervisor>,
) -> Result<CoreConnection, String> {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(14);
    loop {
        {
            let supervisor = supervisor.lock().await;
            if let Ok(connection) = supervisor.connection() {
                return Ok(connection);
            }
            if supervisor.state == supervisor::SupervisorState::Failed {
                return Err("core_failed".to_owned());
            }
        }
        if tokio::time::Instant::now() >= deadline {
            return Err("core_discovery_timeout".to_owned());
        }
        tokio::time::sleep(Duration::from_millis(40)).await;
    }
}

#[tauri::command]
async fn report_ui_ready(
    generation: String,
    app: tauri::AppHandle,
    supervisor: State<'_, SharedSupervisor>,
) -> Result<(), String> {
    let connection = supervisor
        .lock()
        .await
        .connection()
        .map_err(str::to_owned)?;
    if generation != connection.generation {
        return Err("ui_generation_mismatch".to_owned());
    }
    event("ui_ready");
    if cfg!(debug_assertions) && std::env::var("LW_DESKTOP_SMOKE").as_deref() == Ok("1") {
        tauri::async_runtime::spawn(async move {
            tokio::time::sleep(Duration::from_millis(250)).await;
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.close();
            }
        });
    }
    Ok(())
}

pub fn run() {
    let supervisor = Arc::new(Mutex::new(CoreSupervisor::new()));
    let stopping = Arc::new(AtomicBool::new(false));
    let app = tauri::Builder::default()
        .manage(supervisor.clone())
        .invoke_handler(tauri::generate_handler![core_connection, report_ui_ready])
        .setup(|app| {
            let config = LaunchConfig {
                project_root: std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("../../..")
                    .canonicalize()?,
                app_data: app.path().app_data_dir()?,
                startup_timeout: Duration::from_secs(12),
            };
            let supervisor = app.state::<SharedSupervisor>().inner().clone();
            tauri::async_runtime::spawn(async move {
                let _ = supervisor.lock().await.start(&config).await;
            });
            if let Some(window) = app.get_webview_window("main") {
                window.show()?;
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("desktop_bootstrap_failed");
    app.run(move |handle, event_kind| {
        if let RunEvent::ExitRequested { api, code, .. } = event_kind {
            if code.is_none() {
                api.prevent_exit();
                if !stopping.swap(true, Ordering::SeqCst) {
                    let supervisor = supervisor.clone();
                    let handle = handle.clone();
                    tauri::async_runtime::spawn(async move {
                        let _ = supervisor.lock().await.stop(Duration::from_secs(8)).await;
                        handle.exit(0);
                    });
                }
            }
        }
    });
}
