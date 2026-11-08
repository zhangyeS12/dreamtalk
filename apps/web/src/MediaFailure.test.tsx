import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CoreClient, CoreRequestError } from "@dreamtalk/api-client";
import { StickerPicker } from "./ChatMedia";
import { SpeechControls, SpeechProvider, useSpeech } from "./SpeechPlayback";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("does not report an empty sticker library on read failure and offers manual retry", async () => {
  const stickers = vi.fn().mockRejectedValueOnce(new CoreRequestError(503)).mockResolvedValue({ items: [], has_more: false });
  const client = { stickers } as unknown as CoreClient;
  render(<StickerPicker client={client} worldId="synthetic" selected={null} onSelect={() => {}} disabled={false} />);
  fireEvent.click(screen.getByRole("button", { name: "表情" }));
  await screen.findByRole("alert");
  expect(screen.queryByText(/没有找到表情/)).toBeNull();
  expect(stickers).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "重新读取表情" }));
  await screen.findByText(/没有找到表情/);
  expect(stickers).toHaveBeenCalledTimes(2);
});

it("preserves text and the old recording when regeneration fails without retrying", async () => {
  vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  const regenerateSpeech = vi.fn().mockRejectedValue(new CoreRequestError(503, "speech_audio_incomplete"));
  const generateSpeech = vi.fn(), speechAudio = vi.fn();
  const client = { speechSettings: vi.fn().mockResolvedValue({ revision: 1, settings: { enabled: true, provider: "local" } }),
    regenerateSpeech, generateSpeech, speechAudio, speechPreviews: vi.fn().mockResolvedValue({ items: [] }) } as unknown as CoreClient;
  function View() { const speech = useSpeech(); return <><p>合成的完整文字回复</p><p role="status">{speech?.feedback}</p><SpeechControls conversation="conversation" message="message" /></>; }
  render(<SpeechProvider client={client} worldId="synthetic"><View /></SpeechProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "重新配音" }));
  await waitFor(() => expect(screen.getByRole("status").textContent).toContain("原配音未替换"));
  expect(screen.getByText("合成的完整文字回复")).toBeTruthy();
  expect(regenerateSpeech).toHaveBeenCalledOnce();
  expect(generateSpeech).not.toHaveBeenCalled();
  expect(speechAudio).not.toHaveBeenCalled();
  expect((screen.getByRole("button", { name: "重新配音" }) as HTMLButtonElement).disabled).toBe(false);
});
