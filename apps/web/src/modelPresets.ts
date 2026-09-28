import catalog from "../../../services/core/src/livingworld/infrastructure/llm/model_presets.json";

export type ProviderKind = "openai-responses" | "anthropic" | "gemini" | "openai-compatible";
type ModelPreset = {
  provider_kind: string; model_id: string; base_urls: string[];
  context_tokens: number; input_tokens: number; output_tokens: number;
  bound_encoding: string | null;
};
export const modelPresets: ModelPreset[] = catalog.models;
export const presetsReviewedAt = catalog.reviewed_at;

export function findModelPreset(provider: ProviderKind, model: string, baseUrl: string) {
  return modelPresets.find(item => item.provider_kind === provider && item.model_id === model
    && (provider !== "openai-compatible" || item.base_urls.includes(baseUrl.replace(/\/+$/, ""))));
}
