import { useCallback, useEffect, useMemo, useState } from "react";
import type { ChatVisuals, CoreClient } from "@dreamtalk/api-client";

export type ChatExpression = ChatVisuals["expressions"][number]["expression"];

export const CHAT_EXPRESSIONS: ReadonlyArray<{ value: ChatExpression; label: string }> = [
  { value: "neutral", label: "平静" },
  { value: "joy", label: "开心" },
  { value: "content", label: "满足" },
  { value: "sad", label: "难过" },
  { value: "angry", label: "生气" },
  { value: "surprised", label: "惊讶" },
  { value: "scared", label: "害怕" },
  { value: "disgusted", label: "嫌弃" },
  { value: "confused", label: "困惑" },
  { value: "love", label: "心动" },
  { value: "embarrassed", label: "害羞" },
  { value: "thinking", label: "思考" },
];

export type ChatVisualState = {
  visuals: ChatVisuals | null;
  urls: Record<string, string>;
  loading: boolean;
  error: string;
  refresh: () => void;
  replace: (next: ChatVisuals) => void;
};

export function useChatVisuals(client: CoreClient, worldId: string, visible: boolean): ChatVisualState {
  const [visuals, setVisuals] = useState<ChatVisuals | null>(null);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  const replace = useCallback((next: ChatVisuals) => { setVisuals(next); setError(""); }, []);

  useEffect(() => {
    if (!visible) return;
    const abort = new AbortController();
    let active = true;
    setLoading(true); setError("");
    void client.chatVisuals(worldId, abort.signal).then(next => {
      if (active) setVisuals(next);
    }).catch(() => {
      if (active) setError("聊天视觉配置暂未读取，请稍后重试。");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; abort.abort(); };
  }, [client, worldId, visible, revision]);

  const digestKey = useMemo(() => {
    if (!visuals) return "";
    return [...new Set([
      ...(visuals.common_background_digest ? [visuals.common_background_digest] : []),
      ...Object.values(visuals.character_backgrounds),
      ...visuals.expressions.map(item => item.digest),
    ])].sort().join(",");
  }, [visuals]);

  useEffect(() => {
    if (!visible || !digestKey) { setUrls({}); return; }
    const abort = new AbortController();
    const created: string[] = [];
    let active = true;
    void (async () => {
      const next: Record<string, string> = {};
      const digests = digestKey.split(",");
      for (let offset = 0; offset < digests.length && active; offset += 8) {
        const entries = await Promise.all(digests.slice(offset, offset + 8).map(async digest => {
          try {
            const blob = await client.coverImage(worldId, digest, abort.signal);
            return [digest, URL.createObjectURL(blob)] as const;
          } catch { return null; }
        }));
        for (const entry of entries) if (entry) { next[entry[0]] = entry[1]; created.push(entry[1]); }
      }
      if (active) setUrls(next);
    })().catch(() => { if (active) setUrls({}); });
    return () => { active = false; abort.abort(); for (const url of created) URL.revokeObjectURL(url); };
  }, [client, worldId, visible, digestKey]);

  return { visuals, urls, loading, error, refresh, replace };
}

export function expressionLabel(expression: ChatExpression): string {
  return CHAT_EXPRESSIONS.find(item => item.value === expression)?.label ?? expression;
}

const expressionRules: ReadonlyArray<{ expression: ChatExpression; words: string[] }> = [
  { expression: "joy", words: ["哈哈", "笑死", "开心", "高兴", "太棒", "快乐", "lol", "haha"] },
  { expression: "sad", words: ["难过", "伤心", "悲伤", "哭", "眼泪", "遗憾", "对不起"] },
  { expression: "angry", words: ["生气", "愤怒", "气死", "滚开", "讨厌", "闭嘴"] },
  { expression: "surprised", words: ["什么", "居然", "竟然", "没想到", "惊讶", "真的吗", "不会吧"] },
  { expression: "scared", words: ["害怕", "恐惧", "吓", "危险", "救命", "不敢"] },
  { expression: "disgusted", words: ["恶心", "嫌弃", "反胃", "脏", "无语"] },
  { expression: "confused", words: ["困惑", "疑惑", "不明白", "不懂", "怎么回事", "为什么"] },
  { expression: "love", words: ["喜欢", "爱你", "心动", "想你", "亲爱的", "温柔"] },
  { expression: "embarrassed", words: ["害羞", "脸红", "不好意思", "羞", "呃"] },
  { expression: "thinking", words: ["想想", "思考", "考虑", "让我想", "也许", "或许"] },
  { expression: "content", words: ["满意", "安心", "放心", "很好", "不错", "当然"] },
];

export function inferExpression(text: string): ChatExpression {
  const normalized = text.toLocaleLowerCase();
  for (const rule of expressionRules) if (rule.words.some(word => normalized.includes(word))) return rule.expression;
  return "neutral";
}

