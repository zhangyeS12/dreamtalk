export type CoverFace = "front" | "spine" | "back";
export type CoverCrop = { x: number; y: number; width: number; height: number; rotation: 0 | 90 | 180 | 270 };
export type CoverImage = { digest: string; size: number; media_type: string; width: number; height: number };
export type WorldCover = { world_id: string; mode: "text" | "image"; title: string; show_title: boolean;
  faces: Partial<Record<CoverFace, { source: CoverImage; display: CoverImage; crop: CoverCrop }>>; revision: number };
export type WorldCoverWrite = Pick<WorldCover, "mode" | "title" | "show_title"> & {
  faces: Partial<Record<CoverFace, { source_digest: string; crop: CoverCrop }>>; expected_revision: number };

import { createParser } from "eventsource-parser";
import contract from "../../../services/core/src/livingworld/domain/api_contract.json";

export const API_PROTOCOL = contract.api_protocol;
export interface CoreConnection { endpoint: string; token: string; generation: string }
export type LLMRuntimeStatus = "ready" | "partially_configured" | "unconfigured" | "degraded";
export interface CoreHealth {
  ready: boolean;
  core_version: string;
  api_protocol: number;
  generation: string;
  llm_status: LLMRuntimeStatus;
}
export interface WorldSummary { world_id: string; name: string }
export interface ActivityLocation { location_id: string; name: string; is_home: boolean }
export interface ActivityCharacter { character_id: string; name: string; initialized: boolean }
export interface ActivityCharacterDirectory { player_id: string | null; items: ActivityCharacter[] }
export interface WorldSettings extends WorldSummary {
  world_time: string;
  clock_state: "running" | "paused";
  time_scale: string;
  runtime_state: string;
}
export interface ProactiveContactStatus {
  player_id: string;
  enabled: boolean; consented: boolean; revision: number; interval_minutes: number;
  state: "off" | "idle" | "writing" | "attention" | "waiting_reply";
  error: string | null; model_available: boolean; waiting_conversation_id: string | null;
}
export interface ChatUnreadStatus {
  player_id: string;
  items: Array<{ conversation_id: string; latest_position: number; unread: number }>;
  waiting_conversation_id: string | null;
}
export interface OfflineContactStatus {
  enabled: boolean; consented: boolean; revision: number; hours: number;
  state: "off" | "idle" | "waiting" | "planning" | "writing" | "delivered" | "skipped" | "attention";
  error: string | null; last_online_at: string | null; model_available: boolean;
  unread: Array<{ message_id: string; conversation_id: string }>;
}
export interface DirectorStatus {
  enabled: boolean; revision: number; state: "off" | "idle" | "planning" | "ready" | "attention";
  error: string | null; consented: boolean; model_available: boolean; model: string | null;
  encounters_enabled: boolean; encounter_revision: number; encounters_consented: boolean;
  shared_activities_enabled: boolean; shared_activity_revision: number; shared_activities_consented: boolean;
}
export interface ChatStoryEntry {
  entry_id: string; character_id: string; character_name: string; conversation_id: string; message_id: string;
  kind: "activity" | "plan" | "rumor" | "invitation" | "change";
  title: string; quote: string; time_text: string | null; source_event_id: string | null; updates_entry_id: string | null;
  learned_at: string; learned_world_time: string | null; revision: number; correction: string | null;
}
export type NewsMark = "pending" | "experienced" | "skipped";
export interface PublicNewsEntry {
  entry_id: string; event_id: string; batch_id: string; title: string; body: string; time_text: string | null;
  published_at: string; occurred_at: string; state: NewsMark; revision: number;
}
export interface WorldStoryEntries { chat: ChatStoryEntry[]; news: PublicNewsEntry[]; next_before: string | null }
export interface LongChatMemory {
  entry_id: string; character_id: string; kind: "identity" | "preference" | "promise" | "experience";
  topic: string; content: string; quote: string; source_kind: "player" | "character"; source_sender_id: string;
  conversation_id: string; message_id: string; created_at: string; world_time: string | null;
  state: "active" | "forgotten" | "superseded"; pinned: boolean; revision: number; replaces: string | null;
}
export interface LongChatMemorySnapshot {
  enabled: boolean; settings_revision: number; items: LongChatMemory[]; next_cursor: string | null;
}

