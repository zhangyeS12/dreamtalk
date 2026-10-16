pub mod background;
pub mod credentials;
pub mod file_exports;
pub mod host_control;
pub mod llm_config;
pub mod local_images;
pub mod local_speech;
pub mod media_credentials;
pub mod save_safety;
pub mod scoped_credentials;
pub mod speech_credentials;
pub mod supervisor;
pub mod updater;

use serde::Serialize;
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
use uuid::Uuid;

use credentials::{
    status, CredentialStatus, CredentialStore, CredentialStoreError, NativeCredentialStore,
};

type SharedSupervisor = Arc<Mutex<CoreSupervisor>>;
type SharedCredentialStore = Arc<dyn CredentialStore>;

async fn put_scoped_credential(
    domain: scoped_credentials::CredentialDomain,
    world: &str,
    reference: &str,
    secret: &str,
    config: &LaunchConfig,
    credentials: &SharedCredentialStore,
    supervisor: &SharedSupervisor,
) -> Result<(), String> {
    let mut supervisor = supervisor.lock().await;
    let exists = credentials.exists(reference).map_err(credential_error)?;
    domain
        .authorize_reference(config, world, reference, exists)
        .await
        .map_err(str::to_owned)?;
    credentials
        .put(reference, secret)
        .map_err(credential_error)?;
    if let Err(error) = domain.register(config, world, reference).await {
        if !exists {
            let _ = credentials.delete(reference);
        }
        return Err(error.to_owned());
    }
    match domain {
        scoped_credentials::CredentialDomain::Media => {
            supervisor
                .provision_media_credential(world, reference, secret)
                .await
        }
        scoped_credentials::CredentialDomain::Speech => {
            supervisor.provision_credential(reference, secret).await
        }
    }
    .map_err(str::to_owned)
}

async fn forget_scoped_credentials(
    domain: scoped_credentials::CredentialDomain,
    world: &str,
    reference: Option<&str>,
    keep: Option<&str>,
    config: &LaunchConfig,
    credentials: &SharedCredentialStore,
    supervisor: &SharedSupervisor,
) -> Result<(), String> {
    let mut supervisor = supervisor.lock().await;
    if let Some(keep) = keep {
        domain
            .authorize_reference(
                config,
                world,
                keep,
                credentials.exists(keep).map_err(credential_error)?,
            )
            .await
            .map_err(str::to_owned)?;
    }
    let references = domain
        .world_references(config, world, reference)
        .await
        .map_err(str::to_owned)?;
    for reference in references {
        if keep == Some(reference.as_str()) {
            continue;
        }
        credentials.delete(&reference).map_err(credential_error)?;
        if let Err(error) = supervisor.remove_session_credential(&reference).await {
            let _ = supervisor.stop(Duration::from_secs(3)).await;
            return Err(error.to_owned());
        }
        domain
            .forget(config, world, Some(&reference))
            .await
            .map_err(str::to_owned)?;
    }
    Ok(())
}

#[tauri::command]
async fn speech_credential_put(
    world_id: String,
    secret_ref: String,
    mut secret: String,
    config: State<'_, LaunchConfig>,
    credentials: State<'_, SharedCredentialStore>,
    supervisor: State<'_, SharedSupervisor>,
    updates: State<'_, updater::UpdateState>,
) -> Result<(), String> {
    let _guard = updates
        .operation
        .try_lock()
        .map_err(|_| "update_busy".to_owned())?;
    let result = put_scoped_credential(
        speech_credentials::REGISTRY,
        &world_id,
        &secret_ref,
        &secret,
        &config,
        &credentials,
        &supervisor,
    )
    .await;
    secret.clear();
    result
}

#[tauri::command]
async fn forget_speech_credentials(
    world_id: String,
    secret_ref: Option<String>,
    config: State<'_, LaunchConfig>,
    credentials: State<'_, SharedCredentialStore>,
    supervisor: State<'_, SharedSupervisor>,
    updates: State<'_, updater::UpdateState>,
) -> Result<(), String> {
    let _guard = updates
        .operation
        .try_lock()
        .map_err(|_| "update_busy".to_owned())?;
    forget_scoped_credentials(
        speech_credentials::REGISTRY,
        &world_id,
        secret_ref.as_deref(),
        None,
        &config,
        &credentials,
        &supervisor,
    )
    .await
}

#[tauri::command]
async fn media_credential_put(
    world_id: String,
    secret_ref: String,
    mut secret: String,
    config: State<'_, LaunchConfig>,
    credentials: State<'_, SharedCredentialStore>,
    supervisor: State<'_, SharedSupervisor>,
    updates: State<'_, updater::UpdateState>,
) -> Result<(), String> {
    let _guard = updates
        .operation
        .try_lock()
        .map_err(|_| "update_busy".to_owned())?;
    let result = put_scoped_credential(
        media_credentials::REGISTRY,
        &world_id,
        &secret_ref,
        &secret,
        &config,
        &credentials,
        &supervisor,
    )
    .await;
    secret.clear();
    result
}

