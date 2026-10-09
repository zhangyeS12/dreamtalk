//! Signed, user-initiated Windows upgrades. Never exposes arbitrary URLs or paths to JS.
use crate::{supervisor::LaunchConfig, SharedSupervisor};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    path::{Component, Path, PathBuf},
    sync::atomic::{AtomicBool, Ordering},
    time::Duration,
};
use tauri::{Emitter, State};
use tauri_plugin_autostart::ManagerExt;
use tauri_plugin_updater::{Update, UpdaterExt};
use tokio::sync::Mutex;

const IDENTITY: &str = "app.livingworld.desktop";
const MAX_PACKAGE: u64 = 512 * 1024 * 1024;

#[derive(Clone, Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Preferences {
    suppress_popup: bool,
}

#[derive(Clone, Serialize)]
pub struct ReleaseInfo {
    version: String,
    notes: String,
    date: Option<String>,
}

#[derive(Serialize)]
pub struct UpdateStatus {
    current_version: String,
    suppress_popup: bool,
    signing_ready: bool,
    installed: bool,
    release: Option<ReleaseInfo>,
    cleanup_notice: Option<String>,
}

#[derive(Clone, Serialize)]
struct Progress {
    phase: &'static str,
    downloaded: u64,
    total: Option<u64>,
}

pub struct UpdateState {
    directory: PathBuf,
    preferences: Mutex<Preferences>,
    pub(crate) operation: Mutex<()>,
    checking: Mutex<()>,
    prompted: AtomicBool,
    pending: Mutex<Option<Update>>,
    cleanup_notice: Mutex<Option<String>>,
}

impl UpdateState {
    pub fn load(app_data: &Path) -> Self {
        let preferences = std::fs::read(app_data.join("config/desktop-updates.json"))
            .ok()
            .and_then(|bytes| serde_json::from_slice(&bytes).ok())
            .unwrap_or_default();
        Self {
            directory: app_data.to_owned(),
            preferences: Mutex::new(preferences),
            operation: Mutex::new(()),
            checking: Mutex::new(()),
            prompted: AtomicBool::new(false),
            pending: Mutex::new(None),
            cleanup_notice: Mutex::new(None),
        }
    }
    pub fn busy(&self) -> bool {
        self.operation.try_lock().is_err()
    }
}

fn signing_ready(app: &tauri::AppHandle) -> bool {
    app.config()
        .plugins
        .0
        .get("updater")
        .and_then(|v| v.get("pubkey"))
        .and_then(|v| v.as_str())
        .is_some_and(|v| !v.is_empty())
}
fn executable_root() -> Result<PathBuf, String> {
    std::env::current_exe()
        .map_err(|_| "update_executable_unknown".to_owned())?
        .parent()
        .map(Path::to_owned)
        .ok_or_else(|| "update_executable_unknown".to_owned())
}
fn release(update: &Update) -> ReleaseInfo {
    ReleaseInfo {
        version: update.version.clone(),
        notes: update
            .body
            .clone()
            .unwrap_or_default()
            .chars()
            .take(32_000)
            .collect(),
        date: update.date.map(|v| v.to_string()),
    }
}
fn progress(app: &tauri::AppHandle, phase: &'static str, downloaded: u64, total: Option<u64>) {
    let _ = app.emit(
        "desktop-update-progress",
        Progress {
            phase,
            downloaded,
            total,
        },
    );
}
fn atomic_json<T: Serialize>(path: &Path, value: &T) -> Result<(), String> {
    std::fs::create_dir_all(path.parent().ok_or("update_path_invalid")?)
        .map_err(|_| "update_preferences_failed")?;
    let temporary = path.with_extension("tmp");
    std::fs::write(
        &temporary,
        serde_json::to_vec_pretty(value).map_err(|_| "update_record_failed")?,
    )
    .map_err(|_| "update_record_failed")?;
    std::fs::rename(temporary, path).map_err(|_| "update_record_failed".to_owned())
}

