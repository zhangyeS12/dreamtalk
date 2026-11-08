use tauri::{plugin::{Builder, TauriPlugin}, Manager, Runtime};
mod commands; mod error; mod models;
#[cfg(mobile)] mod mobile;
#[cfg(desktop)] mod desktop;
pub use error::{Error, Result};
#[cfg(mobile)] use mobile::MobileCore;
#[cfg(desktop)] use desktop::MobileCore;
pub trait MobileCoreExt<R: Runtime> { fn mobile_core(&self) -> &MobileCore<R>; }
impl<R: Runtime, T: Manager<R>> MobileCoreExt<R> for T {
    fn mobile_core(&self) -> &MobileCore<R> { self.state::<MobileCore<R>>().inner() }
}
pub fn init<R: Runtime>() -> TauriPlugin<R> {
    Builder::new("mobile-core").invoke_handler(tauri::generate_handler![commands::call])
        .setup(|app, api| {
            #[cfg(mobile)] let core = mobile::init(app, api)?;
            #[cfg(desktop)] let core = desktop::init(app, api)?;
            app.manage(core); Ok(())
        }).build()
}
