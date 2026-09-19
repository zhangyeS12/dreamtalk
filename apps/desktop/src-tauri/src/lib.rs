pub mod credentials;
pub mod host_control;
pub mod llm_config;
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

use credentials::{
    status, CredentialStatus, CredentialStore, CredentialStoreError, NativeCredentialStore,
};

type SharedSupervisor = Arc<Mutex<CoreSupervisor>>;
type SharedCredentialStore = Arc<dyn CredentialStore>;

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

fn credential_error(error: CredentialStoreError) -> String {
    match error {
        CredentialStoreError::InvalidReference => "invalid_secret_ref",
        CredentialStoreError::Missing => "credential_missing",
        CredentialStoreError::Unavailable => "secure_storage_unavailable",
    }
    .to_owned()
}

#[tauri::command]
async fn credential_put(
    secret_ref: String,
    mut secret: String,
    credentials: State<'_, SharedCredentialStore>,
    supervisor: State<'_, SharedSupervisor>,
) -> Result<(), String> {
    credentials
        .put(&secret_ref, &secret)
        .map_err(credential_error)?;
    let result = supervisor
        .lock()
        .await
        .provision_credential(&secret_ref, &secret)
        .await
        .map_err(str::to_owned);
    secret.clear();
    result
}

#[tauri::command]
async fn credential_delete(
    secret_ref: String,
    credentials: State<'_, SharedCredentialStore>,
    supervisor: State<'_, SharedSupervisor>,
) -> Result<(), String> {
    credentials.delete(&secret_ref).map_err(credential_error)?;
    let mut supervisor = supervisor.lock().await;
    if let Err(error) = supervisor.remove_session_credential(&secret_ref).await {
        // The secure copy is gone. Terminate the session process if its private
        // control channel cannot confirm removal, so future calls cannot use the
        // previously provisioned value.
        let _ = supervisor.stop(Duration::from_secs(3)).await;
        return Err(error.to_owned());
    }
    Ok(())
}

#[tauri::command]
async fn credential_status(
    secret_ref: String,
    credentials: State<'_, SharedCredentialStore>,
) -> Result<CredentialStatus, String> {
    credentials::validate_secret_ref(&secret_ref).map_err(credential_error)?;
    Ok(status(credentials.inner().as_ref(), &secret_ref))
}

pub fn run() {
    let credentials: SharedCredentialStore = Arc::new(NativeCredentialStore);
    let supervisor = Arc::new(Mutex::new(CoreSupervisor::with_credential_store(
        credentials.clone(),
    )));
    let stopping = Arc::new(AtomicBool::new(false));
    let app = tauri::Builder::default()
        .manage(supervisor.clone())
        .manage(credentials)
        .invoke_handler(tauri::generate_handler![
            core_connection,
            report_ui_ready,
            credential_put,
            credential_delete,
            credential_status
        ])
        .setup(|app| {
            let config = LaunchConfig {
                project_root: std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("../../..")
                    .canonicalize()?,
                app_data: app.path().app_data_dir()?,
                startup_timeout: Duration::from_secs(12),
                llm_config_path: app.path().app_data_dir()?.join("config").join("llm.json"),
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
