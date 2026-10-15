//! Whole-save operations use the Core's offline SQLite tool, never a model.
use crate::{supervisor::LaunchConfig, updater, SharedSupervisor};
use serde_json::{json, Value};
use std::time::Duration;
use tauri::{Manager, State};
use tauri_plugin_dialog::DialogExt;
use tokio::{io::AsyncWriteExt, process::Command};
use uuid::Uuid;

pub(crate) async fn tool(
    config: &LaunchConfig,
    version: &str,
    mut request: Value,
) -> Result<Value, String> {
    request["app_data"] = json!(config.app_data);
    request["version"] = json!(version);
    let directory = config.app_data.join("runtime");
    tokio::fs::create_dir_all(&directory)
        .await
        .map_err(|_| "save_tool_unavailable")?;
    let path = directory.join(format!("storage-{}.json", Uuid::new_v4()));
    let mut file = tokio::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&path)
        .await
        .map_err(|_| "save_tool_unavailable")?;
    file.write_all(&serde_json::to_vec(&request).map_err(|_| "save_request_invalid")?)
        .await
        .map_err(|_| "save_tool_unavailable")?;
    file.sync_all().await.map_err(|_| "save_tool_unavailable")?;
    drop(file);
    let packaged = config.project_root.join("core/dreamtalk-core.exe");
    let mut command = if packaged.is_file() {
        Command::new(packaged)
    } else if cfg!(debug_assertions) {
        let mut command = Command::new(config.project_root.join(".venv/Scripts/python.exe"));
        command.args(["-m", "livingworld.bootstrap"]);
        command.env("PYTHONPATH", config.project_root.join("services/core/src"));
        command
    } else {
        return Err("save_tool_unavailable".into());
    };
    command
        .arg("--storage-request")
        .arg(&path)
        .current_dir(&config.project_root)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .kill_on_drop(true);
    #[cfg(windows)]
    command.creation_flags(0x08000000);
    let output = tokio::time::timeout(Duration::from_secs(240), command.output()).await;
    let _ = tokio::fs::remove_file(&path).await;
    let output = output
        .map_err(|_| "save_operation_timeout")?
        .map_err(|_| "save_tool_unavailable")?;
    if output.stdout.len() > 2 * 1024 * 1024 {
        return Err("save_record_invalid".into());
    }
    let reply: Value =
        serde_json::from_slice(&output.stdout).map_err(|_| "save_tool_unavailable")?;
    if !output.status.success() || reply["ok"] != true {
        return Err(reply["error"]
            .as_str()
            .filter(|code| code.starts_with("save_"))
            .unwrap_or("save_operation_failed")
            .to_owned());
    }
    Ok(reply["result"].clone())
}

pub(crate) async fn evidence(
    connection: &crate::supervisor::CoreConnection,
) -> Result<Value, String> {
    reqwest::Client::builder()
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(15))
        .build()
        .map_err(|_| "save_core_unavailable")?
        .get(format!("{}/system/storage", connection.endpoint))
        .bearer_auth(connection.bearer_token())
        .send()
        .await
        .map_err(|_| "save_core_unavailable")?
        .error_for_status()
        .map_err(|_| "save_core_unavailable")?
        .json()
        .await
        .map_err(|_| "save_core_unavailable".into())
}

pub(crate) async fn drain(connection: &crate::supervisor::CoreConnection) -> Result<(), String> {
    updater::maintenance(connection, "prepare").await?;
    let deadline = tokio::time::Instant::now() + Duration::from_secs(30);
    loop {
        let status = updater::maintenance(connection, "status").await?;
        if !status.preparing {
            return Err("save_barrier_expired".into());
        }
        if status.active == 0 {
            return Ok(());
        }
        if tokio::time::Instant::now() >= deadline {
            return Err("save_tasks_running".into());
        }
        tokio::time::sleep(Duration::from_millis(250)).await;
    }
}

