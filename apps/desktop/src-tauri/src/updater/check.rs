//! Bounded channel checks and content-free receipts.
use super::package::atomic_json;
use std::{path::Path, time::Duration};

#[derive(Debug)]
pub(super) struct CheckFailure {
    pub(super) code: &'static str,
    pub(super) attempts: u8,
}

fn check_failure(error: &tauri_plugin_updater::Error) -> (&'static str, bool) {
    use tauri_plugin_updater::Error;
    match error {
        Error::Reqwest(error) if error.is_timeout() => ("update_check_timeout", true),
        Error::Reqwest(error) if error.is_connect() => ("update_connection_failed", true),
        Error::Reqwest(error) if error.is_decode() => ("update_manifest_invalid", false),
        Error::Network(_) => ("update_connection_failed", true),
        Error::ReleaseNotFound => ("update_channel_unavailable", false),
        Error::Serialization(_)
        | Error::Semver(_)
        | Error::UrlParse(_)
        | Error::TargetNotFound(_)
        | Error::TargetsNotFound(_) => ("update_manifest_invalid", false),
        _ => ("update_check_failed", false),
    }
}

pub(super) async fn checked_update<F, Fut, T>(mut check: F) -> Result<(T, u8), CheckFailure>
where
    F: FnMut() -> Fut,
    Fut: std::future::Future<Output = Result<T, tauri_plugin_updater::Error>>,
{
    // Metadata GET only: at most one retry, using the same endpoint, proxy and
    // TLS policy. Both attempts share the original 30-second outer deadline.
    let deadline = tokio::time::Instant::now() + Duration::from_secs(30);
    for attempts in 1..=2 {
        match tokio::time::timeout_at(deadline, check()).await {
            Ok(Ok(value)) => return Ok((value, attempts)),
            Ok(Err(error)) => {
                let (code, retryable) = check_failure(&error);
                if retryable && attempts == 1 && tokio::time::Instant::now() < deadline {
                    continue;
                }
                return Err(CheckFailure { code, attempts });
            }
            Err(_) => {
                return Err(CheckFailure {
                    code: "update_check_timeout",
                    attempts,
                })
            }
        }
    }
    unreachable!()
}

pub(super) fn record_check(directory: &Path, version: &str, result: &'static str, attempts: u8) {
    // One bounded metadata receipt. No URLs, exception text, credentials or save contents.
    let _ = atomic_json(
        &directory.join("updates/check-result.json"),
        &serde_json::json!({
            "current_version": version, "result": result, "attempts": attempts,
            "time_unix_ms": std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_millis()
        }),
    );
}

#[cfg(test)]
mod check_tests {
    use super::*;

    #[test]
    fn transient_connection_can_recover_but_invalid_feed_is_not_retried() {
        tauri::async_runtime::block_on(async {
            let mut calls = 0;
            let result = checked_update(|| {
                calls += 1;
                std::future::ready(if calls == 1 {
                    Err(tauri_plugin_updater::Error::Network(
                        "synthetic detail must not be logged".into(),
                    ))
                } else {
                    Ok(None::<()>)
                })
            })
            .await
            .unwrap();
            assert_eq!(calls, 2);
            assert_eq!(result, (None, 2));
            let mut calls = 0;
            let result = checked_update(|| {
                calls += 1;
                std::future::ready(Err::<(), _>(tauri_plugin_updater::Error::TargetNotFound(
                    "synthetic".into(),
                )))
            })
            .await
            .unwrap_err();
            assert_eq!(calls, 1);
            assert_eq!(result.code, "update_manifest_invalid");
        });
    }

    #[test]
    fn failed_connections_remain_errors_and_receipt_contains_no_exception_text() {
        tauri::async_runtime::block_on(async {
            let result = checked_update(|| {
                std::future::ready(Err::<(), _>(tauri_plugin_updater::Error::Network(
                    "synthetic-private-exception".into(),
                )))
            })
            .await
            .unwrap_err();
            assert_eq!(result.attempts, 2);
            assert_eq!(result.code, "update_connection_failed");
            let directory = tempfile::tempdir().unwrap();
            record_check(directory.path(), "0.1.81", result.code, result.attempts);
            let text = std::fs::read_to_string(directory.path().join("updates/check-result.json"))
                .unwrap();
            assert!(!text.contains("synthetic-private-exception"));
            let record: serde_json::Value = serde_json::from_str(&text).unwrap();
            assert_eq!(record["result"], "update_connection_failed");
            assert_eq!(record["attempts"], 2);
        });
    }
}
