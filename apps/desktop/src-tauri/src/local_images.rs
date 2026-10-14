//! Supervise the separately installed Ollama environment; never download or run inference.
use crate::{supervisor::LaunchConfig, SharedSupervisor};
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
pub struct LocalImageState(pub Mutex<LocalImages>);

#[derive(Default)]
pub struct LocalImages {
    child: Option<Child>,
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
        .map_err(|_| "media_local_folder_invalid")?;
    if !root.join("ollama/ollama.exe").is_file() || !root.join("models/manifests").is_dir() {
        return Err("media_local_folder_invalid".into());
    }
    Ok(root)
}

async fn configured(config: &LaunchConfig) -> Result<Option<PathBuf>, String> {
    let path = config.app_data.join("config/local-images.json");
    match tokio::fs::metadata(&path).await {
        Ok(metadata) if metadata.len() <= 8192 => {
            let bytes = tokio::fs::read(path)
                .await
                .map_err(|_| "media_local_config_invalid")?;
            let value: Configuration =
                serde_json::from_slice(&bytes).map_err(|_| "media_local_config_invalid")?;
            Ok(Some(validated(&value.model_root)?))
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            // Only the documented deployment layout; no drive or installed-program scan.
            Ok(config.project_root.ancestors().take(6).find_map(|parent| {
                validated(&parent.join("image-runtime"))
                    .ok()
                    .or_else(|| validated(&parent.join("artifacts/image-runtime")).ok())
            }))
        }
        _ => Err("media_local_config_invalid".into()),
    }
}

async fn health() -> Result<bool, String> {
    let client = reqwest::Client::builder()
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(5))
        .timeout(Duration::from_secs(10))
        .build()
        .map_err(|_| "media_local_unavailable")?;
    let mut response = match client
        .get("http://127.0.0.1:11434/api/version")
        .send()
        .await
    {
        Ok(response) => response,
        Err(error) if error.is_timeout() => return Err("media_local_probe_timeout".into()),
        Err(error) if error.is_connect() => return Ok(false),
        Err(_) => return Err("media_local_unavailable".into()),
    };
    if !response.status().is_success() || response.content_length().is_some_and(|n| n > 4096) {
        return Err("media_local_port_occupied".into());
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| "media_local_unavailable")?
    {
        if bytes.len() + chunk.len() > 4096 {
            return Err("media_local_port_occupied".into());
        }
        bytes.extend_from_slice(&chunk);
    }
    let value: serde_json::Value =
        serde_json::from_slice(&bytes).map_err(|_| "media_local_port_occupied")?;
    if !value["version"]
        .as_str()
        .is_some_and(|s| !s.is_empty() && s.len() <= 64)
    {
        return Err("media_local_port_occupied".into());
    }
    Ok(true)
}