pub(crate) async fn backup(
    app: &tauri::AppHandle,
    config: &LaunchConfig,
    supervisor: &SharedSupervisor,
    reason: &str,
    automatic: bool,
) -> Result<Value, String> {
    if updater::update_unverified(config) {
        return Err("save_update_verification_pending".into());
    }
    let host = supervisor.lock().await;
    let connection = host.connection().map_err(str::to_owned)?;
    let outcome = async {
        drain(&connection).await?;
        let live = evidence(&connection).await?;
        tool(config, &app.package_info().version.to_string(), json!({"action":"backup", "reason":reason, "automatic":automatic, "expected_file_identity":live["file_identity"]})).await
    }.await;
    let _ = updater::maintenance(&connection, "cancel").await;
    outcome
}

#[tauri::command]
pub async fn save_safety_status(
    app: tauri::AppHandle,
    config: State<'_, LaunchConfig>,
    updates: State<'_, updater::UpdateState>,
) -> Result<Value, String> {
    let _operation = updates.operation.try_lock().map_err(|_| "save_busy")?;
    let outcome = tool(
        &config,
        &app.package_info().version.to_string(),
        json!({"action":"status"}),
    )
    .await;
    let can_rollback = updater::rollback_available(&config);
    match outcome {
        Ok(mut value) => {
            value["can_rollback"] = json!(can_rollback);
            value["credential_cleanup_incomplete"] = json!(config
                .app_data
                .join("config/credential-cleanup.json")
                .exists());
            value["update_verifying"] =
                json!(updater::update_unverified(&config) && value["recovery_required"] != true);
            Ok(value)
        }
        Err(_) if can_rollback => Ok(
            json!({"recovery_required":true,"problem":"save_update_tool_unavailable","current":null,"snapshots":[],"backup_directory":"","automatic_minutes":30,"can_rollback":true}),
        ),
        Err(error) => Err(error),
    }
}

#[tauri::command]
pub async fn create_save_backup(
    app: tauri::AppHandle,
    config: State<'_, LaunchConfig>,
    updates: State<'_, updater::UpdateState>,
    supervisor: State<'_, SharedSupervisor>,
) -> Result<Value, String> {
    let _operation = updates.operation.try_lock().map_err(|_| "save_busy")?;
    backup(&app, &config, &supervisor, "manual", false).await
}

#[tauri::command]
pub async fn restore_save_backup(
    snapshot_id: String,
    confirmed: bool,
    app: tauri::AppHandle,
    config: State<'_, LaunchConfig>,
    updates: State<'_, updater::UpdateState>,
    supervisor: State<'_, SharedSupervisor>,
) -> Result<Value, String> {
    if !confirmed || Uuid::parse_str(&snapshot_id).is_err() {
        return Err("save_confirmation_required".into());
    }
    let _operation = updates.operation.try_lock().map_err(|_| "save_busy")?;
    let mut host = supervisor.lock().await;
    if let Ok(connection) = host.connection() {
        if let Err(error) = drain(&connection).await {
            let _ = updater::maintenance(&connection, "cancel").await;
            return Err(error);
        }
        host.stop_for_update(Duration::from_secs(30))
            .await
            .map_err(str::to_owned)?;
    }
    // On success keep Core stopped until the user explicitly reviews/resumes.
    let result = tool(
        &config,
        &app.package_info().version.to_string(),
        json!({"action":"restore", "snapshot_id":snapshot_id}),
    )
    .await;
    if result.is_err() {
        let _ = host.start(&config).await;
    } else {
        updater::use_restored_checkpoint(
            &config,
            &snapshot_id,
            &app.package_info().version.to_string(),
        )?;
    }
    result
}

