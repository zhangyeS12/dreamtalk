import { expect, it } from "vitest";
import { feedback } from "./host";

it.each(["mobile_core_start_failed", "mobile_core_timeout", "mobile_data_path_invalid", "save_link_rejected", "save_path_invalid"])("offers startup diagnostics for %s", code => {
  expect(feedback(new Error(code))).toBe("本机核心未能启动，请复制启动诊断并发给工程端排查。");
});

it("never displays an arbitrary native error message", () => {
  expect(feedback(new Error("SYNTHETIC_SECRET"))).not.toContain("SYNTHETIC_SECRET");
});
