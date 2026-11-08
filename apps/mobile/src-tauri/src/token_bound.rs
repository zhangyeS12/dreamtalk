use deepseek_recipe::openai::chat_completion::request::ChatCompletionRequest;
use deepseek_recipe::request::{ConversionOptions, ProtocolRequest};
use deepseek_recipe_encoding::{dsv4::DeepseekV4Encoding, dsv41::DeepseekV41Encoding, PromptEncoding};
use serde::Deserialize;
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct BoundInput { encoding: String, payload: ChatCompletionRequest }
fn upper_bound(bytes: &[u8]) -> Result<i64, ()> {
    if bytes.len() > 4 * 1024 * 1024 { return Err(()); }
    let input: BoundInput = serde_json::from_slice(bytes).map_err(|_| ())?;
    let mut options = ConversionOptions::default(); options.default_thinking_mode = true;
    let conversation = input.payload.convert(options).map_err(|_| ())?.conversation;
    let rendered = match input.encoding.as_str() {
        "deepseek-v4" => DeepseekV4Encoding::new().render_conversation(&conversation),
        "deepseek-v41" => DeepseekV41Encoding::new().render_conversation(&conversation),
        _ => return Err(()),
    };
    if !rendered.image_sources.is_empty() { return Err(()); }
    Ok(rendered.prompt.len() as i64)
}
#[cfg(target_os = "android")]
#[no_mangle]
pub extern "system" fn Java_app_livingworld_mobile_ExamplePlugin_tokenUpperBound(
    mut env: jni::JNIEnv, _object: jni::objects::JObject, payload: jni::objects::JString
) -> jni::sys::jlong {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let value: String = env.get_string(&payload).map_err(|_| ())?.into();
        upper_bound(value.as_bytes())
    })).ok().and_then(Result::ok).unwrap_or(-1)
}
#[cfg(target_os = "android")]
#[no_mangle]
pub extern "system" fn Java_app_livingworld_mobile_NativeBounds_tokenUpperBound(
    env: jni::JNIEnv, object: jni::objects::JObject, payload: jni::objects::JString
) -> jni::sys::jlong {
    Java_app_livingworld_mobile_ExamplePlugin_tokenUpperBound(env, object, payload)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn rejects_unknown_encoding() { assert!(upper_bound(br#"{"encoding":"other","payload":{}}"#).is_err()); }
    #[test] fn rejects_large_payload_before_parsing() { assert!(upper_bound(&vec![b'a'; 4 * 1024 * 1024 + 1]).is_err()); }
}