#[tauri::command]
pub async fn resume_restored_save(
    app: tauri::AppHandle,
    config: State<'_, LaunchConfig>,
    updates: State<'_, updater::UpdateState>,
    supervisor: State<'_, SharedSupervisor>,
) -> Result<(), String> {
    let _operation = updates.operation.try_lock().map_err(|_| "save_busy")?;
    let review_path = config.app_data.join("restore-hold.json");
    let review = tokio::fs::read(&review_path).await.ok();
    tool(
        &config,
        &app.package_info().version.to_string(),
        json!({"action":"resume"}),
    )
    .await?;
    if let Err(error) = supervisor.lock().await.start(&config).await {
        if let Some(review) = review {
            let _ = crate::llm_config::write_atomic(&review_path, &review).await;
        }
        return Err(error.to_owned());
    }
    let verified = updater::verify_pending_start(&app, &config, &supervisor).await;
    if verified.is_err() {
        let _ = supervisor
            .lock()
            .await
            .stop_for_update(Duration::from_secs(30))
            .await;
        let _ = tokio::fs::write(
            config.app_data.join("update-failure.json"),
            b"{\"code\":\"save_update_verification_failed\"}",
        )
        .await;
    }
    verified
}

#[tauri::command]
pub async fn configure_save_backup_location(
    app: tauri::AppHandle,
    config: State<'_, LaunchConfig>,
    updates: State<'_, updater::UpdateState>,
) -> Result<Option<Value>, String> {
    let _operation = updates.operation.try_lock().map_err(|_| "save_busy")?;
    let handle = app.clone();
    let chosen = tauri::async_runtime::spawn_blocking(move || {
        handle
            .dialog()
            .file()
            .set_title("选择存档备份位置")
            .blocking_pick_folder()
    })
    .await
    .map_err(|_| "save_dialog_failed")?;
    let Some(chosen) = chosen else {
        return Ok(None);
    };
    let path = chosen.into_path().map_err(|_| "save_path_invalid")?;
    tool(
        &config,
        &app.package_info().version.to_string(),
        json!({"action":"configure", "directory":path, "program_root":config.project_root}),
    )
    .await
    .map(Some)
}

#[tauri::command]
pub async fn export_save_backup(
    snapshot_id: String,
    app: tauri::AppHandle,
    config: State<'_, LaunchConfig>,
    updates: State<'_, updater::UpdateState>,
) -> Result<Option<Value>, String> {
    if Uuid::parse_str(&snapshot_id).is_err() {
        return Err("save_snapshot_invalid".into());
    }
    let _operation = updates.operation.try_lock().map_err(|_| "save_busy")?;
    let handle = app.clone();
    let chosen = tauri::async_runtime::spawn_blocking(move || {
        handle
            .dialog()
            .file()
            .set_title("导出完整存档备份")
            .add_filter("dreamtalk 存档", &["dreamsave"])
            .set_file_name("dreamtalk-backup.dreamsave")
            .blocking_save_file()
    })
    .await
    .map_err(|_| "save_dialog_failed")?;
    let Some(chosen) = chosen else {
        return Ok(None);
    };
    let path = chosen.into_path().map_err(|_| "save_path_invalid")?;
    tool(
        &config,
        &app.package_info().version.to_string(),
        json!({"action":"export", "snapshot_id":snapshot_id, "output":path}),
    )
    .await
    .map(Some)
}

#[tauri::command]
pub async fn import_save_backup(
    app: tauri::AppHandle,
    config: State<'_, LaunchConfig>,
    updates: State<'_, updater::UpdateState>,
) -> Result<Option<Value>, String> {
    let _operation = updates.operation.try_lock().map_err(|_| "save_busy")?;
    let handle = app.clone();
    let chosen = tauri::async_runtime::spawn_blocking(move || {
        handle
            .dialog()
            .file()
            .set_title("读取完整存档备份")
            .add_filter("dreamtalk 存档", &["dreamsave"])
            .blocking_pick_file()
    })
    .await
    .map_err(|_| "save_dialog_failed")?;
    let Some(chosen) = chosen else {
        return Ok(None);
    };
    let path = chosen.into_path().map_err(|_| "save_path_invalid")?;
    tool(
        &config,
        &app.package_info().version.to_string(),
        json!({"action":"import", "source":path}),
    )
    .await
    .map(Some)
}

