use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use std::{
    path::PathBuf,
    process::Stdio,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    process::{Child, Command},
};
use uuid::Uuid;

pub const CONTRACT: &str =
    include_str!("../../../../services/core/src/livingworld/domain/api_contract.json");

#[derive(Deserialize)]
pub struct ApiContract {
    pub api_protocol: u32,
    pub loopback_host: String,
    pub session_derivation: String,
}

pub fn contract() -> ApiContract {
    serde_json::from_str(CONTRACT).expect("packaged_system_contract_invalid")
}

pub fn event(name: &'static str) {
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64();
    println!(
        "{}",
        serde_json::json!({"timestamp": timestamp, "level": "INFO", "component": "supervisor", "event": name})
    );
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub enum SupervisorState {
    Starting,
    Ready,
    Degraded,
    Restarting,
    Failed,
    Stopping,
}

#[derive(Clone, Serialize)]
pub struct CoreConnection {
    pub endpoint: String,
    token: String,
    pub generation: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReadyRecord {
    endpoint: String,
    generation: String,
    instance_nonce: String,
    api_protocol: u32,
    core_version: String,
    pid: u32,
    launcher_pid: u32,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Health {
    pub ready: bool,
    pub core_version: String,
    pub api_protocol: u32,
    pub generation: String,
}

pub struct LaunchConfig {
    pub project_root: PathBuf,
    pub app_data: PathBuf,
    pub startup_timeout: Duration,
}

// Owner/ACL validation is an explicit packaging extension point. The development
// implementation only uses an unpredictable app-data directory and create_new.
pub trait BootstrapFilePolicy {
    fn validate_directory(&self, directory: &std::path::Path) -> Result<(), &'static str>;
}
pub struct DevelopmentBootstrapPolicy;
impl BootstrapFilePolicy for DevelopmentBootstrapPolicy {
    fn validate_directory(&self, directory: &std::path::Path) -> Result<(), &'static str> {
        if !directory.is_absolute() || directory.is_symlink() {
            return Err("bootstrap_directory_invalid");
        }
        Ok(())
    }
}

pub struct StopReport {
    pub graceful: bool,
}

pub struct CoreSupervisor {
    pub state: SupervisorState,
    child: Option<Child>,
    session: Option<CoreConnection>,
    runtime_dir: Option<PathBuf>,
    http: reqwest::Client,
}

impl Default for CoreSupervisor {
    fn default() -> Self {
        Self::new()
    }
}

impl CoreSupervisor {
    pub fn new() -> Self {
        Self {
            state: SupervisorState::Starting,
            child: None,
            session: None,
            runtime_dir: None,
            http: reqwest::Client::builder()
                .no_proxy()
                .redirect(reqwest::redirect::Policy::none())
                .timeout(Duration::from_secs(1))
                .build()
                .expect("http_client_invalid"),
        }
    }

    pub fn connection(&self) -> Result<CoreConnection, &'static str> {
        if self.state != SupervisorState::Ready {
            return Err("core_not_ready");
        }
        self.session.clone().ok_or("core_session_missing")
    }

    pub async fn start(&mut self, config: &LaunchConfig) -> Result<(), &'static str> {
        if self.child.is_some() {
            return Err("core_already_started");
        }
        self.state = SupervisorState::Starting;
        event("supervisor_starting");
        let result = self.spawn_and_discover(config).await;
        if result.is_err() {
            let _ = self.stop(Duration::ZERO).await;
            self.state = SupervisorState::Failed;
            event("supervisor_failed");
        }
        result
    }

    async fn spawn_and_discover(&mut self, config: &LaunchConfig) -> Result<(), &'static str> {
        if !cfg!(windows) {
            return Err("desktop_runtime_requires_windows");
        }
        if !config.app_data.is_absolute() || config.app_data.starts_with(&config.project_root) {
            return Err("app_data_directory_required");
        }
        let api = contract();
        let nonce = Uuid::new_v4().to_string();
        let secret = format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple());
        let runtime = config.app_data.join("runtime").join(&nonce);
        tokio::fs::create_dir_all(&runtime)
            .await
            .map_err(|_| "runtime_directory_failed")?;
        self.runtime_dir = Some(runtime.clone());
        DevelopmentBootstrapPolicy.validate_directory(&runtime)?;
        let bootstrap_path = runtime.join("bootstrap.json");
        let input = serde_json::json!({
            "bootstrap_secret": secret, "instance_nonce": nonce,
            "protocol_min": api.api_protocol, "protocol_max": api.api_protocol,
            "data_dir": config.app_data.join("data"), "log_dir": config.app_data.join("logs"),
            "allowed_origins": ["http://127.0.0.1:1420", "http://tauri.localhost", "tauri://localhost"]
        });
        let mut file = tokio::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&bootstrap_path)
            .await
            .map_err(|_| "bootstrap_create_failed")?;
        file.write_all(input.to_string().as_bytes())
            .await
            .map_err(|_| "bootstrap_write_failed")?;
        file.sync_all().await.map_err(|_| "bootstrap_sync_failed")?;
        drop(file);
        let python = config
            .project_root
            .join(".venv")
            .join("Scripts")
            .join("python.exe");
        let mut command = Command::new(python);
        command
            .current_dir(&config.project_root)
            .args([
                "-m",
                "livingworld.bootstrap",
                "--desktop",
                "--bootstrap-path",
            ])
            .arg(&bootstrap_path)
            .arg("--parent-pid")
            .arg(std::process::id().to_string())
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .kill_on_drop(true);
        #[cfg(windows)]
        command.creation_flags(0x08000000);
        let mut child = command.spawn().map_err(|_| "core_spawn_failed")?;
        let pid = child.id().ok_or("core_pid_missing")?;
        if let Some(stdout) = child.stdout.take() {
            tokio::spawn(async move {
                let mut lines = BufReader::new(stdout).lines();
                while let Ok(Some(line)) = lines.next_line().await {
                    // Forward only the exact structured schema, never arbitrary child output.
                    if let Ok(record) = serde_json::from_str::<serde_json::Value>(&line) {
                        if record.as_object().is_some_and(|o| {
                            o.keys().all(|key| {
                                ["timestamp", "level", "component", "event", "trace_id"]
                                    .contains(&key.as_str())
                            })
                        }) {
                            println!("{record}");
                        }
                    }
                }
            });
        }
        self.child = Some(child);
        let deadline = tokio::time::Instant::now() + config.startup_timeout;
        loop {
            if self
                .child
                .as_mut()
                .unwrap()
                .try_wait()
                .map_err(|_| "core_wait_failed")?
                .is_some()
            {
                return Err("core_exited_before_ready");
            }
            if let Ok(bytes) = tokio::fs::read(runtime.join("ready.json")).await {
                let ready: ReadyRecord =
                    serde_json::from_slice(&bytes).map_err(|_| "ready_record_invalid")?;
                let url =
                    reqwest::Url::parse(&ready.endpoint).map_err(|_| "ready_endpoint_invalid")?;
                if ready.instance_nonce != nonce
                    || (ready.pid != pid && ready.launcher_pid != pid)
                    || ready.api_protocol != api.api_protocol
                    || ready.core_version.is_empty()
                    || Uuid::parse_str(&ready.generation).is_err()
                    || url.scheme() != "http"
                    || url.host_str() != Some(api.loopback_host.as_str())
                    || url.port().is_none_or(|port| port == 0)
                    || !url.username().is_empty()
                    || url.password().is_some()
                    || url.path() != "/"
                    || url.query().is_some()
                    || url.fragment().is_some()
                {
                    return Err("ready_contract_mismatch");
                }
                let message = format!("{}:{}:{}", api.session_derivation, nonce, ready.generation);
                let mut mac =
                    Hmac::<Sha256>::new_from_slice(secret.as_bytes()).expect("hmac_key_invalid");
                mac.update(message.as_bytes());
                let token = mac
                    .finalize()
                    .into_bytes()
                    .iter()
                    .map(|byte| format!("{byte:02x}"))
                    .collect();
                self.session = Some(CoreConnection {
                    endpoint: ready.endpoint,
                    token,
                    generation: ready.generation,
                });
                self.authenticated_health().await?;
                self.state = SupervisorState::Ready;
                event("supervisor_ready");
                return Ok(());
            }
            if tokio::time::Instant::now() >= deadline {
                return Err("core_ready_timeout");
            }
            tokio::time::sleep(Duration::from_millis(40)).await;
        }
    }

    pub async fn authenticated_health(&mut self) -> Result<Health, &'static str> {
        let session = self.session.as_ref().ok_or("core_session_missing")?;
        let response = self
            .http
            .get(format!("{}/system/health", session.endpoint))
            .bearer_auth(&session.token)
            .send()
            .await
            .map_err(|_| "core_health_failed");
        let result = match response {
            Ok(response) if response.status().is_success() => response
                .json::<Health>()
                .await
                .map_err(|_| "core_health_invalid"),
            _ => Err("core_health_failed"),
        };
        match result {
            Ok(health)
                if health.ready
                    && health.generation == session.generation
                    && health.api_protocol == contract().api_protocol
                    && !health.core_version.is_empty() =>
            {
                Ok(health)
            }
            _ => {
                self.state = SupervisorState::Degraded;
                Err("core_health_contract_failed")
            }
        }
    }

    pub async fn restart(&mut self, config: &LaunchConfig) -> Result<(), &'static str> {
        self.stop(Duration::from_secs(3)).await?;
        self.state = SupervisorState::Restarting;
        event("supervisor_restarting");
        self.start(config).await
    }

    pub async fn stop(&mut self, grace: Duration) -> Result<StopReport, &'static str> {
        self.state = SupervisorState::Stopping;
        event("supervisor_stopping");
        if let Some(session) = self.session.as_ref() {
            let _ = self
                .http
                .post(format!("{}/system/shutdown", session.endpoint))
                .bearer_auth(&session.token)
                .header("X-Request-Id", Uuid::new_v4().to_string())
                .send()
                .await;
        }
        let mut graceful = true;
        if let Some(mut child) = self.child.take() {
            let deadline = tokio::time::Instant::now() + grace;
            loop {
                if child.try_wait().map_err(|_| "core_wait_failed")?.is_some() {
                    break;
                }
                if tokio::time::Instant::now() >= deadline {
                    graceful = false;
                    // Windows venv python.exe may be a redirector with a child
                    // interpreter. Terminate the owned tree, not just its launcher.
                    #[cfg(windows)]
                    {
                        if let Some(pid) = child.id() {
                            let system_root =
                                std::env::var_os("SystemRoot").ok_or("system_root_missing")?;
                            let mut terminate = Command::new(
                                PathBuf::from(system_root).join("System32/taskkill.exe"),
                            );
                            terminate
                                .args(["/PID", &pid.to_string(), "/T", "/F"])
                                .creation_flags(0x08000000)
                                .stdout(Stdio::null())
                                .stderr(Stdio::null());
                            let result = terminate
                                .status()
                                .await
                                .map_err(|_| "core_tree_terminate_failed")?;
                            if !result.success()
                                && child.try_wait().map_err(|_| "core_wait_failed")?.is_none()
                            {
                                return Err("core_tree_terminate_failed");
                            }
                        }
                    }
                    #[cfg(not(windows))]
                    child.kill().await.map_err(|_| "core_terminate_failed")?;
                    child.wait().await.map_err(|_| "core_wait_failed")?;
                    event("supervisor_forced_termination");
                    break;
                }
                tokio::time::sleep(Duration::from_millis(40)).await;
            }
        }
        self.session = None;
        if let Some(runtime) = self.runtime_dir.take() {
            for name in ["bootstrap.json", "ready.json", "ready.tmp"] {
                let _ = tokio::fs::remove_file(runtime.join(name)).await;
            }
            let _ = tokio::fs::remove_dir(runtime).await;
        }
        event(if graceful {
            "supervisor_stopped_gracefully"
        } else {
            "supervisor_stopped_forced"
        });
        Ok(StopReport { graceful })
    }
}
