import type * as Requests from "./contracts.generated";
import { isContentEditorPage, isChatReplyProgress } from "./contracts.generated";
export type { ContentEditorPage, ContentResearch, SpeechPreviewJob } from "./contracts.generated";
import { isChatMediaSettings, isMediaUsageResult, isStickersResult, isStickerEntry, isEditStickerResult, isRemoveStickerResult, isCaptionMediaResult, isSpeechStatus, isSpeechPricing, isVoiceCardPage, isVoiceBindingResult, isVoiceCardPreview, isVoiceCard, isRemoveVoiceCardResult, isSpeechJob, isSpeechPreviewsResult, isWorldContentItem, isSetCommonLoreResult, isChatMessage, isChatMessagePage, isChatHistoryMatches, isLongChatMemorySnapshot, isConversationMemorySnapshot, isConversationMemoryDraft, isConversationMemoryRevision, isConversationMemorySources, isConversationMemoryDraftSourcesResult, isPendingPlayerSend, isChatReplyAvailability, isChatContextReports, isReplyRecoveryView, isCreateReplyRecoveryResult, isDirectTurnView, isGroupTurnView, isContentEditorResult, isContentBuilderJob, isDiscardWorldContentResult, isActivityCharacterDirectory, isInitializeCharacterActivityResult, isActivityLocation, isWorldCover, isCoverImage, isSocialSnapshot, isAvatarDigest, isCreateFactionResult, isDeleteWorldResult, isContentExportInfo, isChatExportInfo, isDissolveGroupResult, isCreateWorldResult, isExampleWorldTemplate, isPauseProductWorldResult, isSetPlayerAvailabilityResult, isBindPlayerResult, isProactiveContactStatus, isChatUnreadStatus, isMarkConversationReadResult, isOfflineContactStatus, isWorldStoryEntries, isWorldNewsStatus, isDirectorStatus, isWorldSummary, isInspectorSnapshot, isScheduleTriggerResult, isRecordMemoryResult, isCoreHealth, isWorldSettings, isSelectablePlayer, isSelectedPlayerState, isLocalProfile, isKnownWorldEvent, isChatConversation, isGroupChatConversation } from "./contracts.generated";

import type { MediaUsageResult, StickersResult, EditStickerResult, RemoveStickerResult, CaptionMediaResult, VoiceBindingResult, RemoveVoiceCardResult, SpeechPreviewsResult, SetCommonLoreResult, ConversationMemoryDraftSourcesResult, CreateReplyRecoveryResult, ContentEditorResult, DiscardWorldContentResult, InitializeCharacterActivityResult, CreateFactionResult, DeleteWorldResult, DissolveGroupResult, CreateWorldResult, PauseProductWorldResult, SetPlayerAvailabilityResult, BindPlayerResult, MarkConversationReadResult, ScheduleTriggerResult, RecordMemoryResult } from "./contracts.generated";
import type { ExampleWorldTemplate, CoverImage, WorldCover, WorldCoverWrite, ContentExportFormat, FileExportRequest, ContentExportInfo, ChatExportInfo, Residency, ActivityLocation, LocationDraft, ActivityCharacterDirectory, ProactiveContactStatus, ChatUnreadStatus, OfflineContactStatus, DirectorStatus, ChatStoryEntry, NewsMark, PublicNewsEntry, WorldStoryEntries, LongChatMemory, LongChatMemorySnapshot, WorldNewsStatus, InspectorSnapshot, ConversationMemoryRevision, ConversationMemoryDraft, ConversationMemorySnapshot, ConversationMemorySources, WorldContentItem, SocialSnapshot, AvatarDigest, ContentEditorDraft, ContentBuilderJob, ChatMessage, StickerLibrary, StickerEntry, ChatMediaSettings, ChatReplyProgress, ChatMessagePage, ChatHistoryMatches, PendingPlayerSend, DirectTurnView, GroupTurnView, ReplyRecoveryView, ChatReplyAvailability, VoiceCardPreview, VoiceCard, VoiceCardPage, SpeechSettings, SpeechStatus, SpeechJob, SpeechPricing, ChatContextReports } from "./contracts.generated";
export type { ExampleWorldTemplate, CoverFace, CoverCrop, CoverImage, WorldCover, WorldCoverWrite, ContentExportFormat, FileExportRequest, ContentExportInfo, ChatExportInfo, Residency, ActivityLocation, ActivityCharacter, LocationDraft, ActivityCharacterDirectory, ProactiveContactStatus, ChatUnreadStatus, OfflineContactStatus, DirectorStatus, ChatStoryEntry, NewsMark, PublicNewsEntry, WorldStoryEntries, LongChatMemory, LongChatMemorySnapshot, WorldNewsStatus, InspectorSnapshot, ConversationMemoryContent, ConversationMemoryRevision, ConversationMemoryDraft, ConversationMemorySnapshot, ConversationMemorySources, WorldContentItem, SocialSnapshot, AvatarDigest, ContentEditorEntry, ContentEditorDraft, ContentBuilderJob, ChatMessage, StickerLibrary, StickerEntry, ChatMediaAttachment, ChatMediaSettings, ChatReplyProgress, ChatMessagePage, ChatHistoryMatches, PendingPlayerSend, DirectTurnView, GroupTurnView, ReplyRecoveryView, ChatReplyAvailability, VoiceManifest, VoiceCardPreview, VoiceCard, VoiceCardPage, SpeechSettings, SpeechStatus, SpeechJob, SpeechPricing, ChatContextReports } from "./contracts.generated";
import type { CreateWorldRequest, ClockScaleRequest, DeleteWorldRequest, ProfileWrite, BindPlayerRequest, AvailabilityRequest, CreateGroupRequest } from "./contracts.generated";
export type { LLMRuntimeStatus, CoreHealth, WorldSummary, WorldSettings, SelectablePlayer, PlayerAvailability, SelectedPlayerState, LocalProfile, KnownWorldEvent, ChatConversation, GroupChatConversation } from "./contracts.generated";
import type { CoreHealth, WorldSummary, WorldSettings, SelectablePlayer, PlayerAvailability, SelectedPlayerState, LocalProfile, KnownWorldEvent, ChatConversation, GroupChatConversation } from "./contracts.generated";








import { createParser } from "eventsource-parser";
import contract from "../../../services/core/src/livingworld/domain/api_contract.json";

export const API_PROTOCOL = contract.api_protocol;




export function fileExportPath(request: FileExportRequest): string {
  const segment = request.kind === "content" ? "content" : "conversations";
  const params = new URLSearchParams({ format: request.format, expected_digest: request.expected_digest });
  if (request.kind === "content") {
    params.set("reviewed_hash", request.reviewed_hash); params.set("content_id", request.content_id);
    params.set("use_regex", String(request.use_regex));
  } else {
    params.set("player_id", request.player_id); params.set("through_position", String(request.through_position));
  }
  return `/worlds/${encodeURIComponent(request.world_id)}/${segment}/${encodeURIComponent(request.item_id)}/export?${params}`;
}
export interface CoreConnection { endpoint: string; token: string; generation: string }

