#[tauri::command]
async fn forget_media_credentials(
    world_id: String,
    secret_ref: Option<String>,
    keep_secret_ref: Option<String>,
    config: State<'_, LaunchConfig>,
    credentials: State<'_, SharedCredentialStore>,
    supervisor: State<'_, SharedSupervisor>,
    updates: State<'_, updater::UpdateState>,
) -> Result<(), String> {
    let _guard = updates
        .operation
        .try_lock()
        .map_err(|_| "update_busy".to_owned())?;
    forget_scoped_credentials(
        media_credentials::REGISTRY,
        &world_id,
        secret_ref.as_deref(),
        keep_secret_ref.as_deref(),
        &config,
        &credentials,
        &supervisor,
    )
    .await
}

#[tauri::command]
async fn core_connection(
    supervisor: State<'_, SharedSupervisor>,
    config: State<'_, LaunchConfig>,
) -> Result<CoreConnection, String> {
    let deadline = tokio::time::Instant::now() + config.startup_timeout + Duration::from_secs(5);
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
async fn retry_core_start(
    app: tauri::AppHandle,
    config: State<'_, LaunchConfig>,
    supervisor: State<'_, SharedSupervisor>,
    updates: State<'_, updater::UpdateState>,
) -> Result<CoreConnection, String> {
    let _operation = updates.operation.try_lock().map_err(|_| "update_busy")?;
    let mut host = supervisor.lock().await;
    let (connection, restarted) = recover_core_start(&config, &mut host).await?;
    if !restarted {
        return Ok(connection);
    }
    drop(host);
    updater::verify_pending_start(&app, &config, &supervisor).await?;
    let (startup_app, startup_config, startup_supervisor) = (
        app.clone(),
        config.inner().clone(),
        supervisor.inner().clone(),
    );
    tauri::async_runtime::spawn(async move {
        tokio::join!(
            local_speech::on_start(
                startup_app.clone(),
                startup_config.clone(),
                startup_supervisor.clone()
            ),
            local_images::on_start(startup_app, startup_config, startup_supervisor),
        );
    });
    Ok(connection)
}

async fn recover_core_start(
    config: &LaunchConfig,
    host: &mut CoreSupervisor,
) -> Result<(CoreConnection, bool), String> {
    // A late successful start is reused; never stop a live model task to retry UI discovery.
    if let Ok(connection) = host.connection() {
        return Ok((connection, false));
    }
    if host.state != supervisor::SupervisorState::Failed || !host.safely_stopped() {
        return Err("core_start_in_progress".into());
    }
    if updater::update_unverified(config) {
        return Err("save_update_retry_unavailable".into());
    }
    host.start(config).await.map_err(str::to_owned)?;
    let connection = host.connection().map_err(str::to_owned)?;
    Ok((connection, true))
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

async fn rollback_chat_model_setup(
    supervisor: &mut CoreSupervisor,
    config: &LaunchConfig,
    credentials: &dyn CredentialStore,
    reference: &str,
    previous: &[u8],
) -> Result<(), String> {
    if llm_config::write_atomic(&config.llm_config_path, previous)
        .await
        .is_err()
    {
        let _ = supervisor.stop(Duration::from_secs(3)).await;
        return Err("model_setup_recovery_failed".to_owned());
    }
    // Restore the previous runtime even if deleting the now-orphaned credential fails.
    let restarted = supervisor.restart(config).await.is_ok();
    let deleted = credentials.delete(reference).is_ok();
    if restarted && deleted {
        Ok(())
    } else {
        Err("model_setup_recovery_failed".to_owned())
    }
}

#[tauri::command]
#[expect(
    clippy::too_many_arguments,
    reason = "Tauri injects four independent managed states; preserve the IPC contract"
)]
async fn configure_chat_model(
    setup: llm_config::ChatModelSetup,
    mut secret: String,
    streaming: Option<bool>,
    world_id: Option<String>,
    config: State<'_, LaunchConfig>,
    credentials: State<'_, SharedCredentialStore>,
    supervisor: State<'_, SharedSupervisor>,
    updates: State<'_, updater::UpdateState>,
) -> Result<(), String> {
    let _update_guard = updates
        .operation
        .try_lock()
        .map_err(|_| "update_busy".to_owned())?;
    llm_config::validate_world_scope(world_id.as_deref()).map_err(str::to_owned)?;
    if secret.is_empty() || secret.len() > 4096 {
        return Err("model_setup_invalid".to_owned());
    }
    let reference = Uuid::new_v4().to_string();
    let document =
        llm_config::single_chat_document_streaming(&setup, &reference, streaming.unwrap_or(false))
            .map_err(str::to_owned)?;
    let mut supervisor = supervisor.lock().await;
    let health = supervisor
        .authenticated_health_for_world(world_id.as_deref())
        .await
        .map_err(str::to_owned)?;
    let previous = tokio::fs::read(&config.llm_config_path)
        .await
        .map_err(|_| "llm_config_read_failed".to_owned())?;
    let (selected, inherited) =
        llm_config::scope_document(&previous, world_id.as_deref()).map_err(str::to_owned)?;
    if !(world_id.is_some() && inherited)
        && (health.llm_status != "unconfigured" || !llm_config::is_empty_configuration(&selected))
    {
        return Err("model_setup_requires_empty_configuration".to_owned());
    }
    let document = llm_config::replace_scope(&previous, &document, world_id.as_deref())
        .map_err(str::to_owned)?;
    credentials
        .put(&reference, &secret)
        .map_err(credential_error)?;
    secret.clear();
    if llm_config::write_atomic(&config.llm_config_path, &document)
        .await
        .is_err()
    {
        credentials.delete(&reference).map_err(credential_error)?;
        return Err("llm_config_write_failed".to_owned());
    }
    let started = supervisor.restart(&config).await.is_ok();
    let ready = started
        && supervisor
            .authenticated_health_for_world(world_id.as_deref())
            .await
            .is_ok_and(|health| health.llm_status == "ready");
    if !ready {
        rollback_chat_model_setup(
            &mut supervisor,
            &config,
            credentials.inner().as_ref(),
            &reference,
            &previous,
        )
        .await
        .map_err(|_| "model_setup_recovery_failed".to_owned())?;
        return Err("model_setup_failed".to_owned());
    }
    Ok(())
}

