use crate::{supervisor, SharedSupervisor};
use serde::Deserialize;
use std::{path::PathBuf, time::Duration};
use tauri::State;
use tauri_plugin_dialog::DialogExt;
use tokio::io::AsyncWriteExt;
use uuid::Uuid;

#[derive(Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum ExportRequest {
    Content {
        world_id: Uuid,
        item_id: Uuid,
        format: String,
        content_id: Uuid,
        reviewed_hash: String,
        expected_digest: String,
        use_regex: bool,
    },
    Chat {
        world_id: Uuid,
        item_id: Uuid,
        format: String,
        player_id: Uuid,
        expected_digest: String,
        through_position: u64,
    },
}

impl ExportRequest {
    fn query(self) -> Result<(String, Vec<(String, String)>, &'static str), String> {
        fn digest(value: &str) -> bool {
            value.len() == 64
                && value
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
        }
        match self {
            Self::Content {
                world_id,
                item_id,
                format,
                content_id,
                reviewed_hash,
                expected_digest,
                use_regex,
            } if [
                "character_card_v2",
                "character_card_v3",
                "sillytavern_world_info",
            ]
            .contains(&format.as_str())
                && digest(&reviewed_hash)
                && digest(&expected_digest) =>
            {
                Ok((
                    format!("/worlds/{world_id}/content/{item_id}/export"),
                    vec![
                        ("format".into(), format),
                        ("content_id".into(), content_id.to_string()),
                        ("reviewed_hash".into(), reviewed_hash),
                        ("expected_digest".into(), expected_digest),
                        ("use_regex".into(), use_regex.to_string()),
                    ],
                    "json",
                ))
            }
            Self::Chat {
                world_id,
                item_id,
                format,
                player_id,
                expected_digest,
                through_position,
            } if ["json", "txt"].contains(&format.as_str())
                && digest(&expected_digest)
                && through_position <= i64::MAX as u64 =>
            {
                let extension = if format == "txt" { "txt" } else { "json" };
                Ok((
                    format!("/worlds/{world_id}/conversations/{item_id}/export"),
                    vec![
                        ("format".into(), format),
                        ("player_id".into(), player_id.to_string()),
                        ("expected_digest".into(), expected_digest),
                        ("through_position".into(), through_position.to_string()),
                    ],
                    extension,
                ))
            }
            _ => Err("export_request_invalid".into()),
        }
    }
}

struct PartialExport(PathBuf);
impl Drop for PartialExport {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
    }
}

#[tauri::command]
pub async fn save_file_export(
    request: ExportRequest,
    filename: String,
    app: tauri::AppHandle,
    supervisor: State<'_, SharedSupervisor>,
) -> Result<Option<String>, String> {
    let (path, query, extension) = request.query()?;
    if filename.is_empty()
        || filename.len() > 512
        || filename
            .chars()
            .any(|c| c.is_control() || "<>:\"/\\|?*".contains(c))
        || !filename.ends_with(&format!(".{extension}"))
    {
        return Err("export_filename_invalid".into());
    }
    let connection = supervisor
        .lock()
        .await
        .connection()
        .map_err(str::to_owned)?;
    let dialog = app
        .dialog()
        .file()
        .set_title("保存 dreamtalk 导出文件")
        .set_file_name(&filename)
        .add_filter("导出文件", &[extension]);
    let destination = tauri::async_runtime::spawn_blocking(move || dialog.blocking_save_file())
        .await
        .map_err(|_| "export_dialog_failed")?;
    let Some(destination) = destination else {
        return Ok(None);
    };
    let mut destination = destination
        .into_path()
        .map_err(|_| "export_destination_invalid")?;
    if !destination.is_absolute() || destination.file_name().is_none() {
        return Err("export_destination_invalid".into());
    }
    if destination.extension().and_then(|ext| ext.to_str()) != Some(extension) {
        // Preserve an explicitly chosen suffix; never overwrite another file
        // by silently changing it to an already-existing path.
        return Err("export_extension_invalid".into());
    }
    let current = supervisor
        .lock()
        .await
        .connection()
        .map_err(str::to_owned)?;
    if current.generation != connection.generation {
        return Err("export_core_changed".into());
    }
    let http = reqwest::Client::builder()
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(4))
        .build()
        .map_err(|_| "export_download_failed")?;
    let url = format!(
        "{}/api/v{}{path}",
        connection.endpoint,
        supervisor::contract().api_protocol
    );
    let mut response = tokio::time::timeout(
        Duration::from_secs(20),
        http.get(url)
            .query(&query)
            .bearer_auth(connection.bearer_token())
            .send(),
    )
    .await
    .map_err(|_| "export_download_timeout")?
    .map_err(|_| "export_download_failed")?;
    if !response.status().is_success() {
        return Err(if response.status().as_u16() == 409 {
            "export_snapshot_changed"
        } else if response.status().as_u16() == 404 {
            "export_unavailable"
        } else {
            "export_download_failed"
        }
        .into());
    }
    let temporary_path = destination
        .parent()
        .ok_or("export_destination_invalid")?
        .join(format!(".dreamtalk-export-{}.part", Uuid::new_v4()));
    let file = tokio::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temporary_path)
        .await
        .map_err(|_| "export_write_failed")?;
    let temporary = PartialExport(temporary_path);
    let mut file = file;
    loop {
        let chunk = tokio::time::timeout(Duration::from_secs(20), response.chunk())
            .await
            .map_err(|_| "export_download_timeout")?
            .map_err(|_| "export_download_failed")?;
        let Some(chunk) = chunk else {
            break;
        };
        file.write_all(&chunk)
            .await
            .map_err(|_| "export_write_failed")?;
    }
    file.sync_all().await.map_err(|_| "export_write_failed")?;
    drop(file);
    tokio::fs::rename(&temporary.0, &destination)
        .await
        .map_err(|_| "export_write_failed")?;
    Ok(Some(
        std::mem::take(&mut destination)
            .to_string_lossy()
            .into_owned(),
    ))
}
