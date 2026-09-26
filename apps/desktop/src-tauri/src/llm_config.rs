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

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ChatModelSetup {
    pub provider_kind: String,
    pub model_id: String,
    pub base_url: Option<String>,
    pub max_billable_input_tokens: u64,
    pub max_output_tokens: u64,
}

pub fn is_empty_configuration(bytes: &[u8]) -> bool {
    let Ok(document) = serde_json::from_slice::<HostDocument>(bytes) else {
        return false;
    };
    document.version == 1
        && document.providers.is_empty()
        && document.models.is_empty()
        && document.routes.is_empty()
        && document
            .execution_policy
            .is_none_or(|value| value == serde_json::json!({}))
        && document.pricing_catalog.is_none_or(|value| {
            value
                == serde_json::json!({
                    "catalog_id": "empty", "source_label": "configured-empty",
                    "schedules": [], "aliases": [],
                })
        })
}

pub fn single_chat_document(
    setup: &ChatModelSetup,
    secret_ref: &str,
) -> Result<Vec<u8>, &'static str> {
    validate_secret_ref(secret_ref).map_err(|_| "invalid_secret_ref")?;
    if setup.model_id.is_empty()
        || setup.model_id.len() > 128
        || setup.model_id.chars().any(char::is_whitespace)
        || setup.model_id.chars().any(char::is_control)
        || !(1..=1_000_000).contains(&setup.max_billable_input_tokens)
        || !(1..=100_000).contains(&setup.max_output_tokens)
    {
        return Err("model_setup_invalid");
    }
    let provider_id = match setup.provider_kind.as_str() {
        "openai-responses" => "openai",
        "anthropic" => "anthropic",
        "gemini" => "gemini",
        "openai-compatible" => "compatible",
        _ => return Err("model_setup_invalid"),
    };
    if setup.provider_kind == "openai-compatible" {
        let base = setup.base_url.as_ref().ok_or("model_setup_invalid")?;
        let url = reqwest::Url::parse(base).map_err(|_| "model_setup_invalid")?;
        if !matches!(url.scheme(), "http" | "https")
            || url.host_str().is_none()
            || (url.scheme() == "http"
                && !matches!(url.host_str(), Some("localhost" | "127.0.0.1" | "[::1]")))
            || !url.username().is_empty()
            || url.password().is_some()
            || url.query().is_some()
            || url.fragment().is_some()
            || base.contains('\\')
            || base.chars().any(char::is_whitespace)
        {
            return Err("model_setup_invalid");
        }
    } else if setup.base_url.is_some() {
        return Err("model_setup_invalid");
    }
    let mut provider = serde_json::json!({
        "provider_id": provider_id,
        "adapter_kind": setup.provider_kind,
        "secret_ref": secret_ref,
        "timeout_ms": 30_000,
    });
    if let Some(base) = setup.base_url.as_ref() {
        provider["base_url"] = serde_json::Value::String(base.clone());
    }
    let document = serde_json::json!({
        "version": 1,
        "providers": [provider],
        "models": [{
            "provider_id": provider_id,
            "model_id": setup.model_id,
            "enabled": true,
            "capabilities": {"text_generation": true},
            "limits": {
                "max_billable_input_tokens": setup.max_billable_input_tokens,
                "max_output_tokens": setup.max_output_tokens,
            },
            "adapter_profile": {},
        }],
        "routes": [],
        "execution_policy": {},
        "pricing_catalog": {
            "catalog_id": "empty", "source_label": "configured-empty",
            "schedules": [], "aliases": [],
        },
    });
    serde_json::to_vec(&document).map_err(|_| "model_setup_invalid")
}

pub async fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), &'static str> {
    if !path.is_absolute() || path.is_symlink() {
        return Err("llm_config_path_invalid");
    }
    let parent = path.parent().ok_or("llm_config_path_invalid")?;
    let temporary = parent.join(format!("llm-{}.tmp", uuid::Uuid::new_v4()));
    let result = async {
        let mut file = tokio::fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&temporary)
            .await
            .map_err(|_| "llm_config_write_failed")?;
        file.write_all(bytes)
            .await
            .map_err(|_| "llm_config_write_failed")?;
        file.sync_all()
            .await
            .map_err(|_| "llm_config_write_failed")?;
        drop(file);
        tokio::fs::rename(&temporary, path)
            .await
            .map_err(|_| "llm_config_write_failed")
    }
    .await;
    if result.is_err() {
        let _ = tokio::fs::remove_file(&temporary).await;
    }
    result
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

    const REFERENCE: &str = "00000000-0000-0000-0000-000000000001";

    fn setup(kind: &str, base_url: Option<&str>) -> ChatModelSetup {
        ChatModelSetup {
            provider_kind: kind.to_owned(),
            model_id: "example-model".to_owned(),
            base_url: base_url.map(str::to_owned),
            max_billable_input_tokens: 20_000,
            max_output_tokens: 2_000,
        }
    }

    #[test]
    fn single_chat_setup_has_no_secret_and_preserves_exact_model_choice() {
        for (kind, base) in [
            ("openai-responses", None),
            ("anthropic", None),
            ("gemini", None),
            ("openai-compatible", Some("https://example.com/v1")),
        ] {
            let bytes = single_chat_document(&setup(kind, base), REFERENCE).unwrap();
            let document: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
            assert_eq!(document["version"], 1);
            assert_eq!(document["providers"][0]["adapter_kind"], kind);
            assert_eq!(document["providers"][0]["secret_ref"], REFERENCE);
            assert_eq!(document["models"][0]["model_id"], "example-model");
            assert_eq!(
                document["models"][0]["limits"]["max_billable_input_tokens"],
                20_000
            );
            assert!(!String::from_utf8(bytes).unwrap().contains("API-KEY-CANARY"));
        }
    }

    #[test]
    fn setup_rejects_unknown_or_credential_bearing_endpoints() {
        assert!(single_chat_document(&setup("unknown", None), REFERENCE).is_err());
        assert!(single_chat_document(&setup("openai-compatible", None), REFERENCE).is_err());
        assert!(single_chat_document(
            &setup(
                "openai-compatible",
                Some("https://user:password@example.com/v1")
            ),
            REFERENCE,
        )
        .is_err());
        assert!(single_chat_document(
            &setup(
                "openai-compatible",
                Some("https://example.com/v1?key=SECRET")
            ),
            REFERENCE,
        )
        .is_err());
        assert!(single_chat_document(
            &setup("openai-compatible", Some("http://example.com/v1")),
            REFERENCE,
        )
        .is_err());
        assert!(single_chat_document(
            &setup("openai-compatible", Some("http://localhost:11434/v1")),
            REFERENCE,
        )
        .is_ok());
    }

    #[test]
    fn atomic_write_replaces_only_the_nonsecret_config_file() {
        tauri::async_runtime::block_on(async {
            let directory = tempfile::tempdir().unwrap();
            let path = directory.path().join("llm.json");
            let empty = br#"{"version":1,"providers":[],"models":[],"routes":[]}"#;
            std::fs::write(&path, empty).unwrap();
            assert!(is_empty_configuration(empty));
            let configured = single_chat_document(&setup("anthropic", None), REFERENCE).unwrap();
            write_atomic(&path, &configured).await.unwrap();
            assert_eq!(std::fs::read(&path).unwrap(), configured);
            assert!(!is_empty_configuration(&configured));
            assert_eq!(std::fs::read_dir(directory.path()).unwrap().count(), 1);
        });
    }

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