#[tauri::command]
async fn managed_chat_model_setup(
    world_id: Option<String>,
    config: State<'_, LaunchConfig>,
) -> Result<Option<serde_json::Value>, String> {
    let bytes = tokio::fs::read(&config.llm_config_path)
        .await
        .map_err(|_| "llm_config_read_failed".to_owned())?;
    let (selected, inherited) =
        llm_config::scope_document(&bytes, world_id.as_deref()).map_err(str::to_owned)?;
    if llm_config::is_empty_configuration(&selected) {
        return Ok(None);
    }
    let managed = llm_config::managed_chat_configuration(&selected).map_err(|error| {
        if inherited {
            "model_world_inherits_advanced_default".to_owned()
        } else if world_id.is_some() {
            "model_world_has_advanced_configuration".to_owned()
        } else {
            error.to_owned()
        }
    })?;
    let mut setup =
        serde_json::to_value(managed.setup).map_err(|_| "model_setup_invalid".to_owned())?;
    setup["streaming"] = serde_json::json!(managed.streaming);
    setup["inherited"] = serde_json::json!(inherited);
    Ok(Some(setup))
}

#[derive(Serialize)]
struct ModelUpdateOutcome {
    old_credential_cleanup_incomplete: bool,
}

#[tauri::command]
#[expect(
    clippy::too_many_arguments,
    reason = "Tauri injects four independent managed states; preserve the IPC contract"
)]
async fn repair_chat_model(
    setup: llm_config::ChatModelSetup,
    secret: String,
    streaming: bool,
    world_id: Option<String>,
    config: State<'_, LaunchConfig>,
    credentials: State<'_, SharedCredentialStore>,
    supervisor: State<'_, SharedSupervisor>,
    updates: State<'_, updater::UpdateState>,
) -> Result<(), String> {
    let _operation = updates.operation.try_lock().map_err(|_| "update_busy")?;
    let mut host = supervisor.lock().await;
    repair_chat_model_with(
        setup,
        secret,
        streaming,
        world_id.as_deref(),
        &config,
        credentials.inner().as_ref(),
        &mut host,
    )
    .await
}

async fn repair_chat_model_with(
    setup: llm_config::ChatModelSetup,
    mut secret: String,
    streaming: bool,
    world: Option<&str>,
    config: &LaunchConfig,
    credentials: &dyn CredentialStore,
    host: &mut CoreSupervisor,
) -> Result<(), String> {
    llm_config::validate_world_scope(world).map_err(str::to_owned)?;
    if secret.trim().is_empty() || secret.len() > 4096 {
        return Err("model_update_new_secret_required".into());
    }
    let health = host
        .authenticated_health_for_world(world)
        .await
        .map_err(str::to_owned)?;
    if health.llm_status != "degraded" {
        return Err("model_setup_state_changed".into());
    }
    let previous = tokio::fs::read(&config.llm_config_path)
        .await
        .map_err(|_| "llm_config_read_failed")?;
    if previous.len() > 1_048_576 {
        return Err("model_configuration_too_large".into());
    }
    let reference = Uuid::new_v4().to_string();
    let document = llm_config::single_chat_document_streaming(&setup, &reference, streaming)
        .map_err(str::to_owned)?;
    let document = llm_config::repair_scope(&previous, &document, world).map_err(str::to_owned)?;
    let connection = host.connection().map_err(str::to_owned)?;
    if let Err(error) = save_safety::drain(&connection).await {
        let _ = updater::maintenance(&connection, "cancel").await;
        return Err(error);
    }
    let prepare = async {
        // Preserve exact bytes and every existing credential before replacing this scope.
        let archive = config
            .app_data
            .join("config/model-recovery")
            .join(format!("{}.json", Uuid::new_v4()));
        tokio::fs::create_dir_all(archive.parent().ok_or("llm_config_path_invalid")?)
            .await
            .map_err(|_| "llm_config_write_failed")?;
        llm_config::write_atomic(&archive, &previous)
            .await
            .map_err(str::to_owned)?;
        credentials
            .put(&reference, &secret)
            .map_err(credential_error)?;
        secret.clear();
        if llm_config::write_atomic(&config.llm_config_path, &document)
            .await
            .is_err()
        {
            let _ = credentials.delete(&reference);
            return Err("llm_config_write_failed".to_owned());
        }
        Ok::<(), String>(())
    }
    .await;
    if let Err(error) = prepare {
        let _ = updater::maintenance(&connection, "cancel").await;
        return Err(error);
    }
    let stopped = host.stop_for_update(Duration::from_secs(30)).await;
    let started = stopped.is_ok() && host.start(config).await.is_ok();
    if !started
        || !host
            .authenticated_health_for_world(world)
            .await
            .is_ok_and(|health| health.llm_status == "ready")
    {
        rollback_chat_model_setup(host, config, credentials, &reference, &previous).await?;
        return Err("model_setup_failed".into());
    }
    Ok(())
}