export interface WorldNewsStatus {
  enabled: boolean; consented: boolean; revision: number; state: "off" | "idle" | "generating" | "ready" | "attention";
  error: string | null; pending: number; batch_total: number; batch_processed: number;
  model_available: boolean; model: string | null;
}
export interface SelectablePlayer { player_id: string; name: string }
export type PlayerAvailability = "busy" | "available";
export interface SelectedPlayerState {
  player_id: string | null;
  availability: PlayerAvailability | null;
  presence_revision: number | null;
}
export interface LocalProfile { name: string; description: string; revision: number }
export class CoreRequestError extends Error {
  constructor(public readonly status: number, public readonly code: string | null = null) {
    super(`product_request_failed_${status}`);
    this.name = "CoreRequestError";
  }
}
export interface KnownWorldEvent {
  event_id: string;
  title: string;
  occurred_at: string;
  observed_at: string;
  ledger_position: number;
  description?: string | null;
  observation_channel?: "witnessed" | null;
}
export interface InspectorSnapshot {
  world: WorldSummary;
  clock: { world_time: string; state: "running" | "paused"; scale: string; revision: number };
  runtime_state: string;
  locations: Array<{ location_id: string; name: string }>;
  players: Array<{ player_id: string; name: string; location_id: string; activity: string; availability: string; revision: number }>;
  characters: Array<{ character_id: string; name: string; location_id: string | null }>;
  scenes: Array<{ scene_id: string; location_id: string; status: string; started_at: string; participants: Array<{ kind: string; principal_id: string; name: string; joined_at: string }> }>;
  triggers: Array<{ trigger_id: string; kind: string; status: string; priority: number; due_at: string }>;
  activations: Array<{ activation_id: string; target: string; kind: string; priority: number; due_at: string; fidelity: string | null; cause_count: number }>;
  events: Array<{ event_id: string; type: string; occurred_at: string; ledger_position: number }>;
  observations: Array<{ observation_id: string; principal_kind: string; principal_id: string; principal_name: string; event_id: string; channel: string; observed_at: string }>;
  memories: Array<{ memory_id: string; owner_character_id: string; content: string; experienced_from: string; experienced_to: string; formed_at: string; salience: number | null; evidence: Array<{ observation_id: string; observed_at: string }> }>;
}

export interface ConversationMemoryContent {
  base_revision: number; through_position: number; source_ids: string[];
  content: string | null; user_edited: boolean; created_at_utc: string;
}
export interface ConversationMemoryRevision extends ConversationMemoryContent { revision: number; content: string }
export interface ConversationMemoryDraft extends ConversationMemoryContent {
  draft_id: string; mode: "summarize" | "correct";
  state: "generating" | "ready" | "previewed" | "committed" | "failed" | "interrupted";
  reviewed_hash: string | null; committed_revision: number | null; error: string | null;
}
export interface ConversationMemorySnapshot {
  current: ConversationMemoryRevision | null; draft: ConversationMemoryDraft | null;
  latest_position: number; model_available: boolean;
}
export interface ConversationMemorySources { memory: ConversationMemoryRevision; sources: ChatMessage[] }

export interface WorldContentItem {
  import_id: string; replaces_import_id: string | null; kind: "character" | "lorebook"; reviewed_hash: string;
  characters: Array<{ id: string; name: string; description: string; personality: string; background: string; scenario: string; speech_guidance: string; creator_notes: string; tags: string[]; example_dialogue: string[]; authored_instructions: Record<string, unknown> }>;
  lorebooks: Array<{ id: string; name: string; description: string }>;
  entries: Array<{ id: string; title: string; keywords: string[]; secondary_keywords?: string[]; activation_summary?: string; planning_activation_summary?: string; content: string; enabled: boolean; common: boolean }>;
  warnings?: Array<{ code: string; path: string }>;
  research?: ContentResearch | null;
}
export interface SocialSnapshot {
  factions: Array<{ faction_id: string; parent_id: string | null; name: string }>;
  characters: Array<{ root_import_id: string; current_import_id: string; character_id: string; name: string; avatar_digest: string | null }>;
  memberships: Array<{ faction_id: string; root_import_id: string }>;
  connections: Array<{ first_root_import_id: string; second_root_import_id: string; faction_ids: string[] }>;
}

