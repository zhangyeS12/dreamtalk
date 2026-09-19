use serde::Deserialize;
use std::{collections::HashSet, path::Path};
use tokio::io::AsyncWriteExt;

use crate::credentials::validate_secret_ref;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Provider {
    provider_id: String,
    adapter_kind: String,
    #[serde(default)]
    base_url: Option<String>,
    secret_ref: String,
    #[serde(default = "default_timeout")]
    timeout_ms: u64,
}

fn default_timeout() -> u64 {
    30_000
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct HostDocument {
    version: u32,
    #[serde(default)]
    providers: Vec<Provider>,
    #[serde(default)]
    models: Vec<serde_json::Value>,
    #[serde(default)]
    routes: Vec<serde_json::Value>,
    #[serde(default)]
    execution_policy: Option<serde_json::Value>,
    #[serde(default)]
    pricing_catalog: Option<serde_json::Value>,
}

pub struct HostLlmConfiguration {
    pub credential_refs: Vec<String>,
}

pub async fn load(path: &Path) -> Result<HostLlmConfiguration, &'static str> {
    if !path.is_absolute() || path.is_symlink() {
        return Err("llm_config_path_invalid");
    }
    if !path.exists() {
        if let Some(parent) = path.parent() {
            tokio::fs::create_dir_all(parent)
                .await
                .map_err(|_| "llm_config_create_failed")?;
        }
        let mut file = tokio::fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(path)
            .await
            .map_err(|_| "llm_config_create_failed")?;
        file.write_all(
            br#"{"version":1,"providers":[],"models":[],"routes":[],"execution_policy":{},"pricing_catalog":{"catalog_id":"empty","source_label":"configured-empty","schedules":[],"aliases":[]}}"#,
        )
        .await
        .map_err(|_| "llm_config_create_failed")?;
        file.sync_all()
            .await
            .map_err(|_| "llm_config_create_failed")?;
    }
    let metadata = tokio::fs::metadata(path)
        .await
        .map_err(|_| "llm_config_read_failed")?;
    if !metadata.is_file() {
        return Err("llm_config_read_failed");
    }
    if metadata.len() > 1_048_576 {
        return Ok(HostLlmConfiguration {
            credential_refs: Vec::new(),
        });
    }
    let bytes = tokio::fs::read(path)
        .await
        .map_err(|_| "llm_config_read_failed")?;
    let document: HostDocument = match serde_json::from_slice(&bytes) {
        Ok(document) => document,
        Err(_) => {
            return Ok(HostLlmConfiguration {
                credential_refs: Vec::new(),
            })
        }
    };
    if document.version != 1 {
        return Ok(HostLlmConfiguration {
            credential_refs: Vec::new(),
        });
    }
    let _ = (
        document.models.len(),
        document.routes.len(),
        document.execution_policy.as_ref(),
        document.pricing_catalog.as_ref(),
    );
    let kinds = [
        "openai-compatible",
        "anthropic",
        "gemini",
        "openai-responses",
    ];
    let mut provider_ids = HashSet::new();
    let mut references = Vec::new();
    for provider in document.providers {
        if provider.provider_id.is_empty()
            || !provider_ids.insert(provider.provider_id)
            || !kinds.contains(&provider.adapter_kind.as_str())
            || validate_secret_ref(&provider.secret_ref).is_err()
            || provider.timeout_ms == 0
            || provider
                .base_url
                .as_ref()
                .is_some_and(|value| value.contains('@'))
        {
            return Ok(HostLlmConfiguration {
                credential_refs: Vec::new(),
            });
        }
        if !references.contains(&provider.secret_ref) {
            references.push(provider.secret_ref);
        }
    }
    Ok(HostLlmConfiguration {
        credential_refs: references,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn malformed_optional_llm_config_does_not_block_world_core_startup() {
        tauri::async_runtime::block_on(async {
            let directory = tempfile::tempdir().unwrap();
            let path = directory.path().join("llm.json");
            std::fs::write(&path, br#"{"version":1,"api_key":"SECRET-CANARY"}"#).unwrap();
            let configuration = load(&path).await.unwrap();
            assert!(configuration.credential_refs.is_empty());
        });
    }

    #[test]
    fn valid_config_returns_only_canonical_secret_refs() {
        tauri::async_runtime::block_on(async {
            let directory = tempfile::tempdir().unwrap();
            let path = directory.path().join("llm.json");
            let reference = "00000000-0000-0000-0000-000000000001";
            std::fs::write(
                &path,
                serde_json::json!({
                    "version": 1,
                    "providers": [{
                        "provider_id": "provider",
                        "adapter_kind": "anthropic",
                        "secret_ref": reference
                    }]
                })
                .to_string(),
            )
            .unwrap();
            assert_eq!(load(&path).await.unwrap().credential_refs, [reference]);
        });
    }
}
