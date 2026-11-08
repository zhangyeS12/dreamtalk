use tauri::{AppHandle, Runtime, command};
use crate::{MobileCoreExt, models::CallRequest, Result};
#[command]
pub(crate) async fn call<R: Runtime>(app: AppHandle<R>, operation: String, payload: String) -> Result<serde_json::Value> {
    if operation.len() > 64 || payload.len() > 32768 {
        return Err(std::io::Error::other("mobile_invalid_request").into());
    }
    app.mobile_core().call(CallRequest { operation, payload })
}