impl LocalImages {
    async fn ensure(&mut self, config: &LaunchConfig, root: PathBuf) -> Result<Status, String> {
        if health().await? {
            return Ok(Status {
                model_root: Some(root.to_string_lossy().into()),
                state: "ready",
            });
        }
        if self
            .child
            .as_mut()
            .is_some_and(|child| child.try_wait().ok().flatten().is_none())
        {
            return Err("media_local_start_timeout".into());
        }
        let logs = config.app_data.join("logs");
        tokio::fs::create_dir_all(&logs)
            .await
            .map_err(|_| "media_local_log_unavailable")?;
        let output = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(logs.join("local-images.log"))
            .map_err(|_| "media_local_log_unavailable")?;
        let mut command = Command::new(root.join("ollama/ollama.exe"));
        command
            .arg("serve")
            .current_dir(&root)
            .env("OLLAMA_HOST", "127.0.0.1:11434")
            .env("OLLAMA_MODELS", root.join("models"))
            .env("OLLAMA_NO_CLOUD", "1")
            .env("OLLAMA_NUM_PARALLEL", "1")
            .env("OLLAMA_MAX_LOADED_MODELS", "1")
            .env("OLLAMA_CONTEXT_LENGTH", "4096")
            .env("OLLAMA_KEEP_ALIVE", "30s")
            .env_remove("HTTP_PROXY")
            .env_remove("HTTPS_PROXY")
            .env_remove("ALL_PROXY")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::from(output));
        #[cfg(windows)]
        command.creation_flags(0x08000000);
        self.child = Some(command.spawn().map_err(|_| "media_local_start_failed")?);
        let deadline = tokio::time::Instant::now() + Duration::from_secs(20);
        loop {
            if self
                .child
                .as_mut()
                .unwrap()
                .try_wait()
                .map_err(|_| "media_local_start_failed")?
                .is_some()
            {
                self.child = None;
                return Err("media_local_start_failed".into());
            }
            if health().await? {
                return Ok(Status {
                    model_root: Some(root.to_string_lossy().into()),
                    state: "ready",
                });
            }
            if tokio::time::Instant::now() >= deadline {
                return Err("media_local_start_timeout".into());
            }
            tokio::time::sleep(Duration::from_millis(500)).await;
        }
    }

    pub async fn stop(&mut self) {
        if let Some(mut child) = self.child.take() {
            // Reused external Ollama instances are never owned or terminated here.
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
            .map_err(|_| "media_local_unavailable")?
            .get(format!(
                "{}/system/media/local-demand",
                connection.endpoint.trim_end_matches('/')
            ))
            .bearer_auth(connection.bearer_token())
            .send()
            .await
            .map_err(|_| "media_local_unavailable")?
            .error_for_status()
            .map_err(|_| "media_local_unavailable")?
            .json()
            .await
            .map_err(|_| "media_local_unavailable")?;
        if demand["enabled"] == true {
            if let Some(root) = configured(&config).await? {
                app.state::<LocalImageState>()
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
        crate::supervisor::event("local_images_start_unavailable");
    }
}

#[tauri::command]
pub async fn local_image_status(config: State<'_, LaunchConfig>) -> Result<Status, String> {
    let root = configured(&config).await?;
    Ok(Status {
        state: if health().await? {
            "ready"
        } else if root.is_some() {
            "stopped"
        } else {
            "unconfigured"
        },
        model_root: root.map(|path| path.to_string_lossy().into()),
    })
}

#[tauri::command]
pub async fn choose_local_image_folder(app: tauri::AppHandle) -> Result<Option<String>, String> {
    let (sender, receiver) = tokio::sync::oneshot::channel();
    app.dialog().file().pick_folder(move |path| {
        let _ = sender.send(path);
    });
    let Some(path) = receiver.await.map_err(|_| "media_local_folder_invalid")? else {
        return Ok(None);
    };
    let root = validated(&path.into_path().map_err(|_| "media_local_folder_invalid")?)?;
    Ok(Some(root.to_string_lossy().into()))
}

#[tauri::command]
pub async fn prepare_local_image(
    app: tauri::AppHandle,
    config: State<'_, LaunchConfig>,
    updates: State<'_, crate::updater::UpdateState>,
    model_root: Option<String>,
) -> Result<Status, String> {
    let _guard = updates.operation.try_lock().map_err(|_| "update_busy")?;
    let root = match model_root {
        Some(path) => validated(Path::new(&path))?,
        None => match configured(&config).await? {
            Some(root) => root,
            None if health().await? => {
                return Ok(Status {
                    model_root: None,
                    state: "ready",
                })
            }
            None => return Err("media_local_folder_required".into()),
        },
    };
    let result = app
        .state::<LocalImageState>()
        .0
        .lock()
        .await
        .ensure(&config, root.clone())
        .await?;
    let path = config.app_data.join("config/local-images.json");
    tokio::fs::create_dir_all(path.parent().unwrap())
        .await
        .map_err(|_| "media_local_config_invalid")?;
    let bytes = serde_json::to_vec(&Configuration { model_root: root })
        .map_err(|_| "media_local_config_invalid")?;
    let temporary = path.with_extension("tmp");
    tokio::fs::write(&temporary, bytes)
        .await
        .map_err(|_| "media_local_config_invalid")?;
    tokio::fs::rename(temporary, path)
        .await
        .map_err(|_| "media_local_config_invalid")?;
    Ok(result)
}
