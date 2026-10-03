import { useId } from "react";
import type { DirectorStatus, OfflineContactStatus, PlayerAvailability, WorldNewsStatus } from "@dreamtalk/api-client";

export type BackgroundDestination = "model" | "time" | "lore" | "contacts" | "locations" | "events" | "chats" | "me" | "about";
export type BackgroundNavigate = (destination: BackgroundDestination) => void;
interface Guidance { tone?: "neutral" | "success" | "warning" | "error"; title: string; detail: string; destination?: BackgroundDestination; action?: string }
const actions: Record<BackgroundDestination, string> = {
  model: "检查模型设置", time: "查看世界时间", lore: "返回书架管理世界书", contacts: "前往通讯录",
  locations: "设置初始地点", events: "查看世界事件", chats: "查看聊天", me: "查看我的身份", about: "查看连接与诊断",
};
export function taskErrorGuidance(code: string | null, message: string, title = "本次任务已停止"): Guidance {
  const suffix = code?.replace(/^(director|news|offline)_/, "");
  const destination: BackgroundDestination | undefined = suffix?.startsWith("background_") ? "lore"
    : suffix === "model_unavailable" || suffix === "model_failed" || suffix === "generation_failed" && code !== "news_generation_failed" ? "model"
    : suffix === "player_required" ? "me"
    : suffix === "characters_required" ? code?.startsWith("director_") ? "locations" : "contacts"
    : suffix === "character_mapping_invalid" || suffix === "input_unavailable" || suffix === "input_capacity" ? "contacts"
    : suffix === "world_capacity" ? "locations"
    : suffix === "pending_capacity" ? "events"
    : suffix === "token_bound_unavailable" || suffix === "model_quota" || suffix === "context_limit" ? "model"
    : suffix === "execution_failed" ? "about" : undefined;
  return { tone: "error", title, detail: message, destination };
}
const disconnected: Guidance = { tone: "warning", title: "暂未能核对最新状态", detail: "下面保留上次读取的信息。请先刷新状态；读取失败不代表设置已关闭或模型任务已结束。", destination: "about" };

export function activityGuidance(status: DirectorStatus | null, paused: boolean, initialized: boolean | null, error: string, reason: string): Guidance {
  if (error) return disconnected;
  if (!status) return { title: "正在读取自动活动状态", detail: "尚未核对开关，不会在读取时调用模型。" };
  if (!status.enabled) return { title: "自动活动未开启", detail: status.model_available ? "开启后才会批量安排日常活动；首次开启需确认后台模型用量。" : "请先完成模型设置，再开启自动活动。", destination: status.model_available ? undefined : "model" };
  if (status.state === "attention") {
    if (status.error === "director_characters_required" && initialized === true) return { tone: "warning", title: "初始地点已就绪，等待你重新规划", detail: "上一批因缺少角色地点停止。无需重复设置；点击下方“重新规划”会开始新的模型任务，刷新不会重试。" };
    return taskErrorGuidance(status.error, reason || "没有收到可用的活动计划。请刷新核对；需要新计划时显式重新规划。");
  }
  if (status.state === "planning") return { title: "正在规划下一批活动", detail: paused ? "世界已暂停，已发出的模型请求仍可能计费；暂停期间不执行活动。" : "正在使用当前模型安排6小时世界时间的日常。无需反复点击，状态会自动更新。" };
  if (paused) return { title: "世界暂停中，活动等待恢复", detail: "开关仍已开启。恢复世界时间后才执行候选和开始下一批规划。", destination: "time" };
  if (status.state === "idle" && !status.model_available) return { tone: "warning", title: "自动活动已开启，等待模型就绪", detail: "当前模型尚不可用；检查模型设置后再核对状态。", destination: "model" };
  if (initialized === false && status.state === "idle") return { tone: "warning", title: "尚未确认角色的初始地点", detail: "先在通讯录打开私聊，再为至少一名角色选择初始地点。此设置不调用模型。", destination: "locations" };
  if (status.state === "ready") return { tone: "success", title: "活动计划已就绪", detail: "活动按世界时间执行。可以在聊天中问角色近况；世界事件只显示你已获知的变化。", destination: "chats" };
  return { title: "已开启，等待后台开始规划", detail: "世界运行且模型就绪时处理；刷新状态只读取，不会催促或重发模型请求。" };
}

export function newsGuidance(status: WorldNewsStatus | null, paused: boolean, error: string, reason: string): Guidance {
  if (error) return disconnected;
  if (!status) return { title: "正在读取事件池状态", detail: "尚未核对开关，读取不会生成动态。" };
  if (!status.enabled) return { title: "事件池未开启", detail: status.model_available ? "准备公共背景后可开启，每次生成10条并逐条发布。" : "请先完成模型设置，再准备公共背景。", destination: status.model_available ? "lore" : "model" };
  if (status.state === "attention") return taskErrorGuidance(status.error, reason || "本批未能继续。请刷新核对原因；重新生成会开始新的模型任务。");
  if (status.state === "generating") return { title: "正在生成一批动态", detail: paused ? "世界已暂停，已开始的请求仍可能计费；生成结果不会在暂停期间发布。" : "整批内容先存入事件池，再按世界时间逐条发布。无需重复点击。" };
  if (paused) return { title: "世界暂停中，动态等待恢复", detail: "开关仍已开启，暂停期间不开始生成或发布。", destination: "time" };
  if (!status.model_available && status.state === "idle") return { tone: "warning", title: "事件池已开启，等待模型就绪", detail: "当前模型尚不可用，请检查设置。", destination: "model" };
  if (status.state === "ready" && status.pending === 0) {
    const threshold = Math.ceil(status.batch_total * .8);
    if (status.batch_total > 0 && status.batch_processed < threshold) return { title: "暂无待发布动态，等待你标记进度", detail: `最近一批已处理${status.batch_processed}／${status.batch_total}条，还需${threshold - status.batch_processed}条达到自动续批条件。已发布事件可标为“已经历”或“跳过”。`, destination: "events" };
    return { title: "暂无待发布动态", detail: "达到续批条件后后台会核对是否需要补充。需要主动补充时，可点击下方“生成新一批”，会产生模型用量。", destination: "events" };
  }
  if (status.state === "ready") return { tone: "success", title: "事件池已就绪，等待逐条发布", detail: `池内待发布${status.pending}条。发布受世界时间、候选有效时段和背景状态限制，刷新不会提前发布。`, destination: "events" };
  return { title: "等待后台生成下一批", detail: "世界运行且模型就绪后处理。刷新只读取状态，不会重新生成。" };
}

