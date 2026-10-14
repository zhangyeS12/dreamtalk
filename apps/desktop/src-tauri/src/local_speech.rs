//! Optional model environment supervision; no model weights or secrets in the app bundle.
use crate::{
    llm_config, speech_credentials, supervisor::LaunchConfig, SharedCredentialStore,
    SharedSupervisor,
};
use serde::{Deserialize, Serialize};
use std::{
    path::{Path, PathBuf},
    process::Stdio,
    time::Duration,
};
use tauri::{Manager, State};
use tauri_plugin_dialog::DialogExt;
use tokio::{
    process::{Child, Command},
    sync::Mutex,
};

#[derive(Default)]
pub struct LocalSpeechState(pub Mutex<LocalSpeech>);

#[derive(Default)]
pub struct LocalSpeech {
    child: Option<Child>,
    root: Option<PathBuf>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Configuration {
    model_root: PathBuf,
}

#[derive(Serialize)]
pub struct Status {
    model_root: Option<String>,
    state: &'static str,
}

fn validated(root: &Path) -> Result<PathBuf, String> {
    let root = root
        .canonicalize()
        .map_err(|_| "speech_model_folder_invalid")?;
    if !root.join(".venv/Scripts/python.exe").is_file()
        || !root.join("checkpoints/config.yaml").is_file()
        || !root.join("indextts/infer_v2_5.py").is_file()
    {
        return Err("speech_model_folder_invalid".into());
    }
    Ok(root)
}

async fn configured(config: &LaunchConfig) -> Result<Option<PathBuf>, String> {
    let path = config.app_data.join("config/local-speech.json");
    match tokio::fs::metadata(&path).await {
        Ok(metadata) if metadata.len() <= 8192 => {
            let bytes = tokio::fs::read(path)
                .await
                .map_err(|_| "speech_model_config_invalid")?;
            let value: Configuration =
                serde_json::from_slice(&bytes).map_err(|_| "speech_model_config_invalid")?;
            Ok(Some(validated(&value.model_root)?))
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            // The official local deployment layout beside portable builds; no broad disk search.
            Ok(config
                .project_root
                .ancestors()
                .take(5)
                .find_map(|parent| validated(&parent.join("voice-runtime/index-tts")).ok()))
        }
        _ => Err("speech_model_config_invalid".into()),
    }
}

async fn token(root: &Path) -> Result<String, String> {
    let path = root.join("dreamtalk-voice-token.txt");
    let size = tokio::fs::metadata(&path)
        .await
        .map_err(|_| "speech_local_token_missing")?
        .len();
    if !(32..=4098).contains(&size) {
        return Err("speech_local_token_invalid".into());
    }
    let value = tokio::fs::read_to_string(path)
        .await
        .map_err(|_| "speech_local_token_invalid")?;
    let value = value.trim().to_owned();
    if value.len() < 32 || value.len() > 4096 || value.contains(['\r', '\n']) {
        return Err("speech_local_token_invalid".into());
    }
    Ok(value)
}

async fn health(secret: &str) -> Result<Option<bool>, String> {
    let client = reqwest::Client::builder()
        .no_proxy()
        // Windows can take just over two seconds to report ECONNREFUSED.
        // Do not let a shorter request deadline mask an unoccupied port.
        .connect_timeout(Duration::from_secs(5))
        .timeout(Duration::from_secs(10))
        .build()
        .map_err(|_| "speech_local_unavailable")?;
    let response = match client
        .get("http://127.0.0.1:7861/health")
        .bearer_auth(secret)
        .send()
        .await
    {
        Ok(value) => value,
        Err(error) if error.is_timeout() => return Err("speech_local_probe_timeout".into()),
        Err(error) if error.is_connect() => return Ok(None),
        Err(_) => return Err("speech_local_probe_failed".into()),
    };
    if response.status() == reqwest::StatusCode::NOT_FOUND {
        return Ok(Some(false));
    }
    if !response.status().is_success() || response.content_length().is_some_and(|size| size > 4096)
    {
        return Err("speech_local_key_required".into());
    }
    let bytes = response
        .bytes()
        .await
        .map_err(|_| "speech_local_unavailable")?;
    if bytes.len() > 4096 {
        return Err("speech_provider_protocol".into());
    }
    let info: serde_json::Value =
        serde_json::from_slice(&bytes).map_err(|_| "speech_provider_protocol")?;
    if info["engine"] != "indextts-2.5" || info["protocol"] != 2 {
        return Err("speech_provider_protocol".into());
    }
    if info["inference_revision"] != 8 {
        return Err("speech_local_bridge_outdated".into());
    }
    Ok(Some(true))
}

impl LocalSpeech {
    async fn ensure(&mut self, config: &LaunchConfig, root: PathBuf) -> Result<Status, String> {
        let secret = token(&root).await?;
        match health(&secret).await? {
            Some(ready) => {
                return Ok(Status {
                    model_root: Some(root.to_string_lossy().into()),
                    state: if ready { "ready" } else { "legacy" },
                })
            }
            None => {}
        }
        if self
            .child
            .as_mut()
            .is_some_and(|child| child.try_wait().ok().flatten().is_none())
        {
            return Err("speech_local_start_timeout".into());
        }
        let bridge = config.project_root.join("scripts/serve-indextts.py");
        if !bridge.is_file() {
            return Err("speech_bridge_missing".into());
        }
        let logs = config.app_data.join("logs");
        tokio::fs::create_dir_all(&logs)
            .await
            .map_err(|_| "speech_local_log_unavailable")?;
        let output = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(logs.join("local-speech.log"))
            .map_err(|_| "speech_local_log_unavailable")?;
        let mut command = Command::new(root.join(".venv/Scripts/python.exe"));
        command
            .arg(&bridge)
            .arg("--model-dir")
            .arg(root.join("checkpoints"))
            .arg("--token-file")
            .arg(root.join("dreamtalk-voice-token.txt"))
            .current_dir(&root)
            .env("PYTHONPATH", &root)
            .env("PYTHONUNBUFFERED", "1")
            .env("HF_HUB_OFFLINE", "1")
            .env("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
            .env("TRANSFORMERS_OFFLINE", "1")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::from(output));
        if let Some(parent) = root.parent() {
            command.env("NLTK_DATA", parent.join("nltk-data"));
        }
        #[cfg(windows)]
        command.creation_flags(0x08000000);
        self.child = Some(command.spawn().map_err(|_| "speech_local_start_failed")?);
        self.root = Some(root.clone());
        let deadline = tokio::time::Instant::now() + Duration::from_secs(20);
        loop {
            if self
                .child
                .as_mut()
                .unwrap()
                .try_wait()
                .map_err(|_| "speech_local_start_failed")?
                .is_some()
            {
                self.child = None;
                return Err("speech_local_start_failed".into());
            }
            if health(&secret).await? == Some(true) {
                return Ok(Status {
                    model_root: Some(root.to_string_lossy().into()),
                    state: "ready",
                });
            }
            if tokio::time::Instant::now() >= deadline {
                return Err("speech_local_start_timeout".into());
            }
            tokio::time::sleep(Duration::from_millis(500)).await;
        }
    }