#[tauri::command]
pub async fn clear_saved_data(
    confirmation: String,
    include_backups: bool,
    app: tauri::AppHandle,
    config: State<'_, LaunchConfig>,
    updates: State<'_, updater::UpdateState>,
    supervisor: State<'_, SharedSupervisor>,
    credentials: State<'_, crate::SharedCredentialStore>,
) -> Result<Value, String> {
    if confirmation != "删除全部数据" {
        return Err("save_confirmation_required".into());
    }
    let _operation = updates.operation.try_lock().map_err(|_| "save_busy")?;
    let mut host = supervisor.lock().await;
    // Enumerate only registered references for this app; never resolve or expose keys.
    let mut references = crate::llm_config::load(&config.llm_config_path)
        .await
        .map_err(|_| "save_credential_registry_unavailable")?
        .credential_refs;
    references.extend(
        crate::speech_credentials::REGISTRY
            .references(&config)
            .await
            .map_err(|_| "save_credential_registry_unavailable")?,
    );
    references.extend(
        crate::media_credentials::REGISTRY
            .references(&config)
            .await
            .map_err(|_| "save_credential_registry_unavailable")?,
    );
    let pending_path = config.app_data.join("config/credential-cleanup.json");
    match tokio::fs::read(&pending_path).await {
        Ok(bytes) => {
            let pending: Vec<String> = serde_json::from_slice(&bytes)
                .map_err(|_| "save_credential_registry_unavailable")?;
            if pending.len() > 131072
                || pending
                    .iter()
                    .any(|reference| crate::credentials::validate_secret_ref(reference).is_err())
            {
                return Err("save_credential_registry_unavailable".into());
            }
            references.extend(pending);
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(_) => return Err("save_credential_registry_unavailable".into()),
    }
    references.sort();
    references.dedup();
    let connection = host.connection().map_err(str::to_owned)?;
    if let Err(error) = drain(&connection).await {
        let _ = updater::maintenance(&connection, "cancel").await;
        return Err(error);
    }
    if crate::llm_config::write_atomic(
        &pending_path,
        &serde_json::to_vec(&references).map_err(|_| "save_cleanup_record_failed")?,
    )
    .await
    .is_err()
    {
        let _ = updater::maintenance(&connection, "cancel").await;
        return Err("save_cleanup_record_failed".into());
    }
    host.stop_for_update(Duration::from_secs(30))
        .await
        .map_err(str::to_owned)?;
    let mut result = tool(
        &config,
        &app.package_info().version.to_string(),
        json!({"action":"clear", "confirmation":confirmation, "include_backups":include_backups}),
    )
    .await;
    result = match result {
        Ok(mut value) => {
            async {
                let mut failed = Vec::new();
                for reference in references {
                    if credentials.delete(&reference).is_err() {
                        failed.push(reference);
                    }
                }
                if !failed.is_empty() {
                    crate::llm_config::write_atomic(
                        &pending_path,
                        &serde_json::to_vec(&failed).map_err(|_| "save_cleanup_record_failed")?,
                    )
                    .await
                    .map_err(|_| "save_cleanup_record_failed")?;
                } else {
                    tokio::fs::remove_file(&pending_path)
                        .await
                        .map_err(|_| "save_cleanup_record_failed")?;
                }
                value["credential_cleanup_incomplete"] = json!(!failed.is_empty());
                Ok(value)
            }
            .await
        }
        Err(error) => Err(error),
    };
    let _ = host.start(&config).await;
    result
}

pub fn start_automatic(app: tauri::AppHandle, config: LaunchConfig, supervisor: SharedSupervisor) {
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(Duration::from_secs(30)).await;
        let mut interval = tokio::time::interval(Duration::from_secs(30 * 60));
        loop {
            interval.tick().await;
            let updates = app.state::<updater::UpdateState>();
            let Ok(_operation) = updates.operation.try_lock() else {
                continue;
            };
            let outcome = backup(&app, &config, &supervisor, "automatic", true).await;
            if let Err(error) = outcome {
                use tauri::Emitter;
                let _ = app.emit("save-backup-warning", error);
            }
        }
    });
}
