//! Package integrity, bounded file ownership and recovery inventory. No process launch.
use super::IDENTITY;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    path::{Component, Path, PathBuf},
};

#[derive(Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(super) struct PackageManifest {
    pub(super) identity: String,
    pub(super) version: String,
    pub(super) files: BTreeMap<String, String>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Handoff {
    pub(super) identity: String,
    pub(super) version: String,
    pub(super) old_root: PathBuf,
    pub(super) old_package: Option<PackageManifest>,
    #[serde(default)]
    pub(super) save_snapshot_id: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub(super) prior_snapshot_ids: Vec<String>,
    pub(super) autostart: bool,
    pub(super) recovery: PathBuf,
    pub(super) installer: PathBuf,
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

pub(super) fn owned_file(root: &Path, relative: &str) -> Result<PathBuf, String> {
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
pub(super) fn package_manifest(root: &Path) -> Result<PackageManifest, String> {
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
pub(super) fn make_backup(
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
        std::fs::create_dir_all(recovery.join("config")).map_err(|_| "update_backup_failed")?;
        if directory.join(".dreamtalk-storage.json").is_file() {
            copy_tree(
                &directory.join(".dreamtalk-storage.json"),
                &recovery.join(".dreamtalk-storage.json"),
            )?;
        }
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

pub(super) fn prune_recovery(directory: &Path, keep: &Path) -> Result<(), String> {
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

pub(super) fn remove_owned_files(root: &Path, manifest: &PackageManifest) -> Result<(), String> {
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

pub(super) fn atomic_json<T: Serialize>(path: &Path, value: &T) -> Result<(), String> {
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