    pub async fn stop(&mut self) {
        if let Some(mut child) = self.child.take() {
            // Only a still-live child owned by this host; an external service is never killed.
            if matches!(child.try_wait(), Ok(None)) {
                #[cfg(windows)]
                if let Some(pid) = child.id() {
                    if let Some(system_root) = std::env::var_os("SystemRoot") {
                        let _ =
                            Command::new(PathBuf::from(system_root).join("System32/taskkill.exe"))
                                .args(["/PID", &pid.to_string(), "/T", "/F"])
                                .creation_flags(0x08000000)
                                .stdin(Stdio::null())
                                .stdout(Stdio::null())
                                .stderr(Stdio::null())
                                .status()
                                .await;
                    }
                }
                let _ = child.kill().await;
                let _ = child.wait().await;
            }
        }
    }
}

pub async fn on_start(app: tauri::AppHandle, config: LaunchConfig, supervisor: SharedSupervisor) {
    let result = async {
        let connection = supervisor
            .lock()
            .await
            .connection()
            .map_err(str::to_owned)?;
        let demand: serde_json::Value = reqwest::Client::builder()
            .no_proxy()
            .timeout(Duration::from_secs(10))
            .build()
            .map_err(|_| "speech_local_unavailable")?
            .get(format!(
                "{}/system/speech/local-demand",
                connection.endpoint.trim_end_matches('/')
            ))
            .bearer_auth(connection.bearer_token())
            .send()
            .await
            .map_err(|_| "speech_local_unavailable")?
            .error_for_status()
            .map_err(|_| "speech_local_unavailable")?
            .json()
            .await
            .map_err(|_| "speech_provider_protocol")?;
        if demand["enabled"] == true {
            if let Some(root) = configured(&config).await? {
                app.state::<LocalSpeechState>()
                    .0
                    .lock()
                    .await
                    .ensure(&config, root)
                    .await?;
            }
        }
        Ok::<(), String>(())
    }
    .await;
    if result.is_err() {
        crate::supervisor::event("local_speech_start_unavailable");
    }
}

#[tauri::command]
pub async fn local_speech_status(config: State<'_, LaunchConfig>) -> Result<Status, String> {
    let Some(root) = configured(&config).await? else {
        return Ok(Status {
            model_root: None,
            state: "unconfigured",
        });
    };
    let state = match health(&token(&root).await?).await {
        Ok(Some(true)) => "ready",
        Ok(Some(false)) => "legacy",
        Ok(None) => "stopped",
        Err(code) if code == "speech_local_bridge_outdated" => "outdated",
        Err(code) => return Err(code),
    };
    Ok(Status {
        model_root: Some(root.to_string_lossy().into()),
        state,
    })
}

#[tauri::command]
pub async fn choose_local_speech_folder(
    app: tauri::AppHandle,
    config: State<'_, LaunchConfig>,
    local: State<'_, LocalSpeechState>,
    updates: State<'_, crate::updater::UpdateState>,
) -> Result<Option<Status>, String> {
    let _guard = updates.operation.try_lock().map_err(|_| "update_busy")?;
    let dialog = app
        .dialog()
        .file()
        .set_title("选择 IndexTTS 2.5 文件夹（包含 .venv、checkpoints 和 indextts）");
    let root = tauri::async_runtime::spawn_blocking(move || dialog.blocking_pick_folder())
        .await
        .map_err(|_| "speech_model_folder_invalid")?;
    let Some(root) = root else {
        return Ok(None);
    };
    let root = validated(
        &root
            .into_path()
            .map_err(|_| "speech_model_folder_invalid")?,
    )?;
    token(&root).await?;
    let mut manager = local.0.lock().await;
    if manager.child.is_some() {
        return Err("speech_model_folder_busy".into());
    }
    let bytes = serde_json::to_vec(&Configuration {
        model_root: root.clone(),
    })
    .map_err(|_| "speech_model_config_invalid")?;
    llm_config::write_atomic(&config.app_data.join("config/local-speech.json"), &bytes)
        .await
        .map_err(str::to_owned)?;
    manager.root = Some(root.clone());
    Ok(Some(Status {
        model_root: Some(root.to_string_lossy().into()),
        state: "configured",
    }))
}

#[tauri::command]
pub async fn prepare_local_speech(
    world_id: String,
    secret_ref: String,
    config: State<'_, LaunchConfig>,
    credentials: State<'_, SharedCredentialStore>,
    supervisor: State<'_, SharedSupervisor>,
    local: State<'_, LocalSpeechState>,
    updates: State<'_, crate::updater::UpdateState>,
) -> Result<Status, String> {
    let _guard = updates.operation.try_lock().map_err(|_| "update_busy")?;
    let root = configured(&config)
        .await?
        .ok_or("speech_model_folder_missing")?;
    let secret = token(&root).await?;
    provision(
        &config,
        &credentials,
        &supervisor,
        &world_id,
        &secret_ref,
        &secret,
    )
    .await?;
    local.0.lock().await.ensure(&config, root).await
}

async fn provision(
    config: &LaunchConfig,
    credentials: &SharedCredentialStore,
    supervisor: &SharedSupervisor,
    world_id: &str,
    secret_ref: &str,
    secret: &str,
) -> Result<(), String> {
    let mut host = supervisor.lock().await;
    let exists = credentials
        .exists(secret_ref)
        .map_err(|_| "speech_key_required")?;
    speech_credentials::REGISTRY
        .authorize_reference(config, world_id, secret_ref, exists)
        .await
        .map_err(str::to_owned)?;
    credentials
        .put(secret_ref, secret)
        .map_err(|_| "speech_key_required")?;
    speech_credentials::REGISTRY
        .register(config, world_id, secret_ref)
        .await
        .map_err(str::to_owned)?;
    host.provision_credential(secret_ref, secret)
        .await
        .map_err(str::to_owned)?;
    Ok(())
}

#[tauri::command]
pub async fn repair_local_speech(
    world_id: String,
    secret_ref: String,
    config: State<'_, LaunchConfig>,
    credentials: State<'_, SharedCredentialStore>,
    supervisor: State<'_, SharedSupervisor>,
    local: State<'_, LocalSpeechState>,
    updates: State<'_, crate::updater::UpdateState>,
) -> Result<Status, String> {
    let _guard = updates.operation.try_lock().map_err(|_| "update_busy")?;
    let root = configured(&config)
        .await?
        .ok_or("speech_model_folder_missing")?;
    let secret = token(&root).await?;
    let exists = credentials
        .exists(&secret_ref)
        .map_err(|_| "speech_key_required")?;
    speech_credentials::REGISTRY
        .authorize_reference(&config, &world_id, &secret_ref, exists)
        .await
        .map_err(str::to_owned)?;
    let connection = supervisor
        .lock()
        .await
        .connection()
        .map_err(str::to_owned)?;
    let client = reqwest::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(10))
        .build()
        .map_err(|_| "speech_local_repair_failed")?;
    let url = format!(
        "{}/system/speech/local-repair",
        connection.endpoint.trim_end_matches('/')
    );
    let response = client
        .post(&url)
        .bearer_auth(connection.bearer_token())
        .send()
        .await
        .map_err(|_| "speech_local_repair_failed")?;
    if response.status() == reqwest::StatusCode::CONFLICT {
        return Err("speech_local_repair_busy".into());
    }
    let lease: serde_json::Value = response
        .error_for_status()
        .map_err(|_| "speech_local_repair_failed")?
        .json()
        .await
        .map_err(|_| "speech_local_repair_failed")?;
    let identity = lease["lease"]
        .as_str()
        .and_then(|value| uuid::Uuid::parse_str(value).ok())
        .ok_or("speech_local_repair_failed")?;
    let result = async {
        let helper = config.project_root.join("scripts/repair-local-speech.py");
        if !helper.is_file() {
            return Err("speech_local_repair_helper_missing".into());
        }
        let mut command = Command::new(root.join(".venv/Scripts/python.exe"));
        command
            .arg(&helper)
            .arg("--model-root")
            .arg(&root)
            .arg("--project-root")
            .arg(&config.project_root)
            .current_dir(&root)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .kill_on_drop(true);
        #[cfg(windows)]
        command.creation_flags(0x08000000);
        let output = tokio::time::timeout(Duration::from_secs(45), command.output())
            .await
            .map_err(|_| "speech_local_repair_failed")?
            .map_err(|_| "speech_local_repair_failed")?;
        if output.stdout.len() > 4096 {
            return Err("speech_local_repair_failed".into());
        }
        let result: serde_json::Value =
            serde_json::from_slice(&output.stdout).map_err(|_| "speech_local_repair_failed")?;
        if !output.status.success() {
            return Err(match result["error"].as_str() {
                Some("speech_local_repair_busy") => "speech_local_repair_busy",
                Some("speech_local_repair_unverified") => "speech_local_repair_unverified",
                Some("speech_local_repair_changed") => "speech_local_repair_changed",
                Some("speech_local_probe_failed") => "speech_local_probe_failed",
                _ => "speech_local_repair_failed",
            }
            .into());
        }
        if !matches!(
            result["state"].as_str(),
            Some("ready" | "stopped" | "updated")
        ) {
            return Err("speech_local_repair_failed".into());
        }
        provision(
            &config,
            &credentials,
            &supervisor,
            &world_id,
            &secret_ref,
            &secret,
        )
        .await?;
        local.0.lock().await.ensure(&config, root).await
    }
    .await;
    // Cleanup failure cannot permanently fence speech: this in-memory lease
    // expires after 120 seconds even when the host exits or loses its connection.
    let _ = client
        .delete(format!("{url}/{identity}"))
        .bearer_auth(connection.bearer_token())
        .send()
        .await;
    result
}