#[tauri::command]
pub async fn desktop_update_status(
    app: tauri::AppHandle,
    state: State<'_, UpdateState>,
) -> Result<UpdateStatus, String> {
    let root = executable_root()?;
    Ok(UpdateStatus {
        current_version: app.package_info().version.to_string(),
        suppress_popup: state.preferences.lock().await.suppress_popup,
        signing_ready: signing_ready(&app),
        installed: root.join(".dreamtalk-installed").is_file(),
        release: state.pending.lock().await.as_ref().map(release),
        cleanup_notice: state.cleanup_notice.lock().await.clone(),
    })
}

#[tauri::command]
pub async fn configure_desktop_updates(
    suppress_popup: bool,
    state: State<'_, UpdateState>,
) -> Result<(), String> {
    let mut preferences = state.preferences.lock().await;
    let replacement = Preferences { suppress_popup };
    atomic_json(
        &state.directory.join("config/desktop-updates.json"),
        &replacement,
    )?;
    *preferences = replacement;
    Ok(())
}

#[tauri::command]
pub async fn check_desktop_update(
    app: tauri::AppHandle,
    state: State<'_, UpdateState>,
) -> Result<Option<ReleaseInfo>, String> {
    let _checking = state.checking.try_lock().map_err(|_| "update_busy")?;
    if state.busy() {
        return Err("update_busy".to_owned());
    }
    if !signing_ready(&app) {
        return Err("update_signing_not_configured".to_owned());
    }
    let updater = app
        .updater_builder()
        .timeout(Duration::from_secs(20))
        .restart_after_install(false)
        .build()
        .map_err(|_| "update_configuration_invalid")?;
    let result = tokio::time::timeout(Duration::from_secs(30), updater.check())
        .await
        .map_err(|_| "update_check_timeout")?
        .map_err(|_| "update_check_failed")?;
    if let Some(update) = result.as_ref() {
        // Keep downloads within this project's GitHub release namespace. The plugin
        // enforces HTTPS and verifies the installer against the embedded public key.
        let url = &update.download_url;
        let expected = format!(
            "/zhangyeS12/dreamtalk/releases/download/v{}/dreamtalk_{}_x64-setup.exe",
            update.version, update.version
        );
        if url.scheme() != "https"
            || url.host_str() != Some("github.com")
            || url.path() != expected
            || !url.username().is_empty()
            || url.password().is_some()
        {
            return Err("update_download_source_invalid".to_owned());
        }
    }
    let info = result.as_ref().map(release);
    *state.pending.lock().await = result;
    Ok(info)
}

#[tauri::command]
pub async fn claim_desktop_update_popup(
    app: tauri::AppHandle,
    state: State<'_, UpdateState>,
) -> Result<bool, String> {
    if state.preferences.lock().await.suppress_popup || state.pending.lock().await.is_none() {
        return Ok(false);
    }
    use tauri::Manager;
    if !app
        .get_webview_window("main")
        .is_some_and(|window| window.is_visible().unwrap_or(false))
    {
        return Ok(false);
    }
    Ok(state
        .prompted
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .is_ok())
}

#[tauri::command]
pub fn dismiss_desktop_update_popup(state: State<'_, UpdateState>) {
    state.prompted.store(true, Ordering::SeqCst);
}

#[derive(Deserialize)]
pub(crate) struct DrainStatus {
    pub preparing: bool,
    pub active: u64,
}

pub(crate) async fn maintenance(
    connection: &crate::supervisor::CoreConnection,
    action: &str,
) -> Result<DrainStatus, String> {
    let http = reqwest::Client::builder()
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(4))
        .build()
        .map_err(|_| "update_core_unavailable")?;
    let url = format!("{}/system/update/{action}", connection.endpoint);
    let request = if action == "status" {
        http.get(url)
    } else {
        http.post(url)
    };
    request
        .bearer_auth(connection.bearer_token())
        .send()
        .await
        .map_err(|_| "update_core_unavailable")?
        .error_for_status()
        .map_err(|_| "update_core_unavailable")?
        .json()
        .await
        .map_err(|_| "update_core_unavailable".to_owned())
}

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct PackageManifest {
    identity: String,
    version: String,
    files: BTreeMap<String, String>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Handoff {
    identity: String,
    version: String,
    old_root: PathBuf,
    old_package: PackageManifest,
    autostart: bool,
    recovery: PathBuf,
    installer: PathBuf,
}

fn is_link(metadata: &std::fs::Metadata) -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        metadata.file_attributes() & 0x400 != 0
    }
    #[cfg(not(windows))]
    {
        metadata.file_type().is_symlink()
    }
}