#[tauri::command]
#[expect(
    clippy::too_many_arguments,
    reason = "Tauri injects four independent managed states; preserve the IPC contract"
)]
async fn update_chat_model(
    setup: llm_config::ChatModelSetup,
    secret: String,
    streaming: Option<bool>,
    world_id: Option<String>,
    config: State<'_, LaunchConfig>,
    credentials: State<'_, SharedCredentialStore>,
    supervisor: State<'_, SharedSupervisor>,
    updates: State<'_, updater::UpdateState>,
) -> Result<ModelUpdateOutcome, String> {
    let _update_guard = updates
        .operation
        .try_lock()
        .map_err(|_| "update_busy".to_owned())?;
    let mut supervisor = supervisor.lock().await;
    update_chat_model_streaming_with(
        setup,
        secret,
        streaming,
        &config,
        credentials.inner().as_ref(),
        &mut supervisor,
        world_id.as_deref(),
    )
    .await
}

#[cfg(test)]
async fn update_chat_model_with(
    setup: llm_config::ChatModelSetup,
    secret: String,
    config: &LaunchConfig,
    credentials: &dyn CredentialStore,
    supervisor: &mut CoreSupervisor,
) -> Result<ModelUpdateOutcome, String> {
    update_chat_model_streaming_with(setup, secret, None, config, credentials, supervisor, None)
        .await
}

async fn update_chat_model_streaming_with(
    setup: llm_config::ChatModelSetup,
    mut secret: String,
    streaming: Option<bool>,
    config: &LaunchConfig,
    credentials: &dyn CredentialStore,
    supervisor: &mut CoreSupervisor,
    world_id: Option<&str>,
) -> Result<ModelUpdateOutcome, String> {
    llm_config::validate_world_scope(world_id).map_err(str::to_owned)?;
    if secret.len() > 4096 {
        return Err("model_setup_invalid".to_owned());
    }
    let health = supervisor
        .authenticated_health_for_world(world_id)
        .await
        .map_err(str::to_owned)?;
    if !matches!(
        health.llm_status.as_str(),
        "ready" | "partially_configured" | "unconfigured"
    ) {
        return Err("model_update_unavailable".to_owned());
    }
    let previous = tokio::fs::read(&config.llm_config_path)
        .await
        .map_err(|_| "llm_config_read_failed".to_owned())?;
    let (selected, _) = llm_config::scope_document(&previous, world_id).map_err(str::to_owned)?;
    let managed = llm_config::managed_chat_configuration(&selected).map_err(str::to_owned)?;
    if secret.is_empty()
        && (managed.setup.provider_kind != setup.provider_kind
            || managed
                .setup
                .base_url
                .as_deref()
                .map(|url| url.trim_end_matches('/'))
                != setup
                    .base_url
                    .as_deref()
                    .map(|url| url.trim_end_matches('/'))
            || health.llm_status != "ready")
    {
        return Err("model_update_new_secret_required".to_owned());
    }
    let new_reference = (!secret.is_empty()).then(|| Uuid::new_v4().to_string());
    let reference = new_reference.as_deref().unwrap_or(&managed.secret_ref);
    let document = llm_config::single_chat_document_streaming(
        &setup,
        reference,
        streaming.unwrap_or(managed.streaming),
    )
    .map_err(str::to_owned)?;
    let document =
        llm_config::replace_scope(&previous, &document, world_id).map_err(str::to_owned)?;
    if let Some(reference) = new_reference.as_deref() {
        credentials
            .put(reference, &secret)
            .map_err(credential_error)?;
    }
    secret.clear();
    if llm_config::write_atomic(&config.llm_config_path, &document)
        .await
        .is_err()
    {
        if let Some(reference) = new_reference.as_deref() {
            credentials.delete(reference).map_err(credential_error)?;
        }
        return Err("llm_config_write_failed".to_owned());
    }
    let started = supervisor.restart(config).await.is_ok();
    let ready = started
        && supervisor
            .authenticated_health_for_world(world_id)
            .await
            .is_ok_and(|health| health.llm_status == "ready");
    if !ready {
        if llm_config::write_atomic(&config.llm_config_path, &previous)
            .await
            .is_err()
        {
            let _ = supervisor.stop(Duration::from_secs(3)).await;
            return Err("model_setup_recovery_failed".to_owned());
        }
        let restored = supervisor.restart(config).await.is_ok();
        let cleaned = new_reference
            .as_deref()
            .is_none_or(|reference| credentials.delete(reference).is_ok());
        if !restored || !cleaned {
            return Err("model_setup_recovery_failed".to_owned());
        }
        return Err("model_setup_failed".to_owned());
    }
    let retained = llm_config::credential_references(&document).ok();
    let old_credential_cleanup_incomplete = new_reference.is_some()
        && match retained {
            Some(retained) => {
                !retained.contains(&managed.secret_ref)
                    && credentials.delete(&managed.secret_ref).is_err()
            }
            None => true, // An unreadable other scope may still reference the old key.
        };
    Ok(ModelUpdateOutcome {
        old_credential_cleanup_incomplete,
    })
}