export interface ContentEditorEntry {
  source_entry_id: string | null; title: string; content: string; keywords: string[];
  secondary_keywords: string[]; enabled: boolean; constant: boolean;
  selective_logic: "AND_ANY" | "AND_ALL" | "NOT_ANY" | "NOT_ALL"; priority: number; order: number;
}
export interface ContentEditorDraft {
  kind: "character" | "lorebook"; name: string; description: string; personality: string;
  background: string; scenario: string; speech_guidance: string; first_message: string;
  creator_notes: string; tags: string[]; example_dialogue: string[]; entries: ContentEditorEntry[];
}
export interface ContentResearch {
  draft: ContentEditorDraft; query: string; user_edited: boolean;
  sources: Array<{ id: string; title: string; url: string; excerpt: string; retrieved_at: string }>;
  claims: Array<{ field: string; text: string; sources: string[]; status: "sourced" | "uncertain" | "creative" }>;
  conflicts: string[]; uncertainties: string[];
}
export interface ContentBuilderJob {
  request_id: string; state: "searching" | "generating" | "ready" | "failed" | "interrupted";
  result: ContentResearch | null; error: string | null;
}

export interface ChatConversation {
  conversation_id: string;
  player_id: string;
  character_id: string;
  root_import_id: string;
  character_name: string;
  kind: "direct";
}
export interface GroupChatConversation {
  conversation_id: string;
  player_id: string;
  kind: "group";
  participants: Array<{ character_id: string; root_import_id: string; character_name: string }>;
}
export interface ChatMessage {
  message_id: string;
  turn_id: string;
  conversation_id: string;
  position: number;
  sender_kind: "player" | "character";
  sender_id: string;
  text: string;
  created_at_utc: string;
  story_sent_at_utc?: string | null;
}
export type ChatReplyProgress =
  | { kind: "preparing" | "selecting" }
  | { kind: "replying"; speaker_id: string }
  | { kind: "delta"; speaker_id: string; text: string }
  | { kind: "message"; message: ChatMessage };

export interface ChatMessagePage {
  items: ChatMessage[];
  next_before_position: number | null;
}
export interface ChatHistoryMatches {
  items: ChatMessage[];
  scanned_count: number;
  skipped_count: number;
  next_before_position: number | null;
}
export interface PendingPlayerSend {
  turn_id: string;
  token_ceiling: number;
  status: "pending";
  message: ChatMessage;
}
export interface DirectTurnView {
  turn_id: string;
  state: "pending" | "claimed" | "completed";
  token_ceiling: number;
  player_message: ChatMessage;
  reply: ChatMessage | null;
}
export interface GroupTurnView {
  turn_id: string;
  state: "pending" | "claimed" | "completed";
  token_ceiling: number;
  player_message: ChatMessage;
  replies: ChatMessage[];
}

export interface ReplyRecoveryView {
  source_turn_id: string;
  attempt_turn_id: string;
  state: "pending" | "running" | "completed" | "failed" | "unknown" | "interrupted" | "has_replies";
  token_ceiling: number;
  can_generate: boolean;
  can_create: boolean;
  reason: string | null;
}

export interface ChatReplyAvailability {
  available: boolean;
  input_token_reservation?: number | null;
  max_output_tokens?: number | null;
}

export class CoreClient {
  private readonly endpoint: URL;
  constructor(private readonly connection: CoreConnection, private readonly fetcher = globalThis.fetch.bind(globalThis)) {
    this.endpoint = new URL(connection.endpoint);
    if (!(["http:", "https:"].includes(this.endpoint.protocol)) || this.endpoint.username ||
        this.endpoint.password || this.endpoint.pathname !== "/" || this.endpoint.search || this.endpoint.hash) {
      throw new Error("invalid_core_endpoint");
    }
    if (!connection.token || !connection.generation) throw new Error("missing_core_session");
  }