export function offlineGuidance(status: OfflineContactStatus | null, paused: boolean, availability: PlayerAvailability | null, error: string, reason: string): Guidance {
  if (error) return disconnected;
  if (!status) return { title: "正在读取离线联系设置", detail: "尚未核对开关，读取不会生成消息。" };
  if (!status.enabled) return { title: "离线联系未开启", detail: status.model_available ? "开启后先记录在线基线；只有之后符合时长的恢复才考虑联系。" : "请先完成模型设置，再开启离线联系。", destination: status.model_available ? undefined : "model" };
  // No-contact is intentionally broad: the persisted code cannot distinguish a
  // paused/busy recovery, an unanswered outreach or a model choosing silence.
  if (status.state === "skipped" && status.error === "offline_reason_used") return { title: "已开启，本次联系理由已处理", detail: "本次恢复不会重复发送。继续与角色交流后，下次符合条件的恢复会重新判断；刷新或重新保存不会补发。", destination: "chats" };
  if (status.state === "skipped" && status.error === "offline_no_contact") return { title: "已开启，本次恢复没有发起联系", detail: "可能是忙碌、暂停、没有合适角色、上条主动消息未回复，或模型决定不联系。当前记录未区分具体原因，刷新不会补发。", destination: "chats" };
  if (status.error === "offline_context_changed") return { tone: "warning", title: "本次联系已取消，开关仍已开启", detail: "身份、资料、玩家状态或新消息发生变化，原结果不再适用。等待下次符合条件的离线恢复。" };
  if (status.error === "offline_clock_regression") return { tone: "warning", title: "系统时间回退，暂不判断离线时长", detail: "请核对电脑时间。程序等待时间恢复，不会把负时长当成离线。" };
  if (status.state === "attention" || status.error) return { ...taskErrorGuidance(status.error, `${reason || "本次离线任务未能完成。"} 本次恢复不会自动重试；修正后等待下次符合条件的恢复，重新保存开关不会补发。`), title: "本次离线任务已停止" };
  if (status.state === "planning" || status.state === "writing") return { title: status.state === "planning" ? "正在选择联系角色和时段" : "角色正在写离线消息", detail: "这次恢复正在处理，已开始的请求可能计费。不要反复关闭再开启；状态会自动更新。" };
  if (status.state === "delivered") return { tone: "success", title: "本次离线消息已送达", detail: status.unread.length ? `有${status.unread.length}条主动消息尚未读。打开聊天查看；显示的剧情时间与真实生成时间分开保留。` : "可以在聊天中查看已送达的消息。查看或刷新不会再次生成。", destination: "chats" };
  if (status.state === "waiting") return { title: "本次恢复已记录，等待处理", detail: status.model_available ? "后台正在核对这次恢复是否仍然适用；无需重复保存。" : "当前模型尚不可用，请先检查模型设置。", destination: status.model_available ? undefined : "model" };
  if (paused) return { title: "已开启，世界暂停时不发起联系", detail: "暂停状态下的离线恢复会跳过；恢复世界不会立即补发。", destination: "time" };
  if (availability === "busy") return { title: "已开启，当前交流状态为忙碌", detail: "忙碌时的离线恢复会跳过普通主动消息；设为可用不会立即补发。" };
  if (!status.model_available) return { tone: "warning", title: "已开启，当前模型尚不可用", detail: "请检查模型设置；开启开关不代表已有可用生成服务。", destination: "model" };
  return { title: "已开启，等待下一次离线恢复", detail: `Core停止运行至少${status.hours}个真实小时后，再恢复时考虑联系。只隐藏窗口或留在托盘不算离线，首次开启和刷新都不会立即发消息。` };
}

export function BackgroundTaskFeedback({ name, guidance, onNavigate, disabled = false }: { name: string; guidance: Guidance; onNavigate?: BackgroundNavigate; disabled?: boolean }) {
  const id = useId();
  return <div className={`background-task-feedback ${guidance.tone ?? "neutral"}`} role="group" aria-labelledby={id}>
    <div role={guidance.tone === "error" ? "alert" : "status"} aria-atomic="true"><strong id={id}><span className="sr-only">{name}：</span>{guidance.title}</strong><p>{guidance.detail}</p></div>
    {guidance.destination && onNavigate && <button type="button" className="text-action" disabled={disabled} onClick={() => onNavigate(guidance.destination!)}>{guidance.action ?? actions[guidance.destination]}</button>}
  </div>;
}