#[tauri::command]
async fn use_default_chat_model(
    world_id: String,
    config: State<'_, LaunchConfig>,
    credentials: State<'_, SharedCredentialStore>,
    supervisor: State<'_, SharedSupervisor>,
    updates: State<'_, updater::UpdateState>,
) -> Result<ModelUpdateOutcome, String> {
    let _update_guard = updates
        .operation
        .try_lock()
        .map_err(|_| "update_busy".to_owned())?;
    llm_config::validate_world_scope(Some(&world_id)).map_err(str::to_owned)?;
    let mut supervisor = supervisor.lock().await;
    let previous = tokio::fs::read(&config.llm_config_path)
        .await
        .map_err(|_| "llm_config_read_failed".to_owned())?;
    let document = llm_config::inherit_default(&previous, &world_id).map_err(str::to_owned)?;
    if document == previous {
        return Ok(ModelUpdateOutcome {
            old_credential_cleanup_incomplete: false,
        });
    }
    llm_config::write_atomic(&config.llm_config_path, &document)
        .await
        .map_err(str::to_owned)?;
    let healthy = supervisor.restart(&config).await.is_ok()
        && supervisor
            .authenticated_health_for_world(Some(&world_id))
            .await
            .is_ok_and(|health| health.llm_status != "degraded");
    if !healthy {
        if llm_config::write_atomic(&config.llm_config_path, &previous)
            .await
            .is_err()
            || supervisor.restart(&config).await.is_err()
        {
            let _ = supervisor.stop(Duration::from_secs(3)).await;
            return Err("model_setup_recovery_failed".to_owned());
        }
        return Err("model_setup_failed".to_owned());
    }
    let retained = llm_config::credential_references(&document).map_err(str::to_owned)?;
    let previous_refs = llm_config::credential_references(&previous).map_err(str::to_owned)?;
    let mut cleanup_incomplete = false;
    for reference in previous_refs {
        if !retained.contains(&reference) && credentials.delete(&reference).is_err() {
            cleanup_incomplete = true;
        }
    }
    Ok(ModelUpdateOutcome {
        old_credential_cleanup_incomplete: cleanup_incomplete,
    })
}

#[derive(Serialize)]
struct WorldModelCleanupOutcome {
    old_credential_cleanup_incomplete: bool,
    core_restarted: bool,
}

#[tauri::command]
async fn forget_deleted_world_model(
    world_id: String,
    config: State<'_, LaunchConfig>,
    credentials: State<'_, SharedCredentialStore>,
    supervisor: State<'_, SharedSupervisor>,
    updates: State<'_, updater::UpdateState>,
) -> Result<WorldModelCleanupOutcome, String> {
    let _guard = updates.operation.try_lock().map_err(|_| "update_busy")?;
    llm_config::validate_world_scope(Some(&world_id)).map_err(str::to_owned)?;
    let mut host = supervisor.lock().await;
    let connection = host.connection().map_err(str::to_owned)?;
    let http = reqwest::Client::builder()
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(5))
        .build()
        .map_err(|_| "world_cleanup_core_unavailable")?;
    let receipt: serde_json::Value = http
        .get(format!(
            "{}/api/v1/worlds/{}/deletion",
            connection.endpoint, world_id
        ))
        .bearer_auth(connection.bearer_token())
        .send()
        .await
        .map_err(|_| "world_cleanup_core_unavailable")?
        .error_for_status()
        .map_err(|_| "world_cleanup_core_unavailable")?
        .json()
        .await
        .map_err(|_| "world_cleanup_receipt_invalid")?;
    if receipt["deleted"] != true {
        return Err("world_cleanup_not_deleted".to_owned());
    }
    let previous = match tokio::fs::read(&config.llm_config_path).await {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(WorldModelCleanupOutcome {
                old_credential_cleanup_incomplete: false,
                core_restarted: false,
            })
        }
        Err(_) => return Err("llm_config_read_failed".to_owned()),
    };
    let document = llm_config::inherit_default(&previous, &world_id).map_err(str::to_owned)?;
    if document == previous {
        return Ok(WorldModelCleanupOutcome {
            old_credential_cleanup_incomplete: false,
            core_restarted: false,
        });
    }
    if let Err(error) = updater::maintenance(&connection, "prepare").await {
        let _ = updater::maintenance(&connection, "cancel").await;
        return Err(error);
    }
    let drained = async {
        let deadline = tokio::time::Instant::now() + Duration::from_secs(180);
        loop {
            let status = updater::maintenance(&connection, "status").await?;
            if !status.preparing {
                return Err("world_cleanup_barrier_expired".to_owned());
            }
            if status.active == 0 {
                return Ok(());
            }
            if tokio::time::Instant::now() >= deadline {
                return Err("world_cleanup_tasks_running".to_owned());
            }
            tokio::time::sleep(Duration::from_millis(500)).await;
        }
    }
    .await;
    if let Err(error) = drained {
        let _ = updater::maintenance(&connection, "cancel").await;
        return Err(error);
    }
    if let Err(error) = llm_config::write_atomic(&config.llm_config_path, &document).await {
        let _ = updater::maintenance(&connection, "cancel").await;
        return Err(error.to_owned());
    }
    if host.restart(&config).await.is_err() {
        let _ = llm_config::write_atomic(&config.llm_config_path, &previous).await;
        let _ = host.restart(&config).await;
        return Err("world_cleanup_restart_failed".to_owned());
    }
    let retained = llm_config::credential_references(&document).map_err(str::to_owned)?;
    let mut incomplete = false;
    for reference in llm_config::credential_references(&previous).map_err(str::to_owned)? {
        if !retained.contains(&reference) && credentials.delete(&reference).is_err() {
            incomplete = true;
        }
    }
    Ok(WorldModelCleanupOutcome {
        old_credential_cleanup_incomplete: incomplete,
        core_restarted: true,
    })
}

