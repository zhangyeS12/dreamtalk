//! User-facing save positions. Update checkpoints retain their independent lifecycle.
use crate::{save_safety, supervisor::LaunchConfig, updater, SharedSupervisor};
use serde_json::{json, Value};
use std::{
    sync::atomic::{AtomicBool, Ordering},
    time::Duration,
};
use tauri::{Emitter, Manager, State};
use tauri_plugin_dialog::DialogExt;
use tokio::sync::Mutex;

#[derive(Default)]
pub struct SaveSlotState {
    scheduled: AtomicBool,
    startup_saved: AtomicBool,
    error: Mutex<Option<String>>,
}

#[tauri::command]
pub fn save_slots_startup_ready(
    app: tauri::AppHandle,
    config: State<'_, LaunchConfig>,
    supervisor: State<'_, SharedSupervisor>,
) {
    start(app, config.inner().clone(), supervisor.inner().clone());
}

async fn snapshot(app: &tauri::AppHandle, config: &LaunchConfig) -> Result<Value, String> {
    let mut value = save_safety::tool(
        config,
        &app.package_info().version.to_string(),
        json!({"action":"slots_status"}),
    )
    .await?;
    value["startup_error"] = json!(app.state::<SaveSlotState>().error.lock().await.clone());
    Ok(value)
}

async fn save_position(
    app: &tauri::AppHandle,
    config: &LaunchConfig,
    supervisor: &SharedSupervisor,
    mut request: Value,
) -> Result<Value, String> {
    if updater::update_unverified(config) {
        return Err("save_update_verification_pending".into());
    }
    let host = supervisor.lock().await;
    let connection = host.connection().map_err(str::to_owned)?;
    let outcome = async {
        save_safety::drain(&connection).await?;
        request["expected_file_identity"] =
            save_safety::evidence(&connection).await?["file_identity"].clone();
        save_safety::tool(config, &app.package_info().version.to_string(), request).await
    }
    .await;
    let _ = updater::maintenance(&connection, "cancel").await;
    outcome
}

async fn startup_save(
    app: &tauri::AppHandle,
    config: &LaunchConfig,
    supervisor: &SharedSupervisor,
) -> Result<(), String> {
    let state = app.state::<SaveSlotState>();
    if state.startup_saved.load(Ordering::SeqCst) {
        return Ok(());
    }
    let status = snapshot(app, config).await?;
    if status["directory"].is_null() {
        return Ok(());
    }
    let name = status["slots"][0]["name"].as_str().unwrap_or("自动存档");
    save_position(
        app,
        config,
        supervisor,
        json!({"action":"slots_save", "slot":0,"name":name,"revision":status["revision"]}),
    )
    .await?;
    state.startup_saved.store(true, Ordering::SeqCst);
    *state.error.lock().await = None;
    Ok(())
}

#[tauri::command]
pub async fn save_slots_status(
    app: tauri::AppHandle,
    config: State<'_, LaunchConfig>,
    updates: State<'_, updater::UpdateState>,
) -> Result<Value, String> {
    let _operation = updates.operation.try_lock().map_err(|_| "save_busy")?;
    snapshot(&app, &config).await
}

#[tauri::command]
pub async fn choose_save_slots_folder(
    app: tauri::AppHandle,
    config: State<'_, LaunchConfig>,
    updates: State<'_, updater::UpdateState>,
    supervisor: State<'_, SharedSupervisor>,
) -> Result<Option<Value>, String> {
    let _operation = updates.operation.try_lock().map_err(|_| "save_busy")?;
    let handle = app.clone();
    let chosen = tauri::async_runtime::spawn_blocking(move || {
        handle
            .dialog()
            .file()
            .set_title("选择专用存档文件夹")
            .blocking_pick_folder()
    })
    .await
    .map_err(|_| "save_dialog_failed")?;
    let Some(chosen) = chosen else {
        return Ok(None);
    };
    let directory = chosen.into_path().map_err(|_| "save_path_invalid")?;
    save_safety::tool(&config, &app.package_info().version.to_string(), json!({"action":"slots_configure","directory":directory,"program_root":config.project_root})).await?;
    let ready = supervisor.lock().await.connection().is_ok();
    if ready {
        if let Err(error) = startup_save(&app, &config, &supervisor).await {
            *app.state::<SaveSlotState>().error.lock().await = Some(error);
        }
    }
    snapshot(&app, &config).await.map(Some)
}

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SlotOperation {
    action: String,
    slot: u8,
    revision: u64,
    name: Option<String>,
    source: Option<String>,
    confirmed: bool,
}

