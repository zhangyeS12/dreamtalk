use serde::de::DeserializeOwned;
use tauri::{plugin::PluginApi, AppHandle, Runtime};
use crate::models::CallRequest;
pub fn init<R: Runtime, C: DeserializeOwned>(_app: &AppHandle<R>, _api: PluginApi<R, C>) -> crate::Result<MobileCore<R>> { Ok(MobileCore(std::marker::PhantomData)) }
pub struct MobileCore<R: Runtime>(std::marker::PhantomData<R>);
impl<R: Runtime> MobileCore<R> {
    pub fn call(&self, _payload: CallRequest) -> crate::Result<serde_json::Value> { Err(std::io::Error::other("mobile_host_required").into()) }
}