pub fn run() {
    let credentials: SharedCredentialStore = Arc::new(NativeCredentialStore);
    let supervisor = Arc::new(Mutex::new(CoreSupervisor::with_credential_store(
        credentials.clone(),
    )));
    let stopping = Arc::new(AtomicBool::new(false));
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, args, _cwd| {
            if !args.iter().any(|arg| arg == "--background") {
                background::show_main(app);
            }
        }))
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec!["--background"]),
        ))
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_dialog::init())
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::Focused(false)) {
                background::hide_presence(window.app_handle());
            }
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window
                    .try_state::<background::BackgroundState>()
                    .is_some_and(|state| state.closes_to_tray())
                {
                    api.prevent_close();
                    let _ = window.hide();
                    background::hide_presence(window.app_handle());
                }
            }
        })
        .manage(supervisor.clone())
        .manage(credentials)
        .invoke_handler(tauri::generate_handler![
            core_connection,
            retry_core_start,
            report_ui_ready,
            credential_put,
            credential_delete,
            credential_status,
            speech_credential_put,
            media_credential_put,
            forget_media_credentials,
            forget_speech_credentials,
            local_speech::local_speech_status,
            local_speech::choose_local_speech_folder,
            local_speech::prepare_local_speech,
            local_speech::repair_local_speech,
            local_images::local_image_status,
            local_images::choose_local_image_folder,
            local_images::prepare_local_image,
            configure_chat_model,
            repair_chat_model,
            managed_chat_model_setup,
            update_chat_model,
            use_default_chat_model,
            forget_deleted_world_model,
            file_exports::save_file_export,
            background::desktop_background_status,
            background::configure_desktop_background,
            background::report_desktop_presence,
            updater::desktop_update_status,
            updater::configure_desktop_updates,
            updater::check_desktop_update,
            updater::claim_desktop_update_popup,
            updater::dismiss_desktop_update_popup,
            updater::install_desktop_update,
            updater::acknowledge_desktop_update,
            updater::rollback_desktop_update,
            save_safety::save_safety_status,
            save_safety::retry_save_start,
            save_safety::create_save_backup,
            save_safety::restore_save_backup,
            save_safety::resume_restored_save,
            save_safety::configure_save_backup_location,
            save_safety::export_save_backup,
            save_safety::import_save_backup,
            save_safety::clear_saved_data
        ])
        .setup(|app| {
            let mut app_data = app.path().app_data_dir()?;
            if cfg!(debug_assertions) && std::env::var("LW_DESKTOP_SMOKE").as_deref() == Ok("1") {
                if let Some(isolated) = std::env::var_os("LW_DESKTOP_SMOKE_APP_DATA") {
                    app_data = isolated.into();
                }
            }
            app.manage(background::BackgroundState::load(&app_data));
            app.manage(updater::UpdateState::load(&app_data));
            background::install_tray(app)?;
            let executable_dir = std::env::current_exe()?
                .parent()
                .ok_or("desktop_executable_directory_missing")?
                .to_path_buf();
            let project_root = if cfg!(debug_assertions)
                && !executable_dir.join(".dreamtalk-package.json").is_file()
            {
                std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("../../..")
                    .canonicalize()?
            } else if executable_dir
                .join("core")
                .join("dreamtalk-core.exe")
                .is_file()
            {
                executable_dir
            } else if cfg!(debug_assertions) {
                std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("../../..")
                    .canonicalize()?
            } else {
                executable_dir
            };
            let config = LaunchConfig {
                project_root,
                app_data: app_data.clone(),
                startup_timeout: supervisor::CORE_STARTUP_TIMEOUT,
                llm_config_path: app_data.join("config").join("llm.json"),
            };
            let supervisor = app.state::<SharedSupervisor>().inner().clone();
            app.manage(config.clone());
            app.manage(local_speech::LocalSpeechState::default());
            app.manage(local_images::LocalImageState::default());
            let speech_app = app.handle().clone();
            save_safety::start_automatic(speech_app.clone(), config.clone(), supervisor.clone());
            tauri::async_runtime::spawn(async move {
                // A repaired patch can resume a known interrupted upgrade.
                // Keep the maintenance hold and all checks; never replay work.
                let version = speech_app.package_info().version.to_string();
                let retry = updater::retry_start_available(&config, &version);
                let result = if retry && updater::prepare_start_retry(&config, &version).is_err() {
                    Err("save_update_retry_unavailable")
                } else {
                    supervisor
                        .lock()
                        .await
                        .start_with_update_retry(&config, retry)
                        .await
                };
                if result.is_err() && config.app_data.join("updates/handoff.json").exists() {
                    let _ = tokio::fs::write(
                        config.app_data.join("update-failure.json"),
                        b"{\"code\":\"save_update_start_failed\"}",
                    )
                    .await;
                }
                if result.is_ok() {
                    let verification = if retry {
                        updater::verify_retried_start(&speech_app, &config, &supervisor).await
                    } else {
                        updater::verify_pending_start(&speech_app, &config, &supervisor).await
                    };
                    if verification.is_err() {
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
                        return;
                    }
                    tokio::join!(
                        local_speech::on_start(
                            speech_app.clone(),
                            config.clone(),
                            supervisor.clone()
                        ),
                        local_images::on_start(speech_app, config, supervisor),
                    );
                }
            });
            if !std::env::args().any(|arg| arg == "--background") {
                if let Some(window) = app.get_webview_window("main") {
                    window.show()?;
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("desktop_bootstrap_failed");
    app.run(move |handle, event_kind| {
        if let RunEvent::ExitRequested { api, code, .. } = event_kind {
            if code.is_none() || !stopping.load(Ordering::SeqCst) {
                api.prevent_exit();
                if !stopping.swap(true, Ordering::SeqCst) {
                    let supervisor = supervisor.clone();
                    let handle = handle.clone();
                    tauri::async_runtime::spawn(async move {
                        // Core HTTP draining, control closure and SQLite cleanup
                        // have separate bounds; allow the existing 30s shutdown
                        // budget before ordinary quit considers its fallback.
                        let _ = supervisor.lock().await.stop(Duration::from_secs(30)).await;
                        handle
                            .state::<local_speech::LocalSpeechState>()
                            .0
                            .lock()
                            .await
                            .stop()
                            .await;
                        handle
                            .state::<local_images::LocalImageState>()
                            .0
                            .lock()
                            .await
                            .stop()
                            .await;
                        handle.exit(0);
                    });
                }
            }
        }
    });
}

#[cfg(all(test, windows))]
mod model_update_tests {
    use super::*;

    #[test]
    fn startup_retry_restarts_a_stopped_failed_host_and_reuses_a_live_core() {
        tauri::async_runtime::block_on(async {
            let directory = tempfile::tempdir().unwrap();
            let mut config = LaunchConfig {
                project_root: directory.path().join("missing-runtime"),
                app_data: directory.path().join("app"),
                startup_timeout: supervisor::CORE_STARTUP_TIMEOUT,
                llm_config_path: directory.path().join("app/config/llm.json"),
            };
            let mut host =
                CoreSupervisor::with_credential_store(Arc::new(MemoryCredentialStore::default()));
            assert!(host.start(&config).await.is_err());
            assert_eq!(host.state, supervisor::SupervisorState::Failed);
            assert!(host.safely_stopped());
            config.project_root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../..")
                .canonicalize()
                .unwrap();
            let (connection, restarted) = recover_core_start(&config, &mut host).await.unwrap();
            assert!(restarted);
            let (same, restarted) = recover_core_start(&config, &mut host).await.unwrap();
            assert!(!restarted);
            assert_eq!(same.generation, connection.generation);
            host.stop(Duration::from_secs(4)).await.unwrap();
        });
    }

    #[test]
    fn degraded_configuration_can_be_repaired_without_touching_other_worlds_or_old_keys() {
        tauri::async_runtime::block_on(async {
            let directory = tempfile::tempdir().unwrap();
            let config = LaunchConfig {
                project_root: std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("../../..")
                    .canonicalize()
                    .unwrap(),
                app_data: directory.path().to_owned(),
                startup_timeout: supervisor::CORE_STARTUP_TIMEOUT,
                llm_config_path: directory.path().join("config/llm.json"),
            };
            let credentials = Arc::new(MemoryCredentialStore::default());
            let mut host = CoreSupervisor::with_credential_store(credentials.clone());
            let reference = "00000000-0000-0000-0000-000000000001";
            let world = "00000000-0000-0000-0000-000000000002";
            let other = "00000000-0000-0000-0000-000000000003";
            credentials.put(reference, "OLD-KEY-CANARY").unwrap();
            let setup = llm_config::ChatModelSetup {
                provider_kind: "anthropic".into(),
                model_id: "example-model".into(),
                base_url: None,
                max_billable_input_tokens: 20000,
                max_output_tokens: 2000,
                timeout_ms: 30000,
                native_json: false,
            };
            let valid: serde_json::Value = serde_json::from_slice(
                &llm_config::single_chat_document(&setup, reference).unwrap(),
            )
            .unwrap();
            let original = serde_json::json!({"version":2,"default":valid,
                "worlds":{world:{"invalid":true},other:valid}});
            let bytes = serde_json::to_vec(&original).unwrap();
            std::fs::create_dir_all(config.llm_config_path.parent().unwrap()).unwrap();
            llm_config::write_atomic(&config.llm_config_path, &bytes)
                .await
                .unwrap();
            host.start(&config).await.unwrap();
            assert_eq!(
                host.authenticated_health_for_world(Some(world))
                    .await
                    .unwrap()
                    .llm_status,
                "degraded"
            );
            assert_eq!(
                host.authenticated_health_for_world(Some(other))
                    .await
                    .unwrap()
                    .llm_status,
                "ready"
            );
            // A failed secure-store write leaves the source configuration intact.
            credentials.set_unavailable(true);
            assert_eq!(
                repair_chat_model_with(
                    setup.clone(),
                    "NEW-KEY-CANARY".into(),
                    false,
                    Some(world),
                    &config,
                    credentials.as_ref(),
                    &mut host
                )
                .await
                .unwrap_err(),
                "secure_storage_unavailable"
            );
            assert_eq!(std::fs::read(&config.llm_config_path).unwrap(), bytes);
            credentials.set_unavailable(false);
            repair_chat_model_with(
                setup,
                "NEW-KEY-CANARY".into(),
                false,
                Some(world),
                &config,
                credentials.as_ref(),
                &mut host,
            )
            .await
            .unwrap();
            let repaired: serde_json::Value =
                serde_json::from_slice(&std::fs::read(&config.llm_config_path).unwrap()).unwrap();
            assert_eq!(repaired["default"], original["default"]);
            assert_eq!(repaired["worlds"][other], original["worlds"][other]);
            assert_eq!(credentials.resolve(reference).unwrap(), "OLD-KEY-CANARY");
            let archives: Vec<_> = std::fs::read_dir(config.app_data.join("config/model-recovery"))
                .unwrap()
                .map(|entry| std::fs::read(entry.unwrap().path()).unwrap())
                .collect();
            assert!(archives.iter().all(|archive| archive == &bytes));
            assert!(!archives.is_empty());
            assert_eq!(
                host.authenticated_health_for_world(Some(world))
                    .await
                    .unwrap()
                    .llm_status,
                "ready"
            );
            assert_eq!(
                host.authenticated_health_for_world(Some(other))
                    .await
                    .unwrap()
                    .llm_status,
                "ready"
            );
            host.stop(Duration::from_secs(4)).await.unwrap();
        });
    }
    use credentials::MemoryCredentialStore;

    #[test]
    fn managed_model_update_restarts_core_rotates_key_and_keeps_secrets_off_disk() {
        tauri::async_runtime::block_on(async {
            let directory = tempfile::tempdir().unwrap();
            let config = LaunchConfig {
                project_root: std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("../../..")
                    .canonicalize()
                    .unwrap(),
                app_data: directory.path().to_owned(),
                startup_timeout: supervisor::CORE_STARTUP_TIMEOUT,
                llm_config_path: directory.path().join("config").join("llm.json"),
            };
            let credentials = Arc::new(MemoryCredentialStore::default());
            let mut supervisor = CoreSupervisor::with_credential_store(credentials.clone());
            supervisor.start(&config).await.unwrap();
            let old_reference = "00000000-0000-0000-0000-000000000001";
            credentials.put(old_reference, "OLD-KEY-CANARY").unwrap();
            let setup = llm_config::ChatModelSetup {
                provider_kind: "anthropic".to_owned(),
                model_id: "old-model".to_owned(),
                base_url: None,
                max_billable_input_tokens: 20_000,
                max_output_tokens: 2_000,
                timeout_ms: 30_000,
                native_json: false,
            };
            let original = llm_config::single_chat_document(&setup, old_reference).unwrap();
            llm_config::write_atomic(&config.llm_config_path, &original)
                .await
                .unwrap();
            supervisor.restart(&config).await.unwrap();
            assert_eq!(
                supervisor.authenticated_health().await.unwrap().llm_status,
                "ready"
            );

            let changed = llm_config::ChatModelSetup {
                model_id: "new-model".to_owned(),
                ..setup
            };
            let result = update_chat_model_with(
                changed.clone(),
                "NEW-KEY-CANARY".to_owned(),
                &config,
                credentials.as_ref(),
                &mut supervisor,
            )
            .await
            .unwrap();
            assert!(!result.old_credential_cleanup_incomplete);
            assert!(!credentials.exists(old_reference).unwrap());
            assert_eq!(
                supervisor.authenticated_health().await.unwrap().llm_status,
                "ready"
            );
            let bytes = std::fs::read(&config.llm_config_path).unwrap();
            let managed = llm_config::managed_chat_configuration(&bytes).unwrap();
            assert_eq!(managed.setup, changed);
            assert!(credentials.exists(&managed.secret_ref).unwrap());
            assert!(!bytes
                .windows(b"KEY-CANARY".len())
                .any(|part| part == b"KEY-CANARY"));

            let limits_changed = llm_config::ChatModelSetup {
                max_output_tokens: 1_000,
                ..changed
            };
            update_chat_model_with(
                limits_changed.clone(),
                String::new(),
                &config,
                credentials.as_ref(),
                &mut supervisor,
            )
            .await
            .unwrap();
            let updated = llm_config::managed_chat_configuration(
                &std::fs::read(&config.llm_config_path).unwrap(),
            )
            .unwrap();
            assert_eq!(updated.secret_ref, managed.secret_ref);
            assert_eq!(updated.setup, limits_changed);
            supervisor.stop(Duration::from_secs(4)).await.unwrap();
        });
    }
}
