use serde::Serialize;
use std::{collections::HashMap, sync::Mutex};
use uuid::Uuid;

const SERVICE: &str = "LivingWorld";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CredentialStoreError {
    Missing,
    Unavailable,
    InvalidReference,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CredentialStatus {
    Configured,
    Missing,
    SecureStoreUnavailable,
}

pub fn validate_secret_ref(secret_ref: &str) -> Result<(), CredentialStoreError> {
    let parsed = Uuid::parse_str(secret_ref).map_err(|_| CredentialStoreError::InvalidReference)?;
    if secret_ref.len() != 36 || parsed.to_string() != secret_ref {
        return Err(CredentialStoreError::InvalidReference);
    }
    Ok(())
}

pub trait CredentialStore: Send + Sync {
    fn put(&self, secret_ref: &str, secret: &str) -> Result<(), CredentialStoreError>;
    fn exists(&self, secret_ref: &str) -> Result<bool, CredentialStoreError>;
    fn delete(&self, secret_ref: &str) -> Result<(), CredentialStoreError>;
    fn resolve(&self, secret_ref: &str) -> Result<String, CredentialStoreError>;
}

#[derive(Default)]
pub struct NativeCredentialStore;

impl NativeCredentialStore {
    fn entry(secret_ref: &str) -> Result<keyring::Entry, CredentialStoreError> {
        validate_secret_ref(secret_ref)?;
        keyring::Entry::new(SERVICE, secret_ref).map_err(|_| CredentialStoreError::Unavailable)
    }

    fn map_error(error: keyring::Error) -> CredentialStoreError {
        match error {
            keyring::Error::NoEntry => CredentialStoreError::Missing,
            _ => CredentialStoreError::Unavailable,
        }
    }
}

impl CredentialStore for NativeCredentialStore {
    fn put(&self, secret_ref: &str, secret: &str) -> Result<(), CredentialStoreError> {
        if secret.is_empty() || secret.len() > 4096 {
            return Err(CredentialStoreError::Unavailable);
        }
        Self::entry(secret_ref)?
            .set_password(secret)
            .map_err(Self::map_error)
    }

    fn exists(&self, secret_ref: &str) -> Result<bool, CredentialStoreError> {
        match self.resolve(secret_ref) {
            Ok(mut value) => {
                value.clear();
                Ok(true)
            }
            Err(CredentialStoreError::Missing) => Ok(false),
            Err(error) => Err(error),
        }
    }

    fn delete(&self, secret_ref: &str) -> Result<(), CredentialStoreError> {
        match Self::entry(secret_ref)?.delete_credential() {
            Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
            Err(error) => Err(Self::map_error(error)),
        }
    }

    fn resolve(&self, secret_ref: &str) -> Result<String, CredentialStoreError> {
        Self::entry(secret_ref)?
            .get_password()
            .map_err(Self::map_error)
    }
}

#[derive(Default)]
pub struct MemoryCredentialStore {
    values: Mutex<HashMap<String, String>>,
    unavailable: Mutex<bool>,
}

impl MemoryCredentialStore {
    pub fn set_unavailable(&self, unavailable: bool) {
        *self.unavailable.lock().expect("credential_fake_poisoned") = unavailable;
    }

    fn available(&self) -> Result<(), CredentialStoreError> {
        if *self.unavailable.lock().expect("credential_fake_poisoned") {
            Err(CredentialStoreError::Unavailable)
        } else {
            Ok(())
        }
    }
}

impl CredentialStore for MemoryCredentialStore {
    fn put(&self, secret_ref: &str, secret: &str) -> Result<(), CredentialStoreError> {
        self.available()?;
        validate_secret_ref(secret_ref)?;
        if secret.is_empty() || secret.len() > 4096 {
            return Err(CredentialStoreError::Unavailable);
        }
        self.values
            .lock()
            .expect("credential_fake_poisoned")
            .insert(secret_ref.to_owned(), secret.to_owned());
        Ok(())
    }

    fn exists(&self, secret_ref: &str) -> Result<bool, CredentialStoreError> {
        self.available()?;
        validate_secret_ref(secret_ref)?;
        Ok(self
            .values
            .lock()
            .expect("credential_fake_poisoned")
            .contains_key(secret_ref))
    }

    fn delete(&self, secret_ref: &str) -> Result<(), CredentialStoreError> {
        self.available()?;
        validate_secret_ref(secret_ref)?;
        self.values
            .lock()
            .expect("credential_fake_poisoned")
            .remove(secret_ref);
        Ok(())
    }

    fn resolve(&self, secret_ref: &str) -> Result<String, CredentialStoreError> {
        self.available()?;
        validate_secret_ref(secret_ref)?;
        self.values
            .lock()
            .expect("credential_fake_poisoned")
            .get(secret_ref)
            .cloned()
            .ok_or(CredentialStoreError::Missing)
    }
}

pub fn status(store: &dyn CredentialStore, secret_ref: &str) -> CredentialStatus {
    match store.exists(secret_ref) {
        Ok(true) => CredentialStatus::Configured,
        Ok(false) | Err(CredentialStoreError::Missing) => CredentialStatus::Missing,
        Err(_) => CredentialStatus::SecureStoreUnavailable,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const REFERENCE: &str = "00000000-0000-0000-0000-000000000001";

    #[test]
    fn memory_store_supports_status_rotation_and_delete_without_plaintext_api() {
        let store = MemoryCredentialStore::default();
        assert_eq!(status(&store, REFERENCE), CredentialStatus::Missing);
        store.put(REFERENCE, "first-secret").unwrap();
        assert_eq!(status(&store, REFERENCE), CredentialStatus::Configured);
        store.put(REFERENCE, "rotated-secret").unwrap();
        assert_eq!(store.resolve(REFERENCE).unwrap(), "rotated-secret");
        store.delete(REFERENCE).unwrap();
        assert_eq!(status(&store, REFERENCE), CredentialStatus::Missing);
    }

    #[test]
    fn invalid_reference_and_store_unavailability_are_typed() {
        let store = MemoryCredentialStore::default();
        assert_eq!(
            store.put("not-a-secret-ref", "secret"),
            Err(CredentialStoreError::InvalidReference)
        );
        store.set_unavailable(true);
        assert_eq!(
            status(&store, REFERENCE),
            CredentialStatus::SecureStoreUnavailable
        );
    }
}
