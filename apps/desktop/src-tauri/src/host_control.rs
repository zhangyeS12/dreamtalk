use serde::Deserialize;
use serde_json::json;
use tokio::io::{AsyncWrite, AsyncWriteExt};
use uuid::Uuid;

pub const CONTRACT: &str =
    include_str!("../../../../services/core/src/livingworld/bootstrap/host_control_contract.json");

#[derive(Deserialize)]
pub struct HostControlContract {
    pub protocol_version: u32,
    pub max_frame_bytes: usize,
    pub max_secret_ref_bytes: usize,
    pub max_secret_bytes: usize,
    pub message_types: Vec<String>,
}

pub fn contract() -> HostControlContract {
    serde_json::from_str(CONTRACT).expect("packaged_host_control_contract_invalid")
}

fn encode(value: serde_json::Value) -> Result<Vec<u8>, &'static str> {
    let body = serde_json::to_vec(&value).map_err(|_| "host_control_encode_failed")?;
    if body.is_empty() || body.len() > contract().max_frame_bytes {
        return Err("host_control_frame_size_invalid");
    }
    let mut frame = Vec::with_capacity(body.len() + 4);
    frame.extend_from_slice(&(body.len() as u32).to_be_bytes());
    frame.extend_from_slice(&body);
    Ok(frame)
}

fn validate_reference(secret_ref: &str, maximum: usize) -> Result<(), &'static str> {
    let parsed = Uuid::parse_str(secret_ref).map_err(|_| "host_control_secret_ref_invalid")?;
    if secret_ref.len() > maximum || parsed.to_string() != secret_ref {
        return Err("host_control_secret_ref_invalid");
    }
    Ok(())
}

pub fn credential_upsert(secret_ref: &str, secret: &str) -> Result<Vec<u8>, &'static str> {
    let contract = contract();
    validate_reference(secret_ref, contract.max_secret_ref_bytes)?;
    if secret.is_empty() || secret.len() > contract.max_secret_bytes {
        return Err("host_control_value_size_invalid");
    }
    encode(json!({
        "version": contract.protocol_version,
        "type": "credential_upsert",
        "secret_ref": secret_ref,
        "secret": secret,
    }))
}

pub fn credential_remove(secret_ref: &str) -> Result<Vec<u8>, &'static str> {
    let contract = contract();
    validate_reference(secret_ref, contract.max_secret_ref_bytes)?;
    encode(json!({
        "version": contract.protocol_version,
        "type": "credential_remove",
        "secret_ref": secret_ref,
    }))
}

pub fn credential_sync_complete(available: bool) -> Result<Vec<u8>, &'static str> {
    let contract = contract();
    encode(json!({
        "version": contract.protocol_version,
        "type": "credential_sync_complete",
        "secure_store_available": available,
    }))
}

pub async fn write_frame<W: AsyncWrite + Unpin>(
    writer: &mut W,
    frame: &[u8],
) -> Result<(), &'static str> {
    writer
        .write_all(frame)
        .await
        .map_err(|_| "host_control_write_failed")?;
    writer
        .flush()
        .await
        .map_err(|_| "host_control_write_failed")
}

#[cfg(test)]
mod tests {
    use super::*;

    const REFERENCE: &str = "00000000-0000-0000-0000-000000000001";

    fn body(frame: &[u8]) -> serde_json::Value {
        let length = u32::from_be_bytes(frame[0..4].try_into().unwrap()) as usize;
        assert_eq!(length, frame.len() - 4);
        serde_json::from_slice(&frame[4..]).unwrap()
    }

    #[test]
    fn contract_fixture_and_big_endian_frames_match_python() {
        let contract = contract();
        assert_eq!(contract.protocol_version, 1);
        assert_eq!(contract.max_frame_bytes, 8192);
        assert_eq!(contract.max_secret_ref_bytes, 36);
        assert_eq!(contract.message_types.len(), 3);
        let frame = credential_upsert(REFERENCE, "FRAME-SECRET-CANARY").unwrap();
        let value = body(&frame);
        assert_eq!(value["version"], contract.protocol_version);
        assert_eq!(value["type"], "credential_upsert");
        assert_eq!(value["secret_ref"], REFERENCE);
        assert_eq!(value["secret"], "FRAME-SECRET-CANARY");
    }

    #[test]
    fn malformed_reference_and_oversized_secret_fail_with_safe_labels() {
        assert_eq!(
            credential_upsert("not-a-uuid", "FRAME-SECRET-CANARY"),
            Err("host_control_secret_ref_invalid")
        );
        let canary = "S".repeat(contract().max_secret_bytes + 1);
        let error = credential_upsert(REFERENCE, &canary).unwrap_err();
        assert_eq!(error, "host_control_value_size_invalid");
        assert!(!error.contains(&canary));
    }
}
