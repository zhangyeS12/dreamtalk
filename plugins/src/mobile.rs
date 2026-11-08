use serde::de::DeserializeOwned;
use tauri::{plugin::{PluginApi, PluginHandle}, AppHandle, Runtime};
use crate::models::CallRequest;
pub fn init<R: Runtime, C: DeserializeOwned>(_app: &AppHandle<R>, api: PluginApi<R, C>) -> crate::Result<MobileCore<R>> {
    let handle = api.register_android_plugin("app.livingworld.mobile", "ExamplePlugin")?;
    Ok(MobileCore(handle))
}
pub struct MobileCore<R: Runtime>(PluginHandle<R>);
impl<R: Runtime> MobileCore<R> {
    pub fn call(&self, payload: CallRequest) -> crate::Result<serde_json::Value> {
        self.0.run_mobile_plugin("call", payload).map_err(Into::into)
    }
}