fn owned_file(root: &Path, relative: &str) -> Result<PathBuf, String> {
    let relative_path = Path::new(relative);
    if relative_path
        .components()
        .any(|part| !matches!(part, Component::Normal(_)))
        || relative.is_empty()
    {
        return Err("update_package_manifest_invalid".to_owned());
    }
    let mut ancestor = Some(root);
    while let Some(directory) = ancestor {
        if std::fs::symlink_metadata(directory).is_ok_and(|meta| is_link(&meta)) {
            return Err("update_package_symlink_rejected".to_owned());
        }
        ancestor = directory.parent();
    }
    let mut path = root.to_owned();
    for part in relative_path.components() {
        path.push(part.as_os_str());
        if std::fs::symlink_metadata(&path).is_ok_and(|meta| is_link(&meta)) {
            return Err("update_package_symlink_rejected".to_owned());
        }
    }
    Ok(path)
}
fn digest(path: &Path) -> Result<String, String> {
    use std::io::Read;
    let mut file = std::fs::File::open(path).map_err(|_| "update_package_read_failed")?;
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let size = file
            .read(&mut buffer)
            .map_err(|_| "update_package_read_failed")?;
        if size == 0 {
            break;
        }
        hash.update(&buffer[..size]);
    }
    Ok(format!("{:x}", hash.finalize()))
}
fn package_manifest(root: &Path) -> Result<PackageManifest, String> {
    if root.join(".git").exists() || root.parent().is_none() {
        return Err("update_package_root_invalid".to_owned());
    }
    let manifest: PackageManifest = serde_json::from_slice(
        &std::fs::read(root.join(".dreamtalk-package.json"))
            .map_err(|_| "update_package_manifest_missing")?,
    )
    .map_err(|_| "update_package_manifest_invalid")?;
    if manifest.identity != IDENTITY
        || manifest.files.len() > 10_000
        || !manifest.files.contains_key("dreamtalk-desktop.exe")
        || !manifest.files.contains_key("core/dreamtalk-core.exe")
    {
        return Err("update_package_manifest_invalid".to_owned());
    }
    for (relative, expected) in &manifest.files {
        if digest(&owned_file(root, relative)?)? != *expected {
            return Err("update_package_modified".to_owned());
        }
    }
    Ok(manifest)
}
fn copy_tree(source: &Path, target: &Path) -> Result<(), String> {
    if !source.exists() {
        return Ok(());
    }
    let metadata = std::fs::symlink_metadata(source).map_err(|_| "update_backup_failed")?;
    if is_link(&metadata) {
        return Err("update_backup_symlink_rejected".to_owned());
    }
    if metadata.is_file() {
        std::fs::create_dir_all(target.parent().ok_or("update_path_invalid")?)
            .map_err(|_| "update_backup_failed")?;
        std::fs::copy(source, target).map_err(|_| "update_backup_failed")?;
    } else {
        std::fs::create_dir_all(target).map_err(|_| "update_backup_failed")?;
        for entry in std::fs::read_dir(source).map_err(|_| "update_backup_failed")? {
            let entry = entry.map_err(|_| "update_backup_failed")?;
            if entry.file_name() == "cache" {
                continue;
            } // Rebuildable search caches are not saves.
            copy_tree(&entry.path(), &target.join(entry.file_name()))?;
        }
    }
    Ok(())
}
fn make_backup(
    directory: &Path,
    root: &Path,
    manifest: &PackageManifest,
) -> Result<PathBuf, String> {
    let recovery = directory
        .join("updates/recovery")
        .join(uuid::Uuid::new_v4().to_string());
    std::fs::create_dir_all(&recovery).map_err(|_| "update_backup_failed")?;
    let result = (|| {
        copy_tree(&directory.join("data"), &recovery.join("data"))?;
        copy_tree(&directory.join("config"), &recovery.join("config"))?;
        for relative in manifest.files.keys() {
            let target = owned_file(&recovery.join("program"), relative)?;
            copy_tree(&owned_file(root, relative)?, &target)?;
        }
        atomic_json(&recovery.join("program/.dreamtalk-package.json"), manifest)?;
        atomic_json(&recovery.join(".dreamtalk-recovery.json"), manifest)?;
        let snapshot = PackageManifest {
            identity: IDENTITY.to_owned(),
            version: manifest.version.clone(),
            files: inventory(&recovery)?,
        };
        atomic_json(&recovery.join(".dreamtalk-snapshot.json"), &snapshot)?;
        Ok(recovery.clone())
    })();
    if result.is_err() {
        if let Ok(files) = inventory(&recovery) {
            let partial = PackageManifest {
                identity: IDENTITY.to_owned(),
                version: manifest.version.clone(),
                files,
            };
            let _ = remove_owned_files(&recovery, &partial);
            let _ = std::fs::remove_dir(&recovery);
        }
    }
    result
}

