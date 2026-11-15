//! Same HuggingFace tokenizer revision and fixed resource as desktop FastEmbed.
use serde::Serialize;
use std::sync::OnceLock;
use tokenizers::{AddedToken, PaddingParams, Tokenizer, TruncationParams};

static TOKENIZER: OnceLock<Result<Tokenizer, ()>> = OnceLock::new();
fn tokenizer() -> Result<&'static Tokenizer, ()> {
    TOKENIZER
        .get_or_init(|| {
            let mut value = Tokenizer::from_bytes(include_bytes!(
                "../../../../plugins/android/src/main/assets/semantic-model/tokenizer.json"
            ))
            .map_err(|_| ())?;
            value
                .with_truncation(Some(TruncationParams {
                    max_length: 512,
                    ..Default::default()
                }))
                .map_err(|_| ())?;
            // special_tokens_map.json contains these same five existing vocabulary tokens.
            value.add_special_tokens(
                ["[UNK]", "[SEP]", "[PAD]", "[CLS]", "[MASK]"].map(|s| AddedToken::from(s, true)),
            );
            value.with_padding(Some(PaddingParams {
                pad_id: 0,
                pad_token: "[PAD]".into(),
                ..Default::default()
            }));
            Ok(value)
        })
        .as_ref()
        .map_err(|_| ())
}
#[derive(Serialize)]
struct Batch {
    ids: Vec<Vec<u32>>,
    mask: Vec<Vec<u32>>,
    types: Vec<Vec<u32>>,
}
fn encode(payload: &str) -> Result<String, ()> {
    if payload.len() > 256 * 1024 {
        return Err(());
    }
    let texts: Vec<String> = serde_json::from_str(payload).map_err(|_| ())?;
    if texts.is_empty() || texts.len() > 16 || texts.iter().any(|t| t.chars().count() > 4096) {
        return Err(());
    }
    let encoded = tokenizer()?.encode_batch(texts, true).map_err(|_| ())?;
    let batch = Batch {
        ids: encoded.iter().map(|e| e.get_ids().to_vec()).collect(),
        mask: encoded
            .iter()
            .map(|e| e.get_attention_mask().to_vec())
            .collect(),
        types: encoded.iter().map(|e| e.get_type_ids().to_vec()).collect(),
    };
    serde_json::to_string(&batch).map_err(|_| ())
}
#[cfg(target_os = "android")]
#[no_mangle]
pub extern "system" fn Java_app_livingworld_mobile_NativeBounds_recallTokens(
    mut env: jni::JNIEnv,
    _object: jni::objects::JObject,
    payload: jni::objects::JString,
) -> jni::sys::jstring {
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let value: String = env.get_string(&payload).map_err(|_| ())?.into();
        encode(&value)
    }))
    .ok()
    .and_then(Result::ok)
    .unwrap_or_default();
    env.new_string(result)
        .map(|s| s.into_raw())
        .unwrap_or(std::ptr::null_mut())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn padding_special_tokens_and_truncation() {
        let batch: serde_json::Value =
            serde_json::from_str(&encode(r#"["你好","Test，中文！"]"#).unwrap()).unwrap();
        let ids = batch["ids"].as_array().unwrap();
        assert_eq!(ids[0][0], 101);
        assert_eq!(
            ids[0].as_array().unwrap().len(),
            ids[1].as_array().unwrap().len()
        );
        assert!(batch["mask"][0].as_array().unwrap().iter().any(|v| *v == 0));
        let long = serde_json::to_string(&vec!["中".repeat(1024)]).unwrap();
        let batch: serde_json::Value = serde_json::from_str(&encode(&long).unwrap()).unwrap();
        assert_eq!(batch["ids"][0].as_array().unwrap().len(), 512);
        assert_eq!(batch["ids"][0][511], 102);
    }
    #[test]
    fn matches_desktop_tokenizer_exactly() {
        let cases: Vec<serde_json::Value> =
            serde_json::from_str(include_str!("recall-tokenizer-fixture.json")).unwrap();
        for case in cases {
            let actual: serde_json::Value =
                serde_json::from_str(&encode(&case["texts"].to_string()).unwrap()).unwrap();
            assert_eq!(actual, case["tokens"]);
        }
    }
    #[test]
    fn rejects_invalid_native_batches() {
        for value in ["[]", "{}", r#"["ok",null]"#] {
            assert!(encode(value).is_err());
        }
        assert!(encode(&serde_json::to_string(&vec!["中"; 17]).unwrap()).is_err());
    }
}
