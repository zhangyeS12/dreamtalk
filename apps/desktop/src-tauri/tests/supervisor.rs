#![cfg(windows)]

use livingworld_desktop_lib::credentials::{CredentialStore, MemoryCredentialStore};
use livingworld_desktop_lib::supervisor::{
    contract, CoreSupervisor, LaunchConfig, SupervisorState,
};
use std::{path::PathBuf, sync::Arc, time::Duration};

#[test]
fn windows_supervisor_lifecycle_restart_and_authentication() {
    tauri::async_runtime::block_on(async {
        let directory = tempfile::tempdir().unwrap();
        let config = LaunchConfig {
            project_root: PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../..")
                .canonicalize()
                .unwrap(),
            app_data: directory.path().to_owned(),
            startup_timeout: Duration::from_secs(12),
            llm_config_path: directory.path().join("config").join("llm.json"),
        };
        let mut supervisor = CoreSupervisor::new();
        supervisor.start(&config).await.unwrap();
        assert_eq!(supervisor.state, SupervisorState::Ready);
        let connection = supervisor.connection().unwrap();
        let health = supervisor.authenticated_health().await.unwrap();
        assert_eq!(health.api_protocol, contract().api_protocol);
        let client = reqwest::Client::builder().no_proxy().build().unwrap();
        let endpoint = format!("{}/system/health", connection.endpoint);
        assert_eq!(client.get(&endpoint).send().await.unwrap().status(), 401);
        assert_eq!(
            client
                .get(&endpoint)
                .bearer_auth("wrong")
                .send()
                .await
                .unwrap()
                .status(),
            401
        );
        supervisor.restart(&config).await.unwrap();
        assert_ne!(
            supervisor.connection().unwrap().generation,
            connection.generation
        );
        assert!(
            supervisor
                .stop(Duration::from_secs(4))
                .await
                .unwrap()
                .graceful
        );
        assert!(supervisor.connection().is_err());
        assert!(std::fs::read_dir(directory.path().join("runtime"))
            .unwrap()
            .next()
            .is_none());
    });
}

#[test]
fn windows_credentials_are_reprovisioned_after_restart_without_disk_leak() {
    tauri::async_runtime::block_on(async {
        let directory = tempfile::tempdir().unwrap();
        let secret_ref = "00000000-0000-0000-0000-000000000001";
        let secret = "SIDECAR-CREDENTIAL-CANARY";
        let config_path = directory.path().join("config").join("llm.json");
        std::fs::create_dir_all(config_path.parent().unwrap()).unwrap();
        std::fs::write(
            &config_path,
            serde_json::json!({
                "version": 1,
                "providers": [{
                    "provider_id": "configured-provider",
                    "adapter_kind": "openai-compatible",
                    "base_url": "https://provider.invalid",
                    "secret_ref": secret_ref
                }],
                "models": [{
                    "provider_id": "configured-provider",
                    "model_id": "opaque-model",
                    "enabled": true,
                    "capabilities": {"text_generation": true},
                    "limits": {"max_billable_input_tokens": 1024, "max_output_tokens": 32},
                    "adapter_profile": {}
                }],
                "routes": [],
                "execution_policy": {},
                "pricing_catalog": {
                    "catalog_id": "empty",
                    "source_label": "configured-empty",
                    "schedules": [],
                    "aliases": []
                }
            })
            .to_string(),
        )
        .unwrap();
        let launch = LaunchConfig {
            project_root: PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../..")
                .canonicalize()
                .unwrap(),
            app_data: directory.path().to_owned(),
            startup_timeout: Duration::from_secs(12),
            llm_config_path: config_path,
        };
        let credentials = Arc::new(MemoryCredentialStore::default());
        credentials.put(secret_ref, secret).unwrap();
        let mut supervisor = CoreSupervisor::with_credential_store(credentials);
        supervisor.start(&launch).await.unwrap();
        assert_eq!(
            supervisor.authenticated_health().await.unwrap().llm_status,
            "ready"
        );
        supervisor.restart(&launch).await.unwrap();
        assert_eq!(
            supervisor.authenticated_health().await.unwrap().llm_status,
            "ready"
        );
        supervisor.stop(Duration::from_secs(4)).await.unwrap();

        fn assert_clean(path: &std::path::Path, canary: &[u8]) {
            for entry in std::fs::read_dir(path).unwrap() {
                let entry = entry.unwrap();
                if entry.file_type().unwrap().is_dir() {
                    assert_clean(&entry.path(), canary);
                } else {
                    let bytes = std::fs::read(entry.path()).unwrap();
                    assert!(!bytes.windows(canary.len()).any(|window| window == canary));
                }
            }
        }
        assert_clean(directory.path(), secret.as_bytes());
    });
}

#[test]
fn windows_forced_termination_fallback() {
    tauri::async_runtime::block_on(async {
        let directory = tempfile::tempdir().unwrap();
        let config = LaunchConfig {
            project_root: PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../..")
                .canonicalize()
                .unwrap(),
            app_data: directory.path().to_owned(),
            startup_timeout: Duration::from_secs(12),
            llm_config_path: directory.path().join("config").join("llm.json"),
        };
        let mut supervisor = CoreSupervisor::new();
        supervisor.start(&config).await.unwrap();
        let connection = supervisor.connection().unwrap();
        assert!(!supervisor.stop(Duration::ZERO).await.unwrap().graceful);
        assert!(reqwest::Client::builder()
            .no_proxy()
            .build()
            .unwrap()
            .get(format!("{}/system/live", connection.endpoint))
            .send()
            .await
            .is_err());
    });
}