fn inventory(root: &Path) -> Result<BTreeMap<String, String>, String> {
    fn visit(
        root: &Path,
        folder: &Path,
        files: &mut BTreeMap<String, String>,
    ) -> Result<(), String> {
        for entry in std::fs::read_dir(folder).map_err(|_| "update_backup_failed")? {
            let entry = entry.map_err(|_| "update_backup_failed")?;
            let path = entry.path();
            let metadata = std::fs::symlink_metadata(&path).map_err(|_| "update_backup_failed")?;
            if is_link(&metadata) {
                return Err("update_backup_symlink_rejected".to_owned());
            }
            if metadata.is_dir() {
                visit(root, &path, files)?;
            } else {
                files.insert(
                    path.strip_prefix(root)
                        .map_err(|_| "update_path_invalid")?
                        .to_string_lossy()
                        .replace('\\', "/"),
                    digest(&path)?,
                );
            }
        }
        Ok(())
    }
    let mut files = BTreeMap::new();
    visit(root, root, &mut files)?;
    Ok(files)
}

fn prune_recovery(directory: &Path, keep: &Path) -> Result<(), String> {
    let base = directory.join("updates/recovery");
    for entry in std::fs::read_dir(&base).map_err(|_| "update_cleanup_failed")? {
        let path = entry.map_err(|_| "update_cleanup_failed")?.path();
        if path == keep
            || !path.is_dir()
            || uuid::Uuid::parse_str(&path.file_name().unwrap_or_default().to_string_lossy())
                .is_err()
        {
            continue;
        }
        let marker = owned_file(&path, ".dreamtalk-snapshot.json")?;
        if !marker.exists() {
            continue;
        }
        let snapshot: PackageManifest =
            serde_json::from_slice(&std::fs::read(&marker).map_err(|_| "update_cleanup_failed")?)
                .map_err(|_| "update_cleanup_failed")?;
        if snapshot.identity != IDENTITY {
            continue;
        }
        remove_owned_files(&path, &snapshot)?;
        std::fs::remove_file(marker).map_err(|_| "update_cleanup_failed")?;
        // Never recursively remove unknown or locally added files.
        let _ = std::fs::remove_dir(path);
    }
    Ok(())
}

