import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { DesktopUpdateEntry, DesktopUpdateProvider } from "./DesktopUpdates";

const native = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ isTauri: () => true, invoke: native.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("@tauri-apps/api/window", () => ({ getCurrentWindow: () => ({ isVisible: async () => true }) }));
const status = { current_version: "0.1.81", suppress_popup: false, signing_ready: true, installed: true, repair_install: false, release: null, cleanup_notice: null };
afterEach(() => { cleanup(); native.invoke.mockReset(); });

function mountCheck(pending: Promise<unknown>) {
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
  native.invoke.mockImplementation((command: string) => command === "check_desktop_update" ? pending : Promise.resolve(status));
  render(<DesktopUpdateProvider ready={false}><DesktopUpdateEntry /></DesktopUpdateProvider>);
}

it("shows a manual request's error even when it joins an automatic check", async () => {
  let reject!: (reason: string) => void;
  mountCheck(new Promise((_, fail) => { reject = fail; }));
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: "检查更新" }));
  await act(async () => { reject("update_connection_failed"); });
  expect(screen.getByRole("alert").textContent).toContain("暂时无法连接更新服务");
  expect(screen.queryByText("你正在使用最新版本。")).toBeNull();
  expect(native.invoke.mock.calls.filter(([command]) => command === "check_desktop_update")).toHaveLength(1);
});

it("reports the current version only after a successful check", async () => {
  let resolve!: (value: null) => void;
  mountCheck(new Promise(done => { resolve = done; }));
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: "检查更新" }));
  await act(async () => { resolve(null); });
  expect(screen.getByText("你正在使用最新版本。")).toBeTruthy();
  expect(screen.queryByRole("alert")).toBeNull();
});
