#![cfg(windows)]

use livingworld_desktop_lib::supervisor::{
    contract, CoreSupervisor, LaunchConfig, SupervisorState,
};
use std::{path::PathBuf, time::Duration};

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