#[tauri::command]
pub async fn install_desktop_update(
    version: String,
    app: tauri::AppHandle,
    state: State<'_, UpdateState>,
    supervisor: State<'_, SharedSupervisor>,
    config: State<'_, LaunchConfig>,
) -> Result<(), String> {
    let _operation = state.operation.try_lock().map_err(|_| "update_busy")?;
    let update = state
        .pending
        .lock()
        .await
        .clone()
        .ok_or("update_not_available")?;
    if update.version != version {
        return Err("update_version_changed".to_owned());
    }
    if state.directory.join("updates/handoff.json").exists() {
        return Err("update_recovery_pending".to_owned());
    }
    let root = executable_root()?;
    let manifest = package_manifest(&root)?;
    let autostart = app
        .autolaunch()
        .is_enabled()
        .map_err(|_| "update_autostart_status_failed")?;
    progress(&app, "downloading", 0, None);
    let oversize = tokio::sync::Notify::new();
    let mut downloaded = 0u64;
    let mut last_progress = std::time::Instant::now() - Duration::from_secs(1);
    let download = update.download(
        |chunk, total| {
            downloaded = downloaded.saturating_add(chunk as u64);
            if downloaded > MAX_PACKAGE || total.is_some_and(|size| size > MAX_PACKAGE) {
                oversize.notify_one();
            }
            if last_progress.elapsed() >= Duration::from_millis(100) {
                progress(&app, "downloading", downloaded, total);
                last_progress = std::time::Instant::now();
            }
        },
        || {},
    );
    let bytes = tokio::select! {
        biased;
        _ = oversize.notified() => return Err("update_package_too_large".to_owned()),
        result = tokio::time::timeout(Duration::from_secs(600), download) =>
            result.map_err(|_| "update_download_timeout")?.map_err(|_| "update_download_or_signature_failed")?,
    };
    if bytes.len() as u64 > MAX_PACKAGE {
        return Err("update_package_too_large".to_owned());
    }
    progress(&app, "waiting", 0, None);
    let mut host = supervisor.lock().await;
    let connection = host.connection().map_err(str::to_owned)?;
    if let Err(error) = maintenance(&connection, "prepare").await {
        let _ = maintenance(&connection, "cancel").await;
        return Err(error);
    }
    let drain = async {
        let deadline = tokio::time::Instant::now() + Duration::from_secs(180);
        loop {
            let status = maintenance(&connection, "status").await?;
            if !status.preparing {
                return Err("update_barrier_expired".to_owned());
            }
            if status.active == 0 {
                return Ok(());
            }
            if tokio::time::Instant::now() >= deadline {
                return Err("update_tasks_still_running".to_owned());
            }
            tokio::time::sleep(Duration::from_millis(500)).await;
        }
    }
    .await;
    if let Err(error) = drain {
        let _ = maintenance(&connection, "cancel").await;
        return Err(error);
    }
    progress(&app, "preparing", 0, None);
    // Refuse forced termination for upgrades. Existing shutdown behavior stays intact.
    if let Err(error) = host.stop_for_update(Duration::from_secs(30)).await {
        let _ = maintenance(&connection, "cancel").await;
        return Err(error.to_owned());
    }
    let directory = state.directory.clone();
    let backup_root = root.clone();
    let backup_manifest = manifest.clone();
    let backup = tauri::async_runtime::spawn_blocking(move || {
        make_backup(&directory, &backup_root, &backup_manifest)
    })
    .await;
    let recovery = match backup {
        Ok(Ok(path)) => path,
        _ => {
            let _ = host.start(&config).await;
            return Err("update_backup_failed".to_owned());
        }
    };
    let installer_root = state
        .directory
        .join("updates/installers")
        .join(uuid::Uuid::new_v4().to_string());
    let installer = match owned_file(&installer_root, "installer.exe") {
        Ok(path) => path,
        Err(_) => {
            let _ = host.start(&config).await;
            return Err("update_installer_failed".to_owned());
        }
    };
    let save = (|| {
        use std::io::Write;
        std::fs::create_dir_all(&installer_root).map_err(|_| "update_installer_failed")?;
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&installer)
            .map_err(|_| "update_installer_failed")?;
        file.write_all(&bytes)
            .map_err(|_| "update_installer_failed")?;
        file.sync_all().map_err(|_| "update_installer_failed")?;
        Ok::<_, String>(())
    })();
    if save.is_err() {
        let _ = std::fs::remove_file(&installer);
        let _ = std::fs::remove_dir(&installer_root);
        let _ = host.start(&config).await;
        return Err("update_installer_failed".to_owned());
    }
    drop(bytes);
    let handoff = Handoff {
        identity: IDENTITY.to_owned(),
        version,
        old_root: root,
        old_package: manifest,
        autostart,
        recovery,
        installer: installer.clone(),
    };
    if atomic_json(&state.directory.join("updates/handoff.json"), &handoff).is_err() {
        let _ = std::fs::remove_file(&installer);
        let _ = std::fs::remove_dir(&installer_root);
        let _ = host.start(&config).await;
        return Err("update_handoff_failed".to_owned());
    }
    progress(&app, "installing", 0, None);
    // Reuse the official updater's verified NSIS payload, but own its on-disk
    // lifecycle. This avoids the plugin's unmanaged Windows temporary EXE and
    // abrupt process::exit path. The same passive/update flags go to standard NSIS.
    let mut command = tokio::process::Command::new(&installer);
    #[cfg(windows)]
    command.creation_flags(0x08000000);
    match command.args(["/P", "/UPDATE"]).spawn() {
        Ok(_child) => {
            drop(host);
            app.exit(0);
            Ok(())
        }
        Err(_) => {
            let _ = std::fs::remove_file(state.directory.join("updates/handoff.json"));
            let _ = std::fs::remove_file(&installer);
            let _ = std::fs::remove_dir(&installer_root);
            if host.start(&config).await.is_ok() {
                let _ = remove_owned_files(&handoff.recovery.join("program"), &handoff.old_package);
                let _ =
                    std::fs::remove_file(handoff.recovery.join("program/.dreamtalk-package.json"));
                let _ = std::fs::remove_dir(handoff.recovery.join("program"));
            }
            Err("update_installer_failed".to_owned())
        }
    }
}

