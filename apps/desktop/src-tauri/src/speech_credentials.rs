//! Only opaque voice key references are persisted; secrets reuse the native vault.

use crate::{credentials::validate_secret_ref, llm_config, supervisor::LaunchConfig};
use std::collections::BTreeMap;

type Registry = BTreeMap<String, Vec<String>>;

async fn load(config: &LaunchConfig) -> Result<Registry, &'static str> {
    let path = config.app_data.join("config/speech-credentials.json");
    let metadata = match tokio::fs::symlink_metadata(&path).await {
        Ok(value) => value,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Registry::new()),
        Err(_) => return Err("speech_credential_registry_unavailable"),
    };
    if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() > 262144 {
        return Err("speech_credential_registry_invalid");
    }
    let bytes = tokio::fs::read(path)
        .await
        .map_err(|_| "speech_credential_registry_unavailable")?;
    let value: Registry =
        serde_json::from_slice(&bytes).map_err(|_| "speech_credential_registry_invalid")?;
    if value.len() > 1024 {
        return Err("speech_credential_registry_invalid");
    }
    for (world, references) in &value {
        validate_secret_ref(world).map_err(|_| "speech_credential_registry_invalid")?;
        if references.len() > 64 {
            return Err("speech_credential_registry_invalid");
        }
        for reference in references {
            validate_secret_ref(reference).map_err(|_| "speech_credential_registry_invalid")?;
        }
    }
    Ok(value)
}

pub async fn references(config: &LaunchConfig) -> Result<Vec<String>, &'static str> {
    Ok(load(config).await?.into_values().flatten().collect())
}

pub async fn world_references(
    config: &LaunchConfig,
    world: &str,
    reference: Option<&str>,
) -> Result<Vec<String>, &'static str> {
    validate_secret_ref(world).map_err(|_| "speech_world_invalid")?;
    if let Some(reference) = reference {
        validate_secret_ref(reference).map_err(|_| "speech_reference_invalid")?;
    }
    Ok(load(config)
        .await?
        .remove(world)
        .unwrap_or_default()
        .into_iter()
        .filter(|item| reference.is_none_or(|wanted| wanted == item))
        .collect())
}

pub async fn authorize_reference(
    config: &LaunchConfig,
    world: &str,
    reference: &str,
    exists: bool,
) -> Result<(), &'static str> {
    validate_secret_ref(world).map_err(|_| "speech_world_invalid")?;
    validate_secret_ref(reference).map_err(|_| "speech_reference_invalid")?;
    let values = load(config).await?;
    let owned = values
        .get(world)
        .is_some_and(|items| items.iter().any(|item| item == reference));
    let other = values
        .iter()
        .any(|(key, items)| key != world && items.iter().any(|item| item == reference));
    if other || exists && !owned {
        return Err("speech_reference_not_owned");
    }
    Ok(())
}

pub async fn register(
    config: &LaunchConfig,
    world: &str,
    reference: &str,
) -> Result<(), &'static str> {
    validate_secret_ref(world).map_err(|_| "speech_world_invalid")?;
    validate_secret_ref(reference).map_err(|_| "speech_reference_invalid")?;
    let mut values = load(config).await?;
    let references = values.entry(world.to_owned()).or_default();
    if !references.contains(&reference.to_owned()) {
        references.push(reference.to_owned());
    }
    if references.len() > 64 || values.len() > 1024 {
        return Err("speech_credential_registry_limit");
    }
    let bytes = serde_json::to_vec(&values).map_err(|_| "speech_credential_registry_invalid")?;
    llm_config::write_atomic(
        &config.app_data.join("config/speech-credentials.json"),
        &bytes,
    )
    .await
}

pub async fn forget(
    config: &LaunchConfig,
    world: &str,
    reference: Option<&str>,
) -> Result<Vec<String>, &'static str> {
    validate_secret_ref(world).map_err(|_| "speech_world_invalid")?;
    let mut values = load(config).await?;
    let mut removed = Vec::new();
    if let Some(references) = values.get_mut(world) {
        references.retain(|item| {
            if reference.is_none_or(|wanted| wanted == item) {
                removed.push(item.clone());
                false
            } else {
                true
            }
        });
    }
    if values.get(world).is_some_and(Vec::is_empty) {
        values.remove(world);
    }
    let bytes = serde_json::to_vec(&values).map_err(|_| "speech_credential_registry_invalid")?;
    llm_config::write_atomic(
        &config.app_data.join("config/speech-credentials.json"),
        &bytes,
    )
    .await?;
    Ok(removed)
}
