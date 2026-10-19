import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { OfflineContactStatus } from "@dreamtalk/api-client";
import { BackgroundTaskFeedback, offlineGuidance } from "./BackgroundTaskFeedback";

afterEach(cleanup);
const status: OfflineContactStatus = { enabled: true, consented: true, revision: 1, hours: 6,
  state: "idle", error: null, last_online_at: null, model_available: true, unread: [] };
function show(value: OfflineContactStatus, reason = "") {
  render(<BackgroundTaskFeedback name="离线联系" guidance={offlineGuidance(value, false, "available", "", reason)} />);
}
it("describes input preparation separately from a stopped generation", () => {
  show({ ...status, state: "attention", error: "offline_input_capacity" }, "程序会按批次重新准备参考资料。");
  expect(screen.getByText("离线联系资料暂未就绪")).toBeTruthy();
  expect(screen.queryByText("本次离线任务已停止")).toBeNull();
});
it("explains automatic local batching without asking to delete authored content", () => {
  show({ ...status, input_preparation: { selected: 16, excluded: 1, clipped: 3, batched: true,
    background_omitted: false, context_limited: false } });
  expect(screen.getByText(/角色按批轮选，本批已准备16位候选/)).toBeTruthy();
  expect(screen.getByText(/原资料保持完整/)).toBeTruthy();
  expect(screen.getByText(/1位候选的资料暂不可用/)).toBeTruthy();
});
it("keeps a paid generation failure visible even when future input is ready", () => {
  show({ ...status, state: "attention", error: "offline_generation_failed",
    input_preparation: { selected: 16, excluded: 0, clipped: 0, batched: true,
      background_omitted: false, context_limited: false } }, "本次生成未完成，可能已产生费用。");
  expect(screen.getByText("本次离线任务已停止")).toBeTruthy();
  expect(screen.getByText(/本次恢复不会自动重试/)).toBeTruthy();
});
it("retains compatibility with an older status without preparation metadata", () => {
  show(status);
  expect(screen.getByText("已开启，等待下一次离线恢复")).toBeTruthy();
});
