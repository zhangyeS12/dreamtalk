"""Exercise the actual splash/updater layout with an in-memory native bridge."""

from pathlib import Path

from playwright.sync_api import expect

BRIDGE = """() => {
  window.isTauri = true;
  const state = { outcome: 'pending', calls: 0, installs: 0 };
  window.__updateCheck = state;
  window.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener() {} };
  window.__TAURI_INTERNALS__ = {
    metadata: { currentWindow: {label:'main'}, currentWebview: {label:'main'} },
    transformCallback() { return 1; },
    async invoke(command) {
      if (command === 'save_safety_status')
        return { recovery_required: false, update_verifying: false };
      if (command === 'core_connection') throw 'core_storage_version_unsupported';
      if (command === 'desktop_update_status') return {
        current_version:'0.1.81', suppress_popup:false, signing_ready:true,
        installed:true, repair_install:false, release:null, cleanup_notice:null
      };
      if (command === 'check_desktop_update') {
        state.calls++;
        if (state.outcome === 'current') return null;
        return new Promise((resolve, reject) => { state.reject = reject; });
      }
      if (command === 'install_desktop_update') { state.installs++; throw 'unexpected_install'; }
      if (command === 'plugin:window|is_visible') return true;
      return null;
    }
  };
} """


def check_startup_recovery(browser, url):
    page = browser.new_page(viewport={"width": 1280, "height": 860})
    failures = []
    page.on("pageerror", lambda _: failures.append(True))
    try:
        page.add_init_script("(" + BRIDGE + ")()")
        page.goto(url, wait_until="networkidle")
        expect(page.get_by_text("当前版本无法读取这份存档", exact=True)).to_be_visible()
        # Real browser hit testing catches an updater hidden behind the splash.
        page.locator(".startup-update-entry").get_by_role("button").click()
        dialog = page.get_by_role("dialog", name="应用更新")
        expect(dialog).to_be_visible()
        page.wait_for_function("typeof window.__updateCheck.reject === 'function'")
        page.evaluate("window.__updateCheck.reject('update_connection_failed')")
        expect(dialog.get_by_role("alert")).to_contain_text("暂时无法连接更新服务")
        expect(dialog.get_by_text("你正在使用最新版本。", exact=True)).to_have_count(0)
        assert page.evaluate("window.__updateCheck.calls") == 1
        page.evaluate("window.__updateCheck.outcome = 'current'")
        dialog.get_by_role("button", name="检查更新", exact=True).click()
        expect(dialog.get_by_text("你正在使用最新版本。", exact=True)).to_be_visible()
        expect(dialog.get_by_role("alert")).to_have_count(0)
        assert page.evaluate("window.__updateCheck.calls") == 2
        assert page.evaluate("window.__updateCheck.installs") == 0
        output = Path(__file__).resolve().parents[1] / "artifacts/browser-checks"
        output.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(output / "startup-update-recovery.png"), full_page=True)
        if failures:
            raise RuntimeError("startup_recovery_page_error")
    finally:
        page.close()