  async health(signal?: AbortSignal): Promise<CoreHealth> {
    const response = await this.fetcher(new URL("/system/health", this.endpoint), {
      headers: { Authorization: `Bearer ${this.connection.token}` }, signal,
      credentials: "omit", cache: "no-store",
    });
    if (!response.ok) throw new Error("core_health_rejected");
    const health: unknown = await response.json();
    if (typeof health !== "object" || health === null || !("ready" in health) ||
        health.ready !== true || !("api_protocol" in health) || health.api_protocol !== API_PROTOCOL ||
        !("generation" in health) || health.generation !== this.connection.generation ||
        !("core_version" in health) || typeof health.core_version !== "string" ||
        !("llm_status" in health) || !["ready", "partially_configured", "unconfigured", "degraded"].includes(String(health.llm_status))) {
      throw new Error("core_contract_mismatch");
    }
    return health as CoreHealth;
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

  private async developerRequest<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await this.fetcher(new URL(path, this.endpoint), {
      ...init,
      headers: { Authorization: `Bearer ${this.connection.token}`, "Content-Type": "application/json", ...init?.headers },
      credentials: "omit", cache: "no-store",
    });
    if (!response.ok) throw new Error(`developer_request_failed_${response.status}`);
    return await response.json() as T;
  }

  private async productRequest<T>(path: string, init?: RequestInit): Promise<T> {
    // Bound read-only requests, including body reads. Mutations and paid reply
    // requests retain their existing outcome/claim handling and are not replayed.
    const read = !init?.method || init.method.toUpperCase() === "GET";
    const controller = read ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), 15_000) : undefined;
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
      return await response.json() as T;
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
          onProgress({ kind: "message", message: message as ChatMessage }); return;
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
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/content`);
  }
  setCommonLore(worldId: string, importId: string, entryId: string, common: boolean): Promise<{ common: boolean }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/content/${encodeURIComponent(importId)}/entries/${encodeURIComponent(entryId)}/common`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ common }),
    });
  }
  conversations(worldId: string, signal?: AbortSignal): Promise<ChatConversation[]> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations`, { signal });
  }
  groupConversations(worldId: string, signal?: AbortSignal): Promise<GroupChatConversation[]> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/groups`, { signal });
  }
  createGroupConversation(worldId: string, importIds: string[], requestId: string): Promise<GroupChatConversation> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/groups`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ import_ids: importIds }),
    });
  }
  conversationMessages(worldId: string, conversationId: string): Promise<ChatMessage[]> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/messages`);
  }
  conversationMessagePage(worldId: string, conversationId: string, beforePosition?: number, signal?: AbortSignal): Promise<ChatMessagePage> {
    const path = `/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/messages/page`;
    return this.productRequest(`${path}${beforePosition === undefined ? "" : `?before_position=${beforePosition}`}`, { signal });
  }
  chatMessageSource(worldId: string, conversationId: string, messageId: string, signal?: AbortSignal): Promise<ChatMessagePage> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/source`, { signal });
  }
  searchChatHistory(worldId: string, conversationId: string, query: string, beforePosition?: number, signal?: AbortSignal): Promise<ChatHistoryMatches> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/messages/search`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, before_position: beforePosition }), signal,
    });
  }
  chatMessageContext(worldId: string, conversationId: string, position: number, signal?: AbortSignal): Promise<ChatMessagePage> {
    if (!Number.isSafeInteger(position) || position < 1 || !Number.isSafeInteger(position + 4)) throw new Error("chat_position_invalid");
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/messages/page?limit=7&before_position=${position + 4}`, { signal });
  }
  longChatMemory(worldId: string, conversationId: string, characterId: string, query = "", before?: string, signal?: AbortSignal): Promise<LongChatMemorySnapshot> {
    const params = new URLSearchParams({ query }); if (before) params.set("before", before);
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/long-memory/${encodeURIComponent(characterId)}?${params}`, { signal });
  }
  configureLongChatMemory(worldId: string, conversationId: string, characterId: string, enabled: boolean, revision: number, signal?: AbortSignal): Promise<LongChatMemorySnapshot> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/long-memory/${encodeURIComponent(characterId)}/settings`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled, expected_revision: revision }), signal });
  }
  markLongChatMemory(worldId: string, conversationId: string, characterId: string, entry: LongChatMemory, active: boolean, pinned: boolean, signal?: AbortSignal): Promise<LongChatMemorySnapshot> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/long-memory/${encodeURIComponent(characterId)}/${encodeURIComponent(entry.entry_id)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ active, pinned, expected_revision: entry.revision }), signal });
  }
  conversationMemory(worldId: string, conversationId: string, signal?: AbortSignal): Promise<ConversationMemorySnapshot> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/memory`, { signal });
  }
  draftConversationMemory(worldId: string, conversationId: string, baseRevision: number, mode: "summarize" | "correct", requestId: string, signal?: AbortSignal): Promise<ConversationMemoryDraft> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/memory/drafts`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ base_revision: baseRevision, mode }), signal,
    });
  }
  previewConversationMemory(worldId: string, conversationId: string, draftId: string, content: string, signal?: AbortSignal): Promise<ConversationMemoryDraft> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/memory/preview`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ draft_id: draftId, content }), signal,
    });
  }
  commitConversationMemory(worldId: string, conversationId: string, draftId: string, reviewedHash: string, signal?: AbortSignal): Promise<ConversationMemoryRevision> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/memory/commit`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ draft_id: draftId, reviewed_hash: reviewedHash }), signal,
    });
  }
  conversationMemoryRevision(worldId: string, conversationId: string, revision: number, signal?: AbortSignal): Promise<ConversationMemorySources> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/memory/revisions/${revision}`, { signal });
  }
  conversationMemoryDraftSources(worldId: string, conversationId: string, draftId: string, signal?: AbortSignal): Promise<{ items: ChatMessage[] }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/memory/drafts/${encodeURIComponent(draftId)}/sources`, { signal });
  }
  sendPlayerMessage(worldId: string, conversationId: string, text: string, tokenCeiling: number, requestId: string): Promise<PendingPlayerSend> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ text, token_ceiling: tokenCeiling }),
    });
  }
  directReplyAvailability(worldId: string, signal?: AbortSignal): Promise<ChatReplyAvailability> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/reply-availability`, { signal });
  }
  chatContextReports(worldId: string, conversationId: string, turnId: string, signal?: AbortSignal): Promise<ChatContextReports> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/context-reports/${encodeURIComponent(turnId)}`, { signal });
  }
  replyRecovery(worldId: string, conversationId: string, sourceTurnId: string, signal?: AbortSignal): Promise<ReplyRecoveryView> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/reply-recovery/${encodeURIComponent(sourceTurnId)}`, { signal });
  }
  createReplyRecovery(worldId: string, conversationId: string, sourceTurnId: string, expectedAttemptId: string, ceiling: number, requestId: string, signal?: AbortSignal): Promise<{ turn_id: string; token_ceiling: number }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/reply-recovery/${encodeURIComponent(sourceTurnId)}`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ expected_attempt_id: expectedAttemptId, token_ceiling: ceiling }), signal,
    });
  }
  directTurn(worldId: string, conversationId: string, turnId: string): Promise<DirectTurnView> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/turns/${encodeURIComponent(turnId)}`);
  }
  generateDirectReply(worldId: string, conversationId: string, turnId: string): Promise<DirectTurnView> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/turns/${encodeURIComponent(turnId)}/reply`, { method: "POST" });
  }
  groupReplyAvailability(worldId: string, signal?: AbortSignal): Promise<ChatReplyAvailability> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/group-reply-availability`, { signal });
  }
  sendGroupMessage(worldId: string, conversationId: string, text: string, tokenCeiling: number, requestId: string): Promise<PendingPlayerSend> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/group-messages`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ text, token_ceiling: tokenCeiling }),
    });
  }
  groupTurn(worldId: string, conversationId: string, turnId: string): Promise<GroupTurnView> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/group-turns/${encodeURIComponent(turnId)}`);
  }
  generateGroupReply(worldId: string, conversationId: string, turnId: string): Promise<GroupTurnView> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/group-turns/${encodeURIComponent(turnId)}/reply`, { method: "POST" });
  }
  openDirectConversation(worldId: string, importId: string): Promise<ChatConversation> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/direct/${encodeURIComponent(importId)}`, { method: "POST" });
  }
  previewWorldContent(worldId: string, kind: "character" | "lorebook", file: File, replacesImportId?: string): Promise<WorldContentItem> {
    const replacement = replacesImportId ? `&replaces_import_id=${encodeURIComponent(replacesImportId)}` : "";
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/content/preview?kind=${kind}${replacement}`, {
      method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file,
    });
  }
  contentEditor(worldId: string, importId: string): Promise<{ draft: ContentEditorDraft; research: ContentResearch | null }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/content/editor/${encodeURIComponent(importId)}`);
  }
  previewEditedContent(worldId: string, draft: ContentEditorDraft, replacesImportId?: string, generationId?: string): Promise<WorldContentItem> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/content/editor/preview`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft, replaces_import_id: replacesImportId ?? null, generation_id: generationId ?? null }),
    });
  }
  generateContent(worldId: string, draftKind: "character" | "lorebook", query: string, requestId: string): Promise<ContentBuilderJob> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/content/editor/research`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ kind: draftKind, query }),
    });
  }
  contentGenerationStatus(worldId: string, requestId: string): Promise<ContentBuilderJob> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/content/editor/research/${encodeURIComponent(requestId)}`);
  }

  commitWorldContent(worldId: string, preview: WorldContentItem): Promise<WorldContentItem> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/content/${preview.import_id}/commit`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reviewed_hash: preview.reviewed_hash }),
    });
  }
  discardWorldContent(worldId: string, importId: string): Promise<{ discarded: boolean }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/content/${importId}/discard`, { method: "POST" });
  }

  listActivityCharacters(worldId: string): Promise<ActivityCharacterDirectory> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/activity-characters`);
  }
  initializeCharacterActivity(worldId: string, playerId: string, characterId: string, locationId: string, requestId: string): Promise<{ character_id: string; initialized: boolean }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/activity-characters/${encodeURIComponent(characterId)}/initial-location`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ player_id: playerId, location_id: locationId }),
    });
  }
  listActivityLocations(worldId: string): Promise<ActivityLocation[]> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/activity-locations`);
  }
  createActivityLocation(worldId: string, name: string, requestId: string): Promise<ActivityLocation> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/activity-locations`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ name }),
    });
  }
  listWorldCovers(signal?: AbortSignal): Promise<WorldCover[]> {
    return this.productRequest("/world-covers", { signal });
  }
  worldCover(worldId: string, signal?: AbortSignal): Promise<WorldCover> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/cover`, { signal });
  }
  saveWorldCover(worldId: string, cover: WorldCoverWrite, signal?: AbortSignal): Promise<WorldCover> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/cover`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cover), signal,
    });
  }
  uploadCoverImage(worldId: string, file: File, signal?: AbortSignal): Promise<CoverImage> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/cover/images`, {
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
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/social`, { signal });
  }
  createFaction(worldId: string, name: string, parentId: string | null): Promise<{ faction_id: string }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/social/factions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, parent_id: parentId }) });
  }
  editFaction(worldId: string, factionId: string, name: string, parentId: string | null): Promise<{ saved: boolean }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/social/factions/${encodeURIComponent(factionId)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, parent_id: parentId }) });
  }
  removeFaction(worldId: string, factionId: string): Promise<{ saved: boolean }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/social/factions/${encodeURIComponent(factionId)}`, { method: "DELETE" });
  }
  setFactionMember(worldId: string, factionId: string, rootId: string, enabled: boolean): Promise<{ saved: boolean }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/social/factions/${encodeURIComponent(factionId)}/members/${encodeURIComponent(rootId)}`, { method: enabled ? "PUT" : "DELETE" });
  }
  setCharacterAvatar(worldId: string, rootId: string, digest: string | null): Promise<{ saved: boolean }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/social/avatars/${encodeURIComponent(rootId)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ digest }) });
  }
  listProductWorlds(signal?: AbortSignal): Promise<WorldSettings[]> { return this.productRequest("/worlds", { signal }); }
  createWorld(name: string, requestId: string): Promise<{ world_id: string }> {
    return this.productRequest("/worlds", {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ name }),
    });
  }
  pauseProductWorld(worldId: string): Promise<{ ok: boolean }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/clock/pause`, { method: "POST" });
  }
  resumeProductWorld(worldId: string): Promise<{ ok: boolean }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/clock/resume`, { method: "POST" });
  }
  scaleProductWorld(worldId: string, scale: string): Promise<{ ok: boolean }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/clock/scale`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scale }),
    });
  }
  listPlayers(worldId: string): Promise<SelectablePlayer[]> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/players`);
  }
  selectedPlayer(worldId: string): Promise<SelectedPlayerState> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/me/player`);
  }
  setPlayerAvailability(worldId: string, availability: PlayerAvailability, expectedRevision: number, requestId: string): Promise<{ availability: PlayerAvailability; presence_revision: number }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/me/availability`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": requestId },
      body: JSON.stringify({ availability, expected_presence_revision: expectedRevision }),
    });
  }
  bindPlayer(worldId: string, playerId: string): Promise<{ player_id: string }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/me/player`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ player_id: playerId }),
    });
  }
  startAtHome(worldId: string): Promise<{ player_id: string }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/me/start`, { method: "POST" });
  }
  knownEvents(worldId: string): Promise<KnownWorldEvent[]> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/known-events`);
  }

  profile(worldId?: string): Promise<LocalProfile> {
    return this.productRequest(`${worldId ? `/worlds/${encodeURIComponent(worldId)}` : ""}/me/profile`);
  }
  saveProfile(profile: LocalProfile, worldId?: string): Promise<LocalProfile> {
    return this.productRequest(`${worldId ? `/worlds/${encodeURIComponent(worldId)}` : ""}/me/profile`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: profile.name, description: profile.description, expected_revision: profile.revision }),
    });
  }

  proactiveContactStatus(worldId: string, signal?: AbortSignal): Promise<ProactiveContactStatus> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/proactive-contact`, { signal });
  }
  configureProactiveContact(worldId: string, status: ProactiveContactStatus, enabled: boolean, minutes: number, consent = false): Promise<ProactiveContactStatus> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/proactive-contact`, { method: "POST",
      body: JSON.stringify({ enabled, interval_minutes: minutes, consent_background_usage: consent, expected_revision: status.revision, expected_player_id: status.player_id }) });
  }
  chatUnread(worldId: string, signal?: AbortSignal): Promise<ChatUnreadStatus> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/chat-unread`, { signal });
  }
  markConversationRead(worldId: string, conversationId: string, position: number): Promise<{ read: boolean }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/conversations/${encodeURIComponent(conversationId)}/read`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ position }) });
  }
  offlineContactStatus(worldId: string): Promise<OfflineContactStatus> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/offline-contact`);
  }
  configureOfflineContact(worldId: string, status: OfflineContactStatus, enabled: boolean, hours: number, consent = false): Promise<OfflineContactStatus> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/offline-contact`, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, hours, consent_background_usage: consent, expected_revision: status.revision }),
    });
  }
  markOfflineMessageRead(worldId: string, messageId: string): Promise<{ read: boolean }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/offline-contact/messages/${encodeURIComponent(messageId)}/read`, { method: "POST" });
  }
  worldStories(worldId: string, before?: string): Promise<WorldStoryEntries> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/stories${before ? `?before=${encodeURIComponent(before)}` : ""}`);
  }
  worldNewsStatus(worldId: string): Promise<WorldNewsStatus> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/stories/settings`);
  }
  configureWorldNews(worldId: string, status: WorldNewsStatus, enabled: boolean, consent = false, replenish = false): Promise<WorldNewsStatus> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/stories/settings`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, consent_background_usage: consent, expected_revision: status.revision, replenish }),
    });
  }
  markWorldNews(worldId: string, entry: PublicNewsEntry, state: NewsMark): Promise<WorldNewsStatus> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/stories/news/${encodeURIComponent(entry.entry_id)}/mark`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state, expected_revision: entry.revision }),
    });
  }
  correctChatStory(worldId: string, entry: ChatStoryEntry, correction: string | null, hidden = false): Promise<{ saved: boolean }> {
    return this.productRequest(`/worlds/${encodeURIComponent(worldId)}/stories/chat/${encodeURIComponent(entry.entry_id)}`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hidden, correction, expected_revision: entry.revision }),
    });
  }
  directorStatus(worldId: string): Promise<DirectorStatus> {
    return this.productRequest(`/worlds/${worldId}/director`);
  }
  configureDirector(worldId: string, status: DirectorStatus, enabled: boolean, consent = false, retry = false): Promise<DirectorStatus> {
    return this.productRequest(`/worlds/${worldId}/director`, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, consent_background_usage: consent, expected_revision: status.revision, retry }),
    });
  }
  configureDirectorEncounters(worldId: string, status: DirectorStatus, enabled: boolean, consent = false): Promise<DirectorStatus> {
    return this.productRequest(`/worlds/${worldId}/director/encounters`, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, consent_background_usage: consent, expected_revision: status.encounter_revision }),
    });
  }
  configureSharedActivities(worldId: string, status: DirectorStatus, enabled: boolean, consent = false): Promise<DirectorStatus> {
    return this.productRequest(`/worlds/${worldId}/director/shared-activities`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled, consent_background_usage: consent, expected_revision: status.shared_activity_revision }) });
  }
  listWorlds(): Promise<WorldSummary[]> { return this.developerRequest("/developer/worlds"); }
  createDemoWorld(): Promise<{ world_id: string }> {
    return this.developerRequest("/developer/demo-world", { method: "POST" });
  }
  snapshot(worldId: string, ownerCharacterId?: string): Promise<InspectorSnapshot> {
    const suffix = ownerCharacterId ? `?owner_character_id=${encodeURIComponent(ownerCharacterId)}` : "";
    return this.developerRequest(`/developer/worlds/${worldId}/snapshot${suffix}`);
  }
  pauseWorld(worldId: string): Promise<{ ok: boolean }> {
    return this.developerRequest(`/developer/worlds/${worldId}/clock/pause`, { method: "POST" });
  }
  resumeWorld(worldId: string): Promise<{ ok: boolean }> {
    return this.developerRequest(`/developer/worlds/${worldId}/clock/resume`, { method: "POST" });
  }
  changeClockScale(worldId: string, scale: string): Promise<{ ok: boolean }> {
    return this.developerRequest(`/developer/worlds/${worldId}/clock/scale`, { method: "POST", body: JSON.stringify({ scale }) });
  }
  scheduleTrigger(worldId: string, delayMicroseconds: number, targetCharacterId: string): Promise<{ trigger_id: string }> {
    return this.developerRequest(`/developer/worlds/${worldId}/triggers`, { method: "POST", body: JSON.stringify({ delay_microseconds: delayMicroseconds, target_character_id: targetCharacterId }) });
  }
  movePlayer(worldId: string, playerId: string, destinationId: string): Promise<{ ok: boolean }> {
    return this.developerRequest(`/developer/worlds/${worldId}/move-player`, { method: "POST", body: JSON.stringify({ player_id: playerId, destination_id: destinationId }) });
  }
  recordMemory(worldId: string, ownerCharacterId: string, observationId: string, content: string): Promise<{ memory_id: string }> {
    return this.developerRequest(`/developer/worlds/${worldId}/memories`, { method: "POST", body: JSON.stringify({ owner_character_id: ownerCharacterId, observation_id: observationId, content }) });
  }
}

export type ChatContextReports = { turn_id: string; reports: {
  speaker_id: string; version: number; input_upper_bound: number; output_upper_bound: number;
  remaining_before_call: number; retrieval: string; context_reduced: boolean; references_omitted: number;
  categories: { label: string; included: number; omitted: number }[];
  references: { kind: string; id: string | null; text: string; source: string; time: string; source_kind: string; source_sender_id: string }[];
}[] };