export class CoreRequestError extends Error {
  constructor(public readonly status: number, public readonly code: string | null = null) {
    super(`product_request_failed_${status}`);
    this.name = "CoreRequestError";
  }
}






































export class CoreClient {
  mediaSettings(world: string, signal?: AbortSignal): Promise<ChatMediaSettings> { return this.contractRequest(`/worlds/${world}/media/settings`, isChatMediaSettings, { signal }); }
  saveMediaSettings(world: string, settings: ChatMediaSettings): Promise<ChatMediaSettings> { return this.contractRequest(`/worlds/${world}/media/settings`, isChatMediaSettings, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(settings satisfies Requests.ChatMediaSettings) }); }
  mediaUsage(world: string): Promise<MediaUsageResult> { return this.contractRequest(`/worlds/${world}/media/usage`, isMediaUsageResult); }
  stickers(world: string, library: StickerLibrary, root?: string, offset = 0, query = "", signal?: AbortSignal): Promise<StickersResult> {
    const params = new URLSearchParams({ library, offset: String(offset), query }); if (root) params.set("root", root);
    return this.contractRequest(`/worlds/${world}/media/stickers?${params}`, isStickersResult, { signal });
  }
  importSticker(world: string, library: StickerLibrary, file: File, description: string, root?: string): Promise<StickerEntry> {
    const params = new URLSearchParams({ library }); if (root) params.set("root", root);
    return this.contractRequest(`/worlds/${world}/media/stickers?${params}`, isStickerEntry, { method: "POST", headers: { "Content-Type": file.type || "application/octet-stream", "X-Media-Description": encodeURIComponent(description) }, body: file });
  }
  editSticker(world: string, entry: string, description: string): Promise<EditStickerResult> { return this.contractRequest(`/worlds/${world}/media/stickers/${entry}`, isEditStickerResult, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ description } satisfies Requests.HttpChatMediaStickerEdit) }); }
  removeSticker(world: string, entry: string): Promise<RemoveStickerResult> { return this.contractRequest(`/worlds/${world}/media/stickers/${entry}`, isRemoveStickerResult, { method: "DELETE" }); }
  mediaImage(world: string, asset: string, signal?: AbortSignal): Promise<Blob> { return this.productRequest(`/worlds/${world}/media/assets/${asset}`, { signal }, true); }
  captionMedia(world: string, asset: string, entry?: string): Promise<CaptionMediaResult> { return this.contractRequest(`/worlds/${world}/media/assets/${asset}/caption${entry ? `?entry_id=${encodeURIComponent(entry)}` : ""}`, isCaptionMediaResult, { method: "POST" }); }
  speechSettings(worldId: string, signal?: AbortSignal): Promise<SpeechStatus> {
    return this.contractRequest(`/worlds/${worldId}/speech`, isSpeechStatus, { signal });
  }
  saveSpeechSettings(worldId: string, settings: SpeechSettings, revision: number): Promise<SpeechStatus> {
    return this.contractRequest(`/worlds/${worldId}/speech`, isSpeechStatus, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ settings, expected_revision: revision } satisfies Requests.HttpSpeechSettingsWrite) });
  }
  speechPricing(worldId: string): Promise<SpeechPricing> { return this.contractRequest(`/worlds/${worldId}/speech/pricing`, isSpeechPricing); }
  voiceCards(worldId: string, offset = 0): Promise<VoiceCardPage> { return this.contractRequest(`/worlds/${worldId}/voices?offset=${offset}`, isVoiceCardPage); }
  voiceBinding(worldId: string, root: string): Promise<VoiceBindingResult> { return this.contractRequest(`/worlds/${worldId}/character-voices/${root}`, isVoiceBindingResult); }
  bindVoice(worldId: string, root: string, card: string | null): Promise<VoiceBindingResult> {
    return this.contractRequest(`/worlds/${worldId}/character-voices/${root}`, isVoiceBindingResult, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ card_id: card } satisfies Requests.HttpSpeechBindingWrite) });
  }
  previewVoiceCard(worldId: string, file: File, name: string): Promise<VoiceCardPreview> {
    return this.contractRequest(`/worlds/${worldId}/voices/preview?audio_format=${voiceFileFormat(file)}&name=${encodeURIComponent(name)}`, isVoiceCardPreview, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
  }
  importVoiceCard(worldId: string, file: File, name: string): Promise<VoiceCard> {
    return this.contractRequest(`/worlds/${worldId}/voices?audio_format=${voiceFileFormat(file)}&name=${encodeURIComponent(name)}`, isVoiceCard, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
  }
  voiceReference(worldId: string, card: string, signal?: AbortSignal): Promise<Blob> { return this.productRequest(`/worlds/${worldId}/voices/${card}/reference`, { signal }, true); }
  exportVoiceCard(worldId: string, card: string): Promise<Blob> { return this.productRequest(`/worlds/${worldId}/voices/${card}/export`, undefined, true); }
  removeVoiceCard(worldId: string, card: string): Promise<RemoveVoiceCardResult> { return this.contractRequest(`/worlds/${worldId}/voices/${card}`, isRemoveVoiceCardResult, { method: "DELETE" }); }
  generateSpeech(worldId: string, conversation: string, message: string, signal?: AbortSignal, requestId?: string): Promise<SpeechJob> {
    return this.contractRequest(`/worlds/${worldId}/conversations/${conversation}/messages/${message}/speech`, isSpeechJob, {
      method: "POST", signal,
      ...(requestId ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request_id: requestId } satisfies Requests.HttpSpeechGenerationRequest) } : {}),
    });
  }
  speechAudio(worldId: string, job: string, signal?: AbortSignal, inspectSignal = false): Promise<Blob> { return this.productRequest(`/worlds/${worldId}/speech/audio/${job}${inspectSignal ? "?inspect_signal=true" : ""}`, { signal }, true); }
  speechJob(worldId: string, job: string, signal?: AbortSignal): Promise<SpeechJob> { return this.contractRequest(`/worlds/${worldId}/speech/jobs/${job}`, isSpeechJob, { signal }); }
  regenerateSpeech(worldId: string, conversation: string, message: string, requestId: string, signal?: AbortSignal): Promise<SpeechJob> {
    return this.contractRequest(`/worlds/${worldId}/conversations/${conversation}/messages/${message}/speech/regenerate`, isSpeechJob, {
      method: "POST", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request_id: requestId } satisfies Requests.HttpSpeechGenerationRequest),
    });
  }
  speechPreviews(worldId: string, conversation: string, messages: string[], signal?: AbortSignal): Promise<SpeechPreviewsResult> {
    return this.contractRequest(`/worlds/${worldId}/conversations/${conversation}/speech/previews/query`, isSpeechPreviewsResult, {
      method: "POST", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message_ids: messages } satisfies Requests.HttpSpeechPreviewQuery),
    });
  }
  speechPreviewCompleted(worldId: string, job: string): Promise<SpeechJob> {
    return this.contractRequest(`/worlds/${worldId}/speech/previews/${job}/completed`, isSpeechJob, { method: "POST" });
  }
  decideSpeechPreview(worldId: string, job: string, decision: "replace" | "keep"): Promise<SpeechJob> {
    return this.contractRequest(`/worlds/${worldId}/speech/previews/${job}/decision`, isSpeechJob, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision } satisfies Requests.HttpSpeechPreviewDecision),
    });
  }
  private readonly endpoint: URL;
  constructor(private readonly connection: CoreConnection, private readonly fetcher = globalThis.fetch.bind(globalThis)) {
    this.endpoint = new URL(connection.endpoint);
    if (!(["http:", "https:"].includes(this.endpoint.protocol)) || this.endpoint.username ||
        this.endpoint.password || this.endpoint.pathname !== "/" || this.endpoint.search || this.endpoint.hash) {
      throw new Error("invalid_core_endpoint");
    }
    if (!connection.token || !connection.generation) throw new Error("missing_core_session");
  }

  async health(signal?: AbortSignal, worldId?: string): Promise<CoreHealth> {
    const url = new URL("/system/health", this.endpoint);
    if (worldId) url.searchParams.set("world_id", worldId);
    const response = await this.fetcher(url, {
      headers: { Authorization: `Bearer ${this.connection.token}` }, signal,
      credentials: "omit", cache: "no-store",
    });
    if (!response.ok) throw new Error("core_health_rejected");
    const health: unknown = await response.json();
    if (!isCoreHealth(health) || !health.ready || health.api_protocol !== API_PROTOCOL || health.generation !== this.connection.generation) {
      throw new Error("core_contract_mismatch");
    }
    return health;
  }

  async shutdown(requestId: string, signal?: AbortSignal): Promise<void> {
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(requestId)) {
      throw new Error("valid_request_id_required");
    }
    const response = await this.fetcher(new URL("/system/shutdown", this.endpoint), {
      method: "POST", headers: { Authorization: `Bearer ${this.connection.token}`, "X-Request-Id": requestId },
      signal, credentials: "omit",
    });
    if (!response.ok) throw new Error("core_shutdown_rejected");
  }

  private async contractRequest<T>(path: string, accepts: (value: unknown) => value is T, init?: RequestInit): Promise<T> {
    const value: unknown = await this.productRequest(path, init);
    if (!accepts(value)) throw new CoreRequestError(502, "core_contract_mismatch");
    return value;
  }

  private async developerRequest<T>(path: string, accepts: (value: unknown) => value is T, init?: RequestInit): Promise<T> {
    const response = await this.fetcher(new URL(path, this.endpoint), {
      ...init,
      headers: { Authorization: `Bearer ${this.connection.token}`, "Content-Type": "application/json", ...init?.headers },
      credentials: "omit", cache: "no-store",
    });
    if (!response.ok) throw new Error(`developer_request_failed_${response.status}`);
    const value: unknown = await response.json();
    if (!accepts(value)) throw new CoreRequestError(502, "core_contract_mismatch");
    return value;
  }

  private productRequest(path: string, init: RequestInit | undefined, download: true): Promise<Blob>;
  private productRequest(path: string, init?: RequestInit, download?: false): Promise<unknown>;
  private async productRequest(path: string, init?: RequestInit, download = false): Promise<unknown> {
    // Bound read-only requests, including body reads. Mutations and paid reply
    // requests retain their existing outcome/claim handling and are not replayed.
    const read = !init?.method || init.method.toUpperCase() === "GET";
    const controller = read ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), download ? 120_000 : 15_000) : undefined;
    // AbortController also works on older installed WebView2 runtimes.
    const externalSignal = init?.signal;
    const abortRead = () => controller?.abort();
    if (controller) {
      externalSignal?.addEventListener("abort", abortRead, { once: true });
      if (externalSignal?.aborted) controller.abort();
    }
    const signal = controller?.signal ?? externalSignal;
    try {
      const response = await this.fetcher(new URL(`/api/v${API_PROTOCOL}${path}`, this.endpoint), {
        ...init, signal,
        headers: { Authorization: `Bearer ${this.connection.token}`, ...init?.headers },
        credentials: "omit", cache: "no-store",
      });
      if (!response.ok) {
        // Keep only bounded machine labels; never expose arbitrary server details.
        const body: unknown = await response.json().catch(() => null);
        const code = typeof body === "object" && body !== null && "detail" in body
          && typeof body.detail === "string" && /^[a-z][a-z0-9_]{0,95}$/.test(body.detail)
          ? body.detail : null;
        throw new CoreRequestError(response.status, code);
      }
      if (download) {
        if (!response.body) throw new CoreRequestError(502, "export_download_failed");
        const reader = response.body.getReader(), chunks: Uint8Array<ArrayBuffer>[] = [];
        let size = 0;
        try {
          while (true) {
            const { done, value } = await reader.read(); if (done) break;
            size += value.byteLength;
            if (size > 128 * 1024 * 1024) throw new CoreRequestError(413, "export_browser_size_limit");
            chunks.push(new Uint8Array(value));
          }
          return new Blob(chunks, { type: response.headers.get("Content-Type") ?? "application/octet-stream" });
        } finally { await reader.cancel().catch(() => undefined); reader.releaseLock(); }
      }
      return await response.json();
    } catch (failure) {
      if (controller?.signal.aborted && !init?.signal?.aborted) throw new CoreRequestError(504, "core_read_timeout");
      throw failure;
    } finally {
      if (timer !== undefined) clearTimeout(timer);
      if (controller) externalSignal?.removeEventListener("abort", abortRead);
    }
  }

  async streamChatReply(
    worldId: string, conversationId: string, turnId: string, kind: "direct" | "group",
    onProgress: (event: ChatReplyProgress) => void, signal: AbortSignal,
  ): Promise<void> {
    const segment = kind === "group" ? "group-turns" : "turns";
    const path = `/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/${segment}/${encodeURIComponent(turnId)}/reply/stream`;
    // One authenticated POST. Parsing never reconnects or repeats generation.
    const response = await this.fetcher(new URL(`/api/v${API_PROTOCOL}${path}`, this.endpoint), {
      method: "POST", headers: { Authorization: `Bearer ${this.connection.token}`, Accept: "text/event-stream" },
      signal, credentials: "omit", cache: "no-store",
    });
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null);
      const code = typeof body === "object" && body !== null && "detail" in body
        && typeof body.detail === "string" && /^[a-z][a-z0-9_]{0,95}$/.test(body.detail) ? body.detail : null;
      throw new CoreRequestError(response.status, code);
    }
    const invalid = () => new CoreRequestError(502, "chat_reply_invalid");
    if (!response.body || !response.headers.get("Content-Type")?.startsWith("text/event-stream")) {
      await response.body?.cancel();
      throw invalid();
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8", { fatal: true });
    let completed = false;
    let bytes = 0;
    let eventCount = 0;
    let speaker: string | null = null;
    let textBytes = 0;
    let messageCount = 0;
    const encoder = new TextEncoder();
    const validId = (value: unknown): value is string => typeof value === "string" && /^[0-9a-f-]{36}$/i.test(value);
    const parser = createParser({
      maxBufferSize: 512 * 1024,
      onError: () => { throw invalid(); },
      onRetry: () => { throw invalid(); },
      onEvent: event => {
        if (completed || ++eventCount > 600_000) throw invalid();
        const frame: unknown = JSON.parse(event.data);
        if (typeof frame !== "object" || frame === null || !("turn_id" in frame) || frame.turn_id !== turnId || !("kind" in frame)) throw invalid();
        if (frame.kind === "error") {
          if (!("status" in frame) || typeof frame.status !== "number" || !Number.isInteger(frame.status) || frame.status < 400 || frame.status > 599
            || !("code" in frame) || typeof frame.code !== "string" || !/^[a-z][a-z0-9_]{0,95}$/.test(frame.code)) throw invalid();
          throw new CoreRequestError(frame.status, frame.code);
        }
        if (frame.kind === "completed") { completed = true; return; }
        if (!isChatReplyProgress(frame)) throw invalid();
        if (frame.kind === "preparing" || frame.kind === "selecting") {
          if (speaker !== null) throw invalid();
          onProgress({ kind: frame.kind }); return;
        }
        if (frame.kind === "replying") {
          if (speaker !== null || !("speaker_id" in frame) || !validId(frame.speaker_id)) throw invalid();
          speaker = frame.speaker_id; textBytes = 0;
          onProgress({ kind: "replying", speaker_id: speaker }); return;
        }
        if (frame.kind === "delta") {
          if (!("speaker_id" in frame) || frame.speaker_id !== speaker || !("text" in frame) || typeof frame.text !== "string" || speaker === null) throw invalid();
          textBytes += encoder.encode(frame.text).length;
          if (textBytes > 65536) throw invalid();
          onProgress({ kind: "delta", speaker_id: speaker, text: frame.text }); return;
        }
        if (frame.kind === "message" && "message" in frame && typeof frame.message === "object" && frame.message !== null) {
          const message = frame.message;
          if (!("message_id" in message) || !validId(message.message_id) || !("turn_id" in message) || message.turn_id !== turnId
            || !("conversation_id" in message) || message.conversation_id !== conversationId || !("sender_kind" in message) || message.sender_kind !== "character"
            || !("sender_id" in message) || !validId(message.sender_id) || (speaker !== null && message.sender_id !== speaker)
            || !("text" in message) || typeof message.text !== "string" || !message.text.trim() || encoder.encode(message.text).length > 65536
            || !("position" in message) || typeof message.position !== "number" || !Number.isSafeInteger(message.position) || message.position < 1
            || !("created_at_utc" in message) || typeof message.created_at_utc !== "string" || message.created_at_utc.length > 64 || !Number.isFinite(Date.parse(message.created_at_utc))
            || ++messageCount > (kind === "direct" ? 1 : 32)) throw invalid();
          speaker = null; textBytes = 0;
          onProgress({ kind: "message", message }); return;
        }
        throw invalid();
      },
    });
    try {
      while (!completed) {
        const part = await reader.read();
        if (part.done) break;
        bytes += part.value.byteLength;
        if (bytes > 64 * 1024 * 1024) throw invalid();
        parser.feed(decoder.decode(part.value, { stream: true }));
      }
      if (!completed) {
        parser.feed(decoder.decode());
        parser.reset({ consume: true });
      }
      if (!completed || speaker !== null || (kind === "direct" && messageCount !== 1)) {
        throw new CoreRequestError(502, "chat_stream_interrupted");
      }
    } finally {
      await reader.cancel().catch(() => undefined);
      reader.releaseLock();
    }
  }

  worldContent(worldId: string): Promise<WorldContentItem[]> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/content`, (value): value is WorldContentItem[] => Array.isArray(value) && value.every(isWorldContentItem));
  }
  setCommonLore(worldId: string, importId: string, entryId: string, common: boolean): Promise<SetCommonLoreResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/content/${encodeURIComponent(importId)}/entries/${encodeURIComponent(entryId)}/common`, isSetCommonLoreResult, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ common } satisfies Requests.HttpWorldContentLoreExposure),
    });
  }
  conversations(worldId: string, signal?: AbortSignal): Promise<ChatConversation[]> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations`, (value): value is ChatConversation[] => Array.isArray(value) && value.every(isChatConversation), { signal });
  }
  groupConversations(worldId: string, signal?: AbortSignal): Promise<GroupChatConversation[]> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/groups`, (value): value is GroupChatConversation[] => Array.isArray(value) && value.every(isGroupChatConversation), { signal });
  }
  createGroupConversation(worldId: string, importIds: string[], requestId: string): Promise<GroupChatConversation> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/groups`, isGroupChatConversation, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ import_ids: importIds } satisfies CreateGroupRequest),
    });
  }
  conversationMessages(worldId: string, conversationId: string): Promise<ChatMessage[]> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/messages`, (value): value is ChatMessage[] => Array.isArray(value) && value.every(isChatMessage));
  }
  conversationMessagePage(worldId: string, conversationId: string, beforePosition?: number, signal?: AbortSignal): Promise<ChatMessagePage> {
    const path = `/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/messages/page`;
    return this.contractRequest(`${path}${beforePosition === undefined ? "" : `?before_position=${beforePosition}`}`, isChatMessagePage, { signal });
  }
  chatMessageSource(worldId: string, conversationId: string, messageId: string, signal?: AbortSignal): Promise<ChatMessagePage> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/source`, isChatMessagePage, { signal });
  }
  searchChatHistory(worldId: string, conversationId: string, query: string, beforePosition?: number, signal?: AbortSignal): Promise<ChatHistoryMatches> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/messages/search`, isChatHistoryMatches, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, before_position: beforePosition } satisfies Requests.HttpChatMessagesChatHistorySearchRequest), signal,
    });
  }
  chatMessageContext(worldId: string, conversationId: string, position: number, signal?: AbortSignal): Promise<ChatMessagePage> {
    if (!Number.isSafeInteger(position) || position < 1 || !Number.isSafeInteger(position + 4)) throw new Error("chat_position_invalid");
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/messages/page?limit=7&before_position=${position + 4}`, isChatMessagePage, { signal });
  }
  longChatMemory(worldId: string, conversationId: string, characterId: string, query = "", before?: string, signal?: AbortSignal): Promise<LongChatMemorySnapshot> {
    const params = new URLSearchParams({ query }); if (before) params.set("before", before);
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/long-memory/${encodeURIComponent(characterId)}?${params}`, isLongChatMemorySnapshot, { signal });
  }
  configureLongChatMemory(worldId: string, conversationId: string, characterId: string, enabled: boolean, revision: number, signal?: AbortSignal): Promise<LongChatMemorySnapshot> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/long-memory/${encodeURIComponent(characterId)}/settings`, isLongChatMemorySnapshot, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled, expected_revision: revision } satisfies Requests.HttpLongChatMemoryCaptureRequest), signal });
  }
  markLongChatMemory(worldId: string, conversationId: string, characterId: string, entry: LongChatMemory, active: boolean, pinned: boolean, signal?: AbortSignal): Promise<LongChatMemorySnapshot> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/long-memory/${encodeURIComponent(characterId)}/${encodeURIComponent(entry.entry_id)}`, isLongChatMemorySnapshot, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ active, pinned, expected_revision: entry.revision } satisfies Requests.HttpLongChatMemoryMarkRequest), signal });
  }
  conversationMemory(worldId: string, conversationId: string, signal?: AbortSignal): Promise<ConversationMemorySnapshot> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/memory`, isConversationMemorySnapshot, { signal });
  }
  draftConversationMemory(worldId: string, conversationId: string, baseRevision: number, mode: "summarize" | "correct", requestId: string, signal?: AbortSignal): Promise<ConversationMemoryDraft> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/memory/drafts`, isConversationMemoryDraft, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ base_revision: baseRevision, mode } satisfies Requests.HttpConversationMemoryGenerateMemoryRequest), signal,
    });
  }
  previewConversationMemory(worldId: string, conversationId: string, draftId: string, content: string, signal?: AbortSignal): Promise<ConversationMemoryDraft> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/memory/preview`, isConversationMemoryDraft, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ draft_id: draftId, content } satisfies Requests.HttpConversationMemoryPreviewMemoryRequest), signal,
    });
  }
  commitConversationMemory(worldId: string, conversationId: string, draftId: string, reviewedHash: string, signal?: AbortSignal): Promise<ConversationMemoryRevision> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/memory/commit`, isConversationMemoryRevision, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ draft_id: draftId, reviewed_hash: reviewedHash } satisfies Requests.HttpConversationMemoryCommitMemoryRequest), signal,
    });
  }
  conversationMemoryRevision(worldId: string, conversationId: string, revision: number, signal?: AbortSignal): Promise<ConversationMemorySources> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/memory/revisions/${revision}`, isConversationMemorySources, { signal });
  }
  conversationMemoryDraftSources(worldId: string, conversationId: string, draftId: string, signal?: AbortSignal): Promise<ConversationMemoryDraftSourcesResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/memory/drafts/${encodeURIComponent(draftId)}/sources`, isConversationMemoryDraftSourcesResult, { signal });
  }
  sendPlayerMessage(worldId: string, conversationId: string, text: string, tokenCeiling: number, requestId: string, stickerEntryId?: string): Promise<PendingPlayerSend> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/messages`, isPendingPlayerSend, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ text, token_ceiling: tokenCeiling, ...(stickerEntryId ? { sticker_entry_id: stickerEntryId } : {}) } satisfies Requests.HttpChatMessagesPlayerMessageRequest),
    });
  }
  directReplyAvailability(worldId: string, signal?: AbortSignal): Promise<ChatReplyAvailability> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/reply-availability`, isChatReplyAvailability, { signal });
  }
  chatContextReports(worldId: string, conversationId: string, turnId: string, signal?: AbortSignal): Promise<ChatContextReports> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/context-reports/${encodeURIComponent(turnId)}`, isChatContextReports, { signal });
  }
  replyRecovery(worldId: string, conversationId: string, sourceTurnId: string, signal?: AbortSignal): Promise<ReplyRecoveryView> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/reply-recovery/${encodeURIComponent(sourceTurnId)}`, isReplyRecoveryView, { signal });
  }
  createReplyRecovery(worldId: string, conversationId: string, sourceTurnId: string, expectedAttemptId: string, ceiling: number, requestId: string, signal?: AbortSignal): Promise<CreateReplyRecoveryResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/reply-recovery/${encodeURIComponent(sourceTurnId)}`, isCreateReplyRecoveryResult, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ expected_attempt_id: expectedAttemptId, token_ceiling: ceiling } satisfies Requests.HttpChatMessagesReplyRecoveryRequest), signal,
    });
  }
  directTurn(worldId: string, conversationId: string, turnId: string): Promise<DirectTurnView> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/turns/${encodeURIComponent(turnId)}`, isDirectTurnView);
  }
  generateDirectReply(worldId: string, conversationId: string, turnId: string): Promise<DirectTurnView> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/turns/${encodeURIComponent(turnId)}/reply`, isDirectTurnView, { method: "POST" });
  }
  groupReplyAvailability(worldId: string, signal?: AbortSignal): Promise<ChatReplyAvailability> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/group-reply-availability`, isChatReplyAvailability, { signal });
  }
  sendGroupMessage(worldId: string, conversationId: string, text: string, tokenCeiling: number, requestId: string, stickerEntryId?: string): Promise<PendingPlayerSend> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/group-messages`, isPendingPlayerSend, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ text, token_ceiling: tokenCeiling, ...(stickerEntryId ? { sticker_entry_id: stickerEntryId } : {}) } satisfies Requests.HttpChatMessagesPlayerMessageRequest),
    });
  }
  groupTurn(worldId: string, conversationId: string, turnId: string): Promise<GroupTurnView> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/group-turns/${encodeURIComponent(turnId)}`, isGroupTurnView);
  }
  generateGroupReply(worldId: string, conversationId: string, turnId: string): Promise<GroupTurnView> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/group-turns/${encodeURIComponent(turnId)}/reply`, isGroupTurnView, { method: "POST" });
  }
  openDirectConversation(worldId: string, importId: string): Promise<ChatConversation> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/direct/${encodeURIComponent(importId)}`, isChatConversation, { method: "POST" });
  }
  previewWorldContent(worldId: string, kind: "character" | "lorebook", file: File, replacesImportId?: string): Promise<WorldContentItem> {
    const replacement = replacesImportId ? `&replaces_import_id=${encodeURIComponent(replacesImportId)}` : "";
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/content/preview?kind=${kind}${replacement}`, isWorldContentItem, {
      method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file,
    });
  }
  contentEditor(worldId: string, importId: string): Promise<ContentEditorResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/content/editor/${encodeURIComponent(importId)}`, isContentEditorResult);
  }
  contentEditorPage(worldId: string, importId: string, offset = 0): Promise<Requests.ContentEditorPage> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/content/editor/${encodeURIComponent(importId)}/page?offset=${offset}`, isContentEditorPage);
  }
  previewContentChanges(worldId: string, importId: string, patch: Requests.HttpContentEditorPagesEditorPatchRequest): Promise<WorldContentItem> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/content/editor/${encodeURIComponent(importId)}/preview-changes`, isWorldContentItem, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch),
    });
  }
  previewEditedContent(worldId: string, draft: ContentEditorDraft, replacesImportId?: string, generationId?: string): Promise<WorldContentItem> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/content/editor/preview`, isWorldContentItem, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft, replaces_import_id: replacesImportId ?? null, generation_id: generationId ?? null } satisfies Requests.HttpContentAuthoringDraftReview),
    });
  }
  generateContent(worldId: string, draftKind: "character" | "lorebook", query: string, requestId: string): Promise<ContentBuilderJob> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/content/editor/research`, isContentBuilderJob, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ kind: draftKind, query } satisfies Requests.HttpContentAuthoringResearchRequest),
    });
  }
  contentGenerationStatus(worldId: string, requestId: string): Promise<ContentBuilderJob> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/content/editor/research/${encodeURIComponent(requestId)}`, isContentBuilderJob);
  }

  commitWorldContent(worldId: string, preview: WorldContentItem, initialLocationId?: string): Promise<WorldContentItem> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/content/${preview.import_id}/commit`, isWorldContentItem, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reviewed_hash: preview.reviewed_hash, initial_location_id: initialLocationId } satisfies Requests.HttpWorldContentConfirmation),
    });
  }
  discardWorldContent(worldId: string, importId: string): Promise<DiscardWorldContentResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/content/${importId}/discard`, isDiscardWorldContentResult, { method: "POST" });
  }
  removeCharacterCard(worldId: string, importId: string): Promise<RemoveStickerResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/content/${encodeURIComponent(importId)}`, isRemoveStickerResult, { method: "DELETE" });
  }

  listActivityCharacters(worldId: string, signal?: AbortSignal): Promise<ActivityCharacterDirectory> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/activity-characters`, isActivityCharacterDirectory, { signal });
  }
  initializeCharacterActivity(worldId: string, playerId: string, characterId: string, locationId: string, requestId: string): Promise<InitializeCharacterActivityResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/activity-characters/${encodeURIComponent(characterId)}/initial-location`, isInitializeCharacterActivityResult, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ player_id: playerId, location_id: locationId } satisfies Requests.HttpCharacterActivitySetupInitialActivityRequest),
    });
  }
  listActivityLocations(worldId: string, signal?: AbortSignal): Promise<ActivityLocation[]> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/activity-locations`, (value): value is ActivityLocation[] => Array.isArray(value) && value.every(isActivityLocation), { signal });
  }
  createActivityLocation(worldId: string, name: string, requestId: string, options?: Omit<LocationDraft, "name">): Promise<ActivityLocation> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/activity-locations`, isActivityLocation, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ name, ...options } satisfies Requests.HttpWorldLocationsCreateLocationRequest),
    });
  }
  editActivityLocation(worldId: string, locationId: string, draft: LocationDraft, revision: number, requestId: string): Promise<ActivityLocation> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/activity-locations/${encodeURIComponent(locationId)}`, isActivityLocation, { method: "PUT", headers: { "Content-Type": "application/json", "X-Request-Id": requestId }, body: JSON.stringify({ ...draft, expected_revision: revision } satisfies Requests.HttpWorldLocationsEditLocationRequest) });
  }
  removeActivityLocation(worldId: string, locationId: string, revision: number): Promise<RemoveStickerResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/activity-locations/${encodeURIComponent(locationId)}`, isRemoveStickerResult, { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision: revision } satisfies Requests.HttpWorldLocationsRemoveLocationRequest) });
  }
  configureCharacterLocation(worldId: string, playerId: string, characterId: string, locationId: string, locked: boolean, revision: number | null, requestId: string, policyRevision = 0, residency: Residency = "strong"): Promise<InitializeCharacterActivityResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/activity-characters/${encodeURIComponent(characterId)}/location-policy`, isInitializeCharacterActivityResult, { method: "PUT", headers: { "Content-Type": "application/json", "X-Request-Id": requestId }, body: JSON.stringify({ player_id: playerId, location_id: locationId, locked, residency, expected_revision: revision, expected_policy_revision: policyRevision } satisfies Requests.HttpCharacterActivitySetupCharacterLocationRequest) });
  }
  listWorldCovers(signal?: AbortSignal): Promise<WorldCover[]> {
    return this.contractRequest("/world-covers", (value): value is WorldCover[] => Array.isArray(value) && value.every(isWorldCover), { signal });
  }
  worldCover(worldId: string, signal?: AbortSignal): Promise<WorldCover> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/cover`, isWorldCover, { signal });
  }
  saveWorldCover(worldId: string, cover: WorldCoverWrite, signal?: AbortSignal): Promise<WorldCover> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/cover`, isWorldCover, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cover satisfies Requests.HttpWorldCoversCoverWrite), signal,
    });
  }
  uploadCoverImage(worldId: string, file: File, signal?: AbortSignal): Promise<CoverImage> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/cover/images`, isCoverImage, {
      method: "POST", headers: { "Content-Type": file.type || "application/octet-stream" }, body: file, signal,
    });
  }
  async coverImage(worldId: string, digest: string, signal?: AbortSignal): Promise<Blob> {
    const response = await this.fetcher(new URL(`/api/v${API_PROTOCOL}/worlds/${encodeURIComponent(worldId)}/cover/images/${encodeURIComponent(digest)}`, this.endpoint), {
      headers: { Authorization: `Bearer ${this.connection.token}` }, credentials: "omit", cache: "no-store", signal,
    });
    if (!response.ok) throw new CoreRequestError(response.status, "cover_image_unavailable");
    return response.blob();
  }
  socialSnapshot(worldId: string, signal?: AbortSignal): Promise<SocialSnapshot> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/social`, isSocialSnapshot, { signal });
  }
  async avatarDigests(worldId: string, roots: string[], signal?: AbortSignal): Promise<AvatarDigest[]> {
    const identities = [...new Set(roots)].sort(), result: AvatarDigest[] = [];
    // Bound query size and read one batch at a time, independent of graph size.
    for (let offset = 0; offset < identities.length; offset += 128) {
      if (signal?.aborted) throw new DOMException("Avatar read cancelled", "AbortError");
      const query = new URLSearchParams();
      identities.slice(offset, offset + 128).forEach(root => query.append("root_import_id", root));
      result.push(...await this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/social/avatars?${query}`, (value): value is AvatarDigest[] => Array.isArray(value) && value.every(isAvatarDigest), { signal }));
    }
    return result;
  }
  createFaction(worldId: string, name: string, parentId: string | null): Promise<CreateFactionResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/social/factions`, isCreateFactionResult, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, parent_id: parentId } satisfies Requests.HttpFactionsFactionWrite) });
  }
  editFaction(worldId: string, factionId: string, name: string, parentId: string | null): Promise<EditStickerResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/social/factions/${encodeURIComponent(factionId)}`, isEditStickerResult, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, parent_id: parentId } satisfies Requests.HttpFactionsFactionWrite) });
  }
  removeFaction(worldId: string, factionId: string): Promise<EditStickerResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/social/factions/${encodeURIComponent(factionId)}`, isEditStickerResult, { method: "DELETE" });
  }
  setFactionMember(worldId: string, factionId: string, rootId: string, enabled: boolean, cutContacts = false): Promise<EditStickerResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/social/factions/${encodeURIComponent(factionId)}/members/${encodeURIComponent(rootId)}`, isEditStickerResult, enabled ? { method: "PUT" } : {
      method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cut_contacts: cutContacts } satisfies Requests.HttpFactionsFactionLeave),
    });
  }
  setCharacterAvatar(worldId: string, rootId: string, digest: string | null): Promise<EditStickerResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/social/avatars/${encodeURIComponent(rootId)}`, isEditStickerResult, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ digest } satisfies Requests.HttpFactionsAvatarWrite) });
  }
  listProductWorlds(signal?: AbortSignal): Promise<WorldSettings[]> { return this.contractRequest("/worlds", (value): value is WorldSettings[] => Array.isArray(value) && value.every(isWorldSettings), { signal }); }
  deleteWorld(worldId: string, expectedName: string): Promise<DeleteWorldResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}`, isDeleteWorldResult, {
      method: "DELETE", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmed: true, expected_name: expectedName } satisfies DeleteWorldRequest),
    });
  }
  contentExportInfo(worldId: string, item: WorldContentItem, format: ContentExportFormat, contentId: string, useRegex: boolean, signal?: AbortSignal): Promise<ContentExportInfo> {
    const params = new URLSearchParams({ format, reviewed_hash: item.reviewed_hash, content_id: contentId, use_regex: String(useRegex) });
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/content/${encodeURIComponent(item.import_id)}/export/info?${params}`, isContentExportInfo, { signal });
  }
  chatExportInfo(worldId: string, conversationId: string, signal?: AbortSignal): Promise<ChatExportInfo> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/export/info`, isChatExportInfo, { signal });
  }
  fileExport(request: FileExportRequest, signal?: AbortSignal): Promise<Blob> {
    return this.productRequest(fileExportPath(request), { signal }, true);
  }
  dissolveGroup(worldId: string, conversationId: string): Promise<DissolveGroupResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/groups/${encodeURIComponent(conversationId)}`, isDissolveGroupResult, { method: "DELETE" });
  }
  createWorld(name: string, requestId: string): Promise<CreateWorldResult> {
    return this.contractRequest("/worlds", isCreateWorldResult, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ name } satisfies CreateWorldRequest),
    });
  }

  exampleWorld(): Promise<ExampleWorldTemplate> {
    return this.contractRequest("/world-examples", isExampleWorldTemplate);
  }

  createExampleWorld(template: ExampleWorldTemplate, requestId: string, publicEntries: string[]): Promise<CreateWorldResult> {
    return this.contractRequest(`/world-examples/${encodeURIComponent(template.id)}`, isCreateWorldResult, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ confirmed: true, reviewed_hash: template.reviewed_hash, public_entries: publicEntries } satisfies Requests.HttpExampleWorldsExampleConfirmation),
    });
  }
  pauseProductWorld(worldId: string): Promise<PauseProductWorldResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/clock/pause`, isPauseProductWorldResult, { method: "POST" });
  }
  resumeProductWorld(worldId: string): Promise<PauseProductWorldResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/clock/resume`, isPauseProductWorldResult, { method: "POST" });
  }
  scaleProductWorld(worldId: string, scale: string): Promise<PauseProductWorldResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/clock/scale`, isPauseProductWorldResult, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scale } satisfies ClockScaleRequest),
    });
  }
  listPlayers(worldId: string): Promise<SelectablePlayer[]> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/players`, (value): value is SelectablePlayer[] => Array.isArray(value) && value.every(isSelectablePlayer));
  }
  selectedPlayer(worldId: string): Promise<SelectedPlayerState> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/me/player`, isSelectedPlayerState);
  }
  setPlayerAvailability(worldId: string, availability: PlayerAvailability, expectedRevision: number, requestId: string): Promise<SetPlayerAvailabilityResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/me/availability`, isSetPlayerAvailabilityResult, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ availability, expected_presence_revision: expectedRevision } satisfies AvailabilityRequest),
    });
  }
  bindPlayer(worldId: string, playerId: string): Promise<BindPlayerResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/me/player`, isBindPlayerResult, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ player_id: playerId } satisfies BindPlayerRequest),
    });
  }
  startAtHome(worldId: string): Promise<BindPlayerResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/me/start`, isBindPlayerResult, { method: "POST" });
  }
  knownEvents(worldId: string, signal?: AbortSignal): Promise<KnownWorldEvent[]> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/known-events`, (value): value is KnownWorldEvent[] => Array.isArray(value) && value.every(isKnownWorldEvent), { signal });
  }

  profile(worldId?: string): Promise<LocalProfile> {
    return this.contractRequest(`${worldId ? `/worlds/${encodeURIComponent(worldId)}` : ""}/me/profile`, isLocalProfile);
  }
  saveProfile(profile: LocalProfile, worldId?: string): Promise<LocalProfile> {
    return this.contractRequest(`${worldId ? `/worlds/${encodeURIComponent(worldId)}` : ""}/me/profile`, isLocalProfile, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: profile.name, description: profile.description, expected_revision: profile.revision } satisfies ProfileWrite),
    });
  }

  proactiveContactStatus(worldId: string, signal?: AbortSignal): Promise<ProactiveContactStatus> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/proactive-contact`, isProactiveContactStatus, { signal });
  }
  configureProactiveContact(worldId: string, status: ProactiveContactStatus, enabled: boolean, minutes: number, consent = false): Promise<ProactiveContactStatus> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/proactive-contact`, isProactiveContactStatus, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, interval_minutes: minutes, consent_background_usage: consent, expected_revision: status.revision, expected_player_id: status.player_id } satisfies Requests.HttpProactiveContactSettingsRequest) });
  }
  async chatUnread(worldId: string, signal?: AbortSignal): Promise<ChatUnreadStatus> {
    const items: ChatUnreadStatus["items"] = [];
    let cursor: string | null = null, first: ChatUnreadStatus | null = null;
    const seen = new Set<string>();
    do {
      const query = new URLSearchParams({ page: "true" });
      if (cursor) query.set("after", cursor);
      const value: ChatUnreadStatus = await this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/chat-unread?${query}`, isChatUnreadStatus, { signal });
      if (first && first.player_id !== value.player_id) throw new CoreRequestError(409, "proactive_player_changed");
      first ??= value;
      items.push(...value.items);
      cursor = value.next_after ?? null;
      if (cursor && seen.has(cursor)) throw new CoreRequestError(502, "unread_cursor_invalid");
      if (cursor) seen.add(cursor);
    } while (cursor);
    return { ...first!, items, next_after: null };
  }
  markConversationRead(worldId: string, conversationId: string, position: number): Promise<MarkConversationReadResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/read`, isMarkConversationReadResult, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ position } satisfies Requests.HttpProactiveContactReadRequest) });
  }
  offlineContactStatus(worldId: string): Promise<OfflineContactStatus> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/offline-contact`, isOfflineContactStatus);
  }
  configureOfflineContact(worldId: string, status: OfflineContactStatus, enabled: boolean, hours: number, consent = false): Promise<OfflineContactStatus> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/offline-contact`, isOfflineContactStatus, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, hours, consent_background_usage: consent, expected_revision: status.revision } satisfies Requests.HttpOfflineContactOfflineSettingRequest),
    });
  }
  markOfflineMessageRead(worldId: string, messageId: string): Promise<MarkConversationReadResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/offline-contact/messages/${encodeURIComponent(messageId)}/read`, isMarkConversationReadResult, { method: "POST" });
  }
  worldStories(worldId: string, before?: string): Promise<WorldStoryEntries> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/stories${before ? `?before=${encodeURIComponent(before)}` : ""}`, isWorldStoryEntries);
  }
  worldNewsStatus(worldId: string): Promise<WorldNewsStatus> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/stories/settings`, isWorldNewsStatus);
  }
  configureWorldNews(worldId: string, status: WorldNewsStatus, enabled: boolean, consent = false, replenish = false): Promise<WorldNewsStatus> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/stories/settings`, isWorldNewsStatus, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, consent_background_usage: consent, expected_revision: status.revision, replenish } satisfies Requests.HttpWorldStoryNewsSettingRequest),
    });
  }
  markWorldNews(worldId: string, entry: PublicNewsEntry, state: NewsMark): Promise<WorldNewsStatus> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/stories/news/${encodeURIComponent(entry.entry_id)}/mark`, isWorldNewsStatus, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state, expected_revision: entry.revision } satisfies Requests.HttpWorldStoryNewsMarkRequest),
    });
  }
  correctChatStory(worldId: string, entry: ChatStoryEntry, correction: string | null, hidden = false): Promise<EditStickerResult> {
    return this.contractRequest(`/worlds/${encodeURIComponent(worldId)}/stories/chat/${encodeURIComponent(entry.entry_id)}`, isEditStickerResult, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hidden, correction, expected_revision: entry.revision } satisfies Requests.HttpWorldStoryStoryCorrectionRequest),
    });
  }
  configureDirectorBatchSize(worldId: string, batchSize: number, revision: number): Promise<DirectorStatus> {
    return this.contractRequest(`/worlds/${worldId}/director/batch-size`, isDirectorStatus, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ batch_size: batchSize, expected_revision: revision } satisfies Requests.HttpDirectorBatchSizeRequest) });
  }
  configureCardLocation(worldId: string, importId: string, playerId: string, locationId: string, locked: boolean, revision: number | null, requestId: string, policyRevision = 0, residency: Residency = "strong"): Promise<InitializeCharacterActivityResult> {
    return this.contractRequest(`/worlds/${worldId}/activity-cards/${importId}/location-policy`, isInitializeCharacterActivityResult, { method: "PUT", headers: { "Content-Type": "application/json", "X-Request-Id": requestId }, body: JSON.stringify({ player_id: playerId, location_id: locationId, locked, expected_revision: revision, expected_policy_revision: policyRevision, residency } satisfies Requests.HttpCharacterActivitySetupCharacterLocationRequest) });
  }
  initializeCardLocation(worldId: string, importId: string, locationId: string): Promise<InitializeCharacterActivityResult> {
    return this.contractRequest(`/worlds/${worldId}/activity-cards/${importId}/initial-location`, isInitializeCharacterActivityResult, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ location_id: locationId } satisfies Requests.HttpCharacterActivitySetupCardInitialRequest) });
  }
  directorStatus(worldId: string): Promise<DirectorStatus> {
    return this.contractRequest(`/worlds/${worldId}/director`, isDirectorStatus);
  }
  configureDirector(worldId: string, status: DirectorStatus, enabled: boolean, consent = false, retry = false): Promise<DirectorStatus> {
    return this.contractRequest(`/worlds/${worldId}/director`, isDirectorStatus, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, consent_background_usage: consent, expected_revision: status.revision, retry } satisfies Requests.HttpDirectorDirectorSettingRequest),
    });
  }
  configureDirectorEncounters(worldId: string, status: DirectorStatus, enabled: boolean, consent = false): Promise<DirectorStatus> {
    return this.contractRequest(`/worlds/${worldId}/director/encounters`, isDirectorStatus, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, consent_background_usage: consent, expected_revision: status.encounter_revision } satisfies Requests.HttpDirectorEncounterSettingRequest),
    });
  }
  configureSharedActivities(worldId: string, status: DirectorStatus, enabled: boolean, consent = false): Promise<DirectorStatus> {
    return this.contractRequest(`/worlds/${worldId}/director/shared-activities`, isDirectorStatus, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled, consent_background_usage: consent, expected_revision: status.shared_activity_revision } satisfies Requests.HttpDirectorEncounterSettingRequest) });
  }
  listWorlds(): Promise<WorldSummary[]> { return this.developerRequest("/developer/worlds", (value): value is WorldSummary[] => Array.isArray(value) && value.every(isWorldSummary)); }
  createDemoWorld(): Promise<CreateWorldResult> {
    return this.developerRequest("/developer/demo-world", isCreateWorldResult, { method: "POST" });
  }
  snapshot(worldId: string, ownerCharacterId?: string): Promise<InspectorSnapshot> {
    const suffix = ownerCharacterId ? `?owner_character_id=${encodeURIComponent(ownerCharacterId)}` : "";
    return this.developerRequest(`/developer/worlds/${worldId}/snapshot${suffix}`, isInspectorSnapshot);
  }
  pauseWorld(worldId: string): Promise<PauseProductWorldResult> {
    return this.developerRequest(`/developer/worlds/${worldId}/clock/pause`, isPauseProductWorldResult, { method: "POST" });
  }
  resumeWorld(worldId: string): Promise<PauseProductWorldResult> {
    return this.developerRequest(`/developer/worlds/${worldId}/clock/resume`, isPauseProductWorldResult, { method: "POST" });
  }
  changeClockScale(worldId: string, scale: string): Promise<PauseProductWorldResult> {
    return this.developerRequest(`/developer/worlds/${worldId}/clock/scale`, isPauseProductWorldResult, { method: "POST", body: JSON.stringify({ scale } satisfies ClockScaleRequest) });
  }
  scheduleTrigger(worldId: string, delayMicroseconds: number, targetCharacterId: string): Promise<ScheduleTriggerResult> {
    return this.developerRequest(`/developer/worlds/${worldId}/triggers`, isScheduleTriggerResult, { method: "POST", body: JSON.stringify({ delay_microseconds: delayMicroseconds, target_character_id: targetCharacterId } satisfies Requests.HttpDeveloperTriggerRequest) });
  }
  movePlayer(worldId: string, playerId: string, destinationId: string): Promise<PauseProductWorldResult> {
    return this.developerRequest(`/developer/worlds/${worldId}/move-player`, isPauseProductWorldResult, { method: "POST", body: JSON.stringify({ player_id: playerId, destination_id: destinationId } satisfies Requests.HttpDeveloperMovePlayerRequest) });
  }
  recordMemory(worldId: string, ownerCharacterId: string, observationId: string, content: string): Promise<RecordMemoryResult> {
    return this.developerRequest(`/developer/worlds/${worldId}/memories`, isRecordMemoryResult, { method: "POST", body: JSON.stringify({ owner_character_id: ownerCharacterId, observation_id: observationId, content } satisfies Requests.HttpDeveloperRecordMemoryRequest) });
  }
}

function voiceFileFormat(file: File): string {
  const suffix = file.name.split(".").at(-1)?.toLowerCase();
  return suffix === "wav" || suffix === "mp3" ? suffix : "card";
}