fn remove_owned_files(root: &Path, manifest: &PackageManifest) -> Result<(), String> {
    let mut folders = Vec::new();
    for (relative, expected) in &manifest.files {
        let path = owned_file(root, relative)?;
        if !path.exists() {
            continue;
        }
        if digest(&path)? != *expected {
            return Err("update_cleanup_modified_file".to_owned());
        }
        std::fs::remove_file(&path).map_err(|_| "update_cleanup_failed")?;
        let mut parent = path.parent();
        while let Some(folder) = parent {
            if folder == root {
                break;
            }
            folders.push(folder.to_owned());
            parent = folder.parent();
        }
    }
    folders.sort_by_key(|v| std::cmp::Reverse(v.components().count()));
    folders.dedup();
    for folder in folders {
        let _ = std::fs::remove_dir(folder);
    }
    Ok(())
}

#[tauri::command]
pub async fn acknowledge_desktop_update(
    app: tauri::AppHandle,
    state: State<'_, UpdateState>,
    supervisor: State<'_, SharedSupervisor>,
) -> Result<Option<String>, String> {
    let _operation = state.operation.try_lock().map_err(|_| "update_busy")?;
    supervisor
        .lock()
        .await
        .connection()
        .map_err(str::to_owned)?;
    let root = executable_root()?;
    if !root.join(".dreamtalk-installed").is_file() {
        return Ok(None);
    }
    let path = state.directory.join("updates/handoff.json");
    if !path.exists() {
        return Ok(None);
    }
    let handoff: Handoff =
        serde_json::from_slice(&std::fs::read(&path).map_err(|_| "update_handoff_invalid")?)
            .map_err(|_| "update_handoff_invalid")?;
    if handoff.identity != IDENTITY
        || handoff.version != app.package_info().version.to_string()
        || handoff.old_package.identity != IDENTITY
        || handoff.recovery.parent() != Some(state.directory.join("updates/recovery").as_path())
        || uuid::Uuid::parse_str(
            &handoff
                .recovery
                .file_name()
                .unwrap_or_default()
                .to_string_lossy(),
        )
        .is_err()
    {
        return Err("update_handoff_invalid".to_owned());
    }
    let result = async {
        let installer_base = state.directory.join("updates/installers");
        let installer_parent = handoff.installer.parent().ok_or("update_handoff_invalid")?;
        if installer_parent.parent() != Some(installer_base.as_path())
            || handoff.installer.file_name() != Some(std::ffi::OsStr::new("installer.exe"))
        {
            return Err("update_handoff_invalid".to_owned());
        }
        let installer = owned_file(installer_parent, "installer.exe")?;
        if installer.exists() {
            std::fs::remove_file(installer).map_err(|_| "update_installer_still_running")?;
        }
        let _ = std::fs::remove_dir(installer_parent);
        if handoff.autostart {
            app.autolaunch()
                .enable()
                .map_err(|_| "update_autostart_failed")?;
        }
        migrate_shortcuts(&handoff.old_root, &root).await?;
        let old_root = handoff.old_root.clone();
        let current_root = root.clone();
        let recovery = handoff.recovery.clone();
        let manifest = handoff.old_package.clone();
        let directory = state.directory.clone();
        tauri::async_runtime::spawn_blocking(move || {
            if old_root != current_root {
                // Revalidate the package marker/root before removing a portable origin.
                let marker = old_root.join(".dreamtalk-package.json");
                if marker.exists() {
                    let recorded: PackageManifest = serde_json::from_slice(
                        &std::fs::read(&marker).map_err(|_| "update_cleanup_package_changed")?,
                    )
                    .map_err(|_| "update_cleanup_package_changed")?;
                    if recorded != manifest || old_root.join(".git").exists() {
                        return Err("update_cleanup_package_changed".to_owned());
                    }
                    remove_owned_files(&old_root, &manifest)?;
                    std::fs::remove_file(old_root.join(".dreamtalk-package.json"))
                        .map_err(|_| "update_cleanup_failed")?;
                } else if manifest.files.keys().any(|relative| {
                    owned_file(&old_root, relative).map_or(true, |path| path.exists())
                }) {
                    return Err("update_cleanup_package_changed".to_owned());
                }
                let _ = std::fs::remove_dir(&old_root);
            } else {
                let current = package_manifest(&current_root)?;
                let mut obsolete = manifest.clone();
                obsolete
                    .files
                    .retain(|relative, _| !current.files.contains_key(relative));
                remove_owned_files(&current_root, &obsolete)?;
            }
            remove_owned_files(&recovery.join("program"), &manifest)?;
            let _ = std::fs::remove_file(recovery.join("program/.dreamtalk-package.json"));
            let _ = std::fs::remove_dir(recovery.join("program"));
            prune_recovery(&directory, &recovery)?;
            Ok::<_, String>(())
        })
        .await
        .map_err(|_| "update_cleanup_failed")??;
        std::fs::remove_file(&path).map_err(|_| "update_cleanup_failed")?;
        Ok::<_, String>(())
    }
    .await;
    let notice = result.err();
    *state.cleanup_notice.lock().await = notice.clone();
    Ok(notice)
}

