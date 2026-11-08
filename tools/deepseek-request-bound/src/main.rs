//! Local prompt framing through the official MIT DeepSeek recipe crates.
//! Never emits prompt content, provider credentials, or raw conversion errors.
use deepseek_recipe::openai::chat_completion::request::ChatCompletionRequest;
use deepseek_recipe::request::{ConversionOptions, ProtocolRequest};
use deepseek_recipe_encoding::{
    dsv4::DeepseekV4Encoding, dsv41::DeepseekV41Encoding, PromptEncoding,
};
use serde::Deserialize;
use std::io::{self, Read};

const MAX_BYTES: u64 = 4 * 1024 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    encoding: String,
    payload: ChatCompletionRequest,
}

fn bound() -> Result<u64, ()> {
    let mut bytes = Vec::new();
    io::stdin()
        .take(MAX_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| ())?;
    if bytes.len() as u64 > MAX_BYTES {
        return Err(());
    }
    let input: Input = serde_json::from_slice(&bytes).map_err(|_| ())?;
    let mut options = ConversionOptions::default();
    options.default_thinking_mode = true;
    let conversation = input.payload.convert(options).map_err(|_| ())?.conversation;
    let rendered = match input.encoding.as_str() {
        "deepseek-v4" => DeepseekV4Encoding::new().render_conversation(&conversation),
        "deepseek-v41" => DeepseekV41Encoding::new().render_conversation(&conversation),
        _ => return Err(()),
    };
    if !rendered.image_sources.is_empty() {
        return Err(());
    }
    // Byte-level BPE with no expanding normalizer merges the original bytes.
    // Full framed UTF-8 byte length also overcounts special-token spellings.
    // This conservative upper bound deliberately does not claim exact counting.
    Ok(rendered.prompt.len() as u64)
}

fn main() {
    match bound() {
        Ok(input_upper_bound) => println!(
            "{}",
            serde_json::json!({"input_upper_bound":input_upper_bound})
        ),
        Err(()) => {
            eprintln!("request_bound_unavailable");
            std::process::exit(2);
        }
    }
}
