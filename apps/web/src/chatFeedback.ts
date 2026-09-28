import { CoreRequestError, type DirectTurnView } from "@dreamtalk/api-client";

type ChatKind = "direct" | "group";
export type ChatRequestPhase = "saving" | "replying" | "checking" | null;

export function chatPhaseFeedback(phase: ChatRequestPhase, kind: ChatKind): string {
  if (phase === "saving") return "正在保存消息…";
  if (phase === "checking") return "正在检查已保存的回复状态…";
  if (phase === "replying") return kind === "group"
    ? "消息已保存，角色正在依次回复。已保存的发言会陆续显示…"
    : "消息已保存，正在等待角色回复…";
  return "";
}

export function chatSaveFailureFeedback(failure: CoreRequestError): string {
  if (failure.status === 401 || failure.status === 403) return "消息未保存。核心连接已失效，请重新打开应用后再发送。";
  if (failure.code === "selected_player_required") return "消息未保存。请先在当前世界选择自己的身份。";
  if (failure.code === "conversation_not_found") return "消息未保存。当前会话不可用，请从当前世界的通讯录重新打开聊天。";
  if (failure.code === "chat_request_conflict") return "此次保存请求与已有记录冲突，无法确认本次消息。请检查聊天记录后再发送。";
  return "消息未保存。请检查内容、当前世界和会话后修改重试。";
}

export function chatReplyFailureFeedback(failure: unknown, kind: ChatKind): string {
  const code = failure instanceof CoreRequestError ? failure.code : null;
  const prefix = kind === "group" ? "这一轮未能完整结束。已有发言仍会保留。" : "这轮回复未完成。消息已保存。";
  const noReplay = "系统不会自动重试模型调用；你可以检查回复状态，或继续发送新消息。";
  if (failure instanceof CoreRequestError && failure.status === 422) return kind === "group"
    ? "这一轮未获预算授权或额度已耗尽。请在设置中核对每轮 Token 额度、模型上界与费用预算；已有发言会保留，系统不会自动重试。"
    : "这轮回复未获预算授权。请在设置中核对每轮 Token 额度、模型上界与费用预算；消息已保存，系统不会自动重试模型调用。";
  if (code === "chat_accounting_unavailable") return `${prefix}本次用量或费用记录尚未可靠确认。${noReplay}`;
  if (code === "chat_model_unavailable") return `${prefix}聊天模型暂不可用，请在设置中检查模型和凭据。${noReplay}`;
  if (code === "chat_reply_invalid") return `${prefix}模型回复未通过校验，未作为完整回复发送。${noReplay}`;
  if (code === "chat_generation_failed") return `${prefix}生成服务未能完成这次回复。${noReplay}`;
  if (code === "chat_turn_already_claimed") return `${prefix}这轮已开始处理，当前结果尚未确认。${noReplay}`;
  if (failure instanceof CoreRequestError && (failure.status === 401 || failure.status === 403)) {
    return `${prefix}核心连接已失效，请重新打开应用后检查记录。${noReplay}`;
  }
  return `${prefix}当前结果尚未确认。为避免重复消耗，${noReplay}`;
}

export function chatReplyStateFeedback(state: DirectTurnView["state"] | null, kind: ChatKind): string {
  if (state === "completed") return kind === "group"
    ? "本轮已结束，已保存的发言已更新。"
    : "角色回复已保存，聊天记录已更新。";
  if (state === "pending") return "消息已保存，这轮尚未开始生成回复。系统不会自动重新发起生成；你可以继续发送新消息。";
  if (state === "claimed") return kind === "group"
    ? "这轮已开始处理，尚未确认结束。已保存的发言会保留；可以稍后再次检查状态。"
    : "这轮已开始处理，尚未确认完成。可以稍后再次检查状态。";
  return "暂时无法确认回复状态。可以稍后再次检查，系统不会重新调用模型。";
}
