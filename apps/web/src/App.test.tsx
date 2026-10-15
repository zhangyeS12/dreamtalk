import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { API_PROTOCOL } from "@dreamtalk/api-client";
import { App } from "./App";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); window.history.replaceState(null, "", "/"); });

it("starts Connecting while discovery is pending", () => {
  render(<App discover={() => new Promise(() => {})} />);
  expect(screen.getByRole("status").textContent).toBe("正在打开世界书架。");
});

it("enters Ready only after authenticated compatible health", async () => {
  window.history.replaceState(null, "", "/?developer=1");
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({
      ready: true, core_version: "0.1.0", api_protocol: API_PROTOCOL, generation: "generation", llm_status: "unconfigured",
    })))
    .mockResolvedValue(new Response("[]")));
  render(<App discover={async () => ({ endpoint: "http://127.0.0.1:49153", token: "memory", generation: "generation" })} />);
  expect((await screen.findByText("核心已就绪")).textContent).toBe("核心已就绪");
});

it("enters Failed on discovery failure", async () => {
  render(<App discover={async () => { throw new Error("unavailable"); }} />);
  await screen.findByText("启动暂时没有完成。");
});

it("enters Failed on authentication failure", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 401 })));
  render(<App discover={async () => ({ endpoint: "http://127.0.0.1:49154", token: "wrong", generation: "generation" })} />);
  await screen.findByText("启动暂时没有完成。");
});

it("enters Failed when discovery never finishes", async () => {
  vi.useFakeTimers();
  render(<App discover={() => new Promise(() => {})} />);
  await act(async () => { vi.advanceTimersByTime(60_000); });
  expect(screen.getByRole("status").textContent).toBe("启动暂时没有完成。");
});

it("uses the host recovery command only after an explicit retry", async () => {
  const discover = vi.fn().mockRejectedValue(new Error("unavailable"));
  const recover = vi.fn().mockRejectedValue(new Error("still unavailable"));
  render(<App discover={discover} recover={recover} />);
  const retry = await screen.findByRole("button", { name: "重试启动" });
  expect(discover).toHaveBeenCalledOnce();
  expect(recover).not.toHaveBeenCalled();
  fireEvent.click(retry);
  await screen.findByRole("button", { name: "重试启动" });
  expect(discover).toHaveBeenCalledOnce();
  expect(recover).toHaveBeenCalledOnce();
});
