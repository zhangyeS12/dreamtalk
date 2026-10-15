//! World-owned opaque references; media and speech retain separate registries.

#[derive(Clone, Copy)]
pub enum CredentialDomain {
    Speech,
    Media,
}

use crate::{credentials::validate_secret_ref, llm_config, supervisor::LaunchConfig};
use std::collections::BTreeMap;

type Registry = BTreeMap<String, Vec<String>>;

impl CredentialDomain {
    fn path(self) -> &'static str {
        match self {
            Self::Speech => "config/speech-credentials.json",
            Self::Media => "config/media-credentials.json",
        }
    }

    fn error(self, kind: &str) -> &'static str {
        match (self, kind) {
            (Self::Speech, "credential_registry_unavailable") => {
                "speech_credential_registry_unavailable"
            }
            (Self::Media, "credential_registry_unavailable") => {
                "media_credential_registry_unavailable"
            }
            (Self::Speech, "credential_registry_invalid") => "speech_credential_registry_invalid",
            (Self::Media, "credential_registry_invalid") => "media_credential_registry_invalid",
            (Self::Speech, "world_invalid") => "speech_world_invalid",
            (Self::Media, "world_invalid") => "media_world_invalid",
            (Self::Speech, "reference_invalid") => "speech_reference_invalid",
            (Self::Media, "reference_invalid") => "media_reference_invalid",
            (Self::Speech, "reference_not_owned") => "speech_reference_not_owned",
            (Self::Media, "reference_not_owned") => "media_reference_not_owned",
            (Self::Speech, "credential_registry_limit") => "speech_credential_registry_limit",
            (Self::Media, "credential_registry_limit") => "media_credential_registry_limit",
            _ => unreachable!("fixed credential registry error"),
        }
    }

    async fn load(self, config: &LaunchConfig) -> Result<Registry, &'static str> {
        let path = config.app_data.join(self.path());
        let metadata = match tokio::fs::symlink_metadata(&path).await {
            Ok(value) => value,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return Ok(Registry::new())
            }
            Err(_) => return Err(self.error("credential_registry_unavailable")),
        };
        if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() > 262144 {
            return Err(self.error("credential_registry_invalid"));
        }
        let bytes = tokio::fs::read(path)
            .await
            .map_err(|_| self.error("credential_registry_unavailable"))?;
        let value: Registry = serde_json::from_slice(&bytes)
            .map_err(|_| self.error("credential_registry_invalid"))?;
        if value.len() > 1024 {
            return Err(self.error("credential_registry_invalid"));
        }
        for (world, references) in &value {
            validate_secret_ref(world).map_err(|_| self.error("credential_registry_invalid"))?;
            if references.len() > 64 {
                return Err(self.error("credential_registry_invalid"));
            }
            for reference in references {
                validate_secret_ref(reference)
                    .map_err(|_| self.error("credential_registry_invalid"))?;
            }
        }
        Ok(value)
    }

    pub async fn references(self, config: &LaunchConfig) -> Result<Vec<String>, &'static str> {
        Ok(self.load(config).await?.into_values().flatten().collect())
    }

    pub async fn scoped_references(
        self,
        config: &LaunchConfig,
    ) -> Result<Vec<(String, String)>, &'static str> {
        Ok(self
            .load(config)
            .await?
            .into_iter()
            .flat_map(|(world, references)| {
                references
                    .into_iter()
                    .map(move |reference| (world.clone(), reference))
            })
            .collect())
    }

    pub async fn world_references(
        self,
        config: &LaunchConfig,
        world: &str,
        reference: Option<&str>,
    ) -> Result<Vec<String>, &'static str> {
        validate_secret_ref(world).map_err(|_| self.error("world_invalid"))?;
        if let Some(reference) = reference {
            validate_secret_ref(reference).map_err(|_| self.error("reference_invalid"))?;
        }
        Ok(self
            .load(config)
            .await?
            .remove(world)
            .unwrap_or_default()
            .into_iter()
            .filter(|item| reference.is_none_or(|wanted| wanted == item))
            .collect())
    }

    pub async fn authorize_reference(
        self,
        config: &LaunchConfig,
        world: &str,
        reference: &str,
        exists: bool,
    ) -> Result<(), &'static str> {
        validate_secret_ref(world).map_err(|_| self.error("world_invalid"))?;
        validate_secret_ref(reference).map_err(|_| self.error("reference_invalid"))?;
        let values = self.load(config).await?;
        let owned = values
            .get(world)
            .is_some_and(|items| items.iter().any(|item| item == reference));
        let other = values
            .iter()
            .any(|(key, items)| key != world && items.iter().any(|item| item == reference));
        if other || exists && !owned {
            return Err(self.error("reference_not_owned"));
        }
        Ok(())
    }

    pub async fn register(
        self,
        config: &LaunchConfig,
        world: &str,
        reference: &str,
    ) -> Result<(), &'static str> {
        validate_secret_ref(world).map_err(|_| self.error("world_invalid"))?;
        validate_secret_ref(reference).map_err(|_| self.error("reference_invalid"))?;
        let mut values = self.load(config).await?;
        let references = values.entry(world.to_owned()).or_default();
        if !references.contains(&reference.to_owned()) {
            references.push(reference.to_owned());
        }
        if references.len() > 64 || values.len() > 1024 {
            return Err(self.error("credential_registry_limit"));
        }
        let bytes =
            serde_json::to_vec(&values).map_err(|_| self.error("credential_registry_invalid"))?;
        llm_config::write_atomic(&config.app_data.join(self.path()), &bytes).await
    }

    pub async fn forget(
        self,
        config: &LaunchConfig,
        world: &str,
        reference: Option<&str>,
    ) -> Result<Vec<String>, &'static str> {
        validate_secret_ref(world).map_err(|_| self.error("world_invalid"))?;
        let mut values = self.load(config).await?;
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
        let bytes =
            serde_json::to_vec(&values).map_err(|_| self.error("credential_registry_invalid"))?;
        llm_config::write_atomic(&config.app_data.join(self.path()), &bytes).await?;
        Ok(removed)
    }
}