async fn migrate_shortcuts(old_root: &Path, new_root: &Path) -> Result<(), String> {
    let system = std::env::var_os("SystemRoot").ok_or("update_system_root_missing")?;
    let script = r#"
$ErrorActionPreference='Stop'
$shell=New-Object -ComObject WScript.Shell
$old=[IO.Path]::GetFullPath($env:DREAMTALK_UPDATE_OLD)
$new=[IO.Path]::GetFullPath($env:DREAMTALK_UPDATE_NEW)
foreach($folder in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))) {
    if (-not $folder) { continue }
    Get-ChildItem -LiteralPath $folder -Filter '*.lnk' -File | ForEach-Object {
        $link=$shell.CreateShortcut($_.FullName)
        if ($link.TargetPath -and [IO.Path]::GetFullPath($link.TargetPath) -eq $old) {
            $link.TargetPath=$new; $link.WorkingDirectory=[IO.Path]::GetDirectoryName($new); $link.IconLocation=$new; $link.Save()
        }
    }
}
"#;
    let mut command = tokio::process::Command::new(
        PathBuf::from(system).join("System32/WindowsPowerShell/v1.0/powershell.exe"),
    );
    #[cfg(windows)]
    command.creation_flags(0x08000000);
    let status = command
        .args(["-NoProfile", "-NonInteractive", "-Command", script])
        .env(
            "DREAMTALK_UPDATE_OLD",
            old_root.join("dreamtalk-desktop.exe"),
        )
        .env(
            "DREAMTALK_UPDATE_NEW",
            new_root.join("dreamtalk-desktop.exe"),
        )
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .await
        .map_err(|_| "update_shortcuts_failed")?;
    if status.success() {
        Ok(())
    } else {
        Err("update_shortcuts_failed".to_owned())
    }
}