#[tauri::command]
pub async fn operate_save_slot(
    request: SlotOperation,
    app: tauri::AppHandle,
    config: State<'_, LaunchConfig>,
    updates: State<'_, updater::UpdateState>,
    supervisor: State<'_, SharedSupervisor>,
) -> Result<Value, String> {
    let _operation = updates.operation.try_lock().map_err(|_| "save_busy")?;
    if request.slot > 4
        || ![
            "save",
            "import",
            "copy_auto",
            "rename",
            "export",
            "load",
            "retry_auto",
        ]
        .contains(&request.action.as_str())
    {
        return Err("save_slot_invalid".into());
    }
    if request.action == "retry_auto" {
        startup_save(&app, &config, &supervisor).await?;
        return snapshot(&app, &config).await;
    }
    let status = snapshot(&app, &config).await?;
    if status["revision"].as_u64() != Some(request.revision) {
        return Err("save_slot_changed".into());
    }
    if request.slot == 0 && ["save", "import", "copy_auto"].contains(&request.action.as_str()) {
        return Err("save_slot_invalid".into());
    }
    if (request.action == "load"
        || (!status["slots"][request.slot as usize].is_null()
            && ["save", "import", "copy_auto"].contains(&request.action.as_str())))
        && !request.confirmed
    {
        return Err("save_confirmation_required".into());
    }
    let mut operation = json!({"action":format!("slots_{}",request.action), "slot":request.slot, "revision":request.revision,"name":request.name});
    if request.action == "import" {
        let source = if let Some(source) = request.source.filter(|value| !value.trim().is_empty()) {
            std::path::PathBuf::from(source)
        } else {
            let handle = app.clone();
            let chosen = tauri::async_runtime::spawn_blocking(move || {
                handle
                    .dialog()
                    .file()
                    .set_title("选择存档文件（不会立即加载）")
                    .add_filter("dreamtalk 存档", &["dreamsave"])
                    .blocking_pick_file()
            })
            .await
            .map_err(|_| "save_dialog_failed")?;
            let Some(chosen) = chosen else {
                let mut value = snapshot(&app, &config).await?;
                value["cancelled"] = json!(true);
                return Ok(value);
            };
            chosen.into_path().map_err(|_| "save_path_invalid")?
        };
        operation["source"] = json!(source);
    }
    if request.action == "export" {
        let handle = app.clone();
        let chosen = tauri::async_runtime::spawn_blocking(move || {
            handle
                .dialog()
                .file()
                .set_title("导出存档")
                .set_file_name("dreamtalk-save.dreamsave")
                .add_filter("dreamtalk 存档", &["dreamsave"])
                .blocking_save_file()
        })
        .await
        .map_err(|_| "save_dialog_failed")?;
        let Some(chosen) = chosen else {
            let mut value = snapshot(&app, &config).await?;
            value["cancelled"] = json!(true);
            return Ok(value);
        };
        operation["output"] = json!(chosen.into_path().map_err(|_| "save_path_invalid")?);
    }
    if request.action == "load" {
        if updater::update_unverified(&config) {
            return Err("save_update_verification_pending".into());
        }
        let mut host = supervisor.lock().await;
        if let Ok(connection) = host.connection() {
            if let Err(error) = save_safety::drain(&connection).await {
                let _ = updater::maintenance(&connection, "cancel").await;
                return Err(error);
            }
            if let Err(error) = host.stop_for_update(Duration::from_secs(30)).await {
                let _ = updater::maintenance(&connection, "cancel").await;
                return Err(error.into());
            }
        } else {
            if !host.safely_stopped() {
                return Err("save_core_shutdown_unconfirmed".into());
            }
            host.stop(Duration::ZERO).await.map_err(str::to_owned)?;
        }
        let result =
            save_safety::tool(&config, &app.package_info().version.to_string(), operation).await;
        if result
            .as_ref()
            .is_err_and(|code| code == "save_tool_shutdown_unconfirmed")
        {
            return result;
        }
        // Bootstrap resolves any interrupted slot journal before opening the database.
        let restarted = host.start(&config).await.map_err(str::to_owned);
        if result.is_ok() {
            app.state::<SaveSlotState>()
                .startup_saved
                .store(true, Ordering::SeqCst);
            *app.state::<SaveSlotState>().error.lock().await = None;
        }
        restarted?;
        return result;
    }
    if request.action == "save" {
        save_position(&app, &config, &supervisor, operation).await?;
    } else {
        save_safety::tool(&config, &app.package_info().version.to_string(), operation).await?;
    }
    snapshot(&app, &config).await
}

pub fn start(app: tauri::AppHandle, config: LaunchConfig, supervisor: SharedSupervisor) {
    if app
        .state::<SaveSlotState>()
        .scheduled
        .swap(true, Ordering::SeqCst)
    {
        return;
    }
    tauri::async_runtime::spawn(async move {
        loop {
            let ready = supervisor.lock().await.connection().is_ok();
            if !ready || updater::update_unverified(&config) {
                *app.state::<SaveSlotState>().error.lock().await =
                    Some("save_core_unavailable".into());
                return;
            }
            {
                let updates = app.state::<updater::UpdateState>();
                if let Ok(_operation) = updates.operation.try_lock() {
                    if let Err(error) = startup_save(&app, &config, &supervisor).await {
                        *app.state::<SaveSlotState>().error.lock().await = Some(error.clone());
                        let _ = app.emit("save-backup-warning", error);
                    }
                    return;
                };
            }
            tokio::time::sleep(Duration::from_millis(250)).await;
        }
    });
}
