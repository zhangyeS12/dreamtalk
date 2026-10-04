import { useCallback, useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type OfflineContactStatus } from "@dreamtalk/api-client";

const errors: Record<string, string> = {
  offline_model_unavailable: "当前模型不可用，请检查模型设置。",
  offline_player_required: "请先选择此世界中的玩家身份。",
  offline_settings_changed: "设置已发生变化，请点击刷新状态后再保存。",
  offline_consent_required: "首次开启需要确认后台模型用量。",
  offline_characters_required: "请先在通讯录打开角色私聊，让角色加入当前世界。",
  offline_input_unavailable: "离线联系的角色输入未能准备好。请在通讯录检查已确认的角色卡并打开私聊，再刷新状态；这不等于角色卡已丢失，也不要求重新生成。",
  offline_input_capacity: "离线联系资料超过容量（16位私聊角色、64 KiB资料），请精简后再保存。",
  offline_character_mapping_invalid: "角色与已确认资料的关联不完整，请检查角色卡。",
  offline_background_capacity: "公共背景超过读取容量，请精简公开条目或触发条件。",
  offline_background_invalid: "公共背景格式异常，请检查或重新确认世界书。",
  offline_reason_used: "本次离线恢复已跳过：同一联系理由已处理，不会重复发送。无需重新保存或反复刷新；与角色继续聊天后，下次符合条件的离线恢复会重新判断。",
  offline_waiting_reply: "本次离线恢复已跳过：你还没有回复上一条主动联系。查看或清除红点不会解除等待；请在收到联系的会话中回复。",
  offline_contact_in_progress: "本次离线恢复已跳过：另一条主动联系正在处理中。系统不会并发发送，也不会补发这次恢复。",
  offline_no_contact: "本次恢复没有发起联系。现有记录可能对应忙碌、暂停、没有合适角色、未回复上一条主动消息或模型决定不联系，不能据此确定具体原因。",
  offline_interrupted: "上次任务被中断，系统不会自动重试这次恢复。",
  offline_generation_failed: "本次生成未完成，可能已产生费用，系统不会自动重试。",
  offline_plan_invalid: "本次联系计划未通过校验，已停止。",
  offline_dialogue_invalid: "本次角色消息未通过校验，已停止。",
  offline_context_changed: "身份、资料、玩家状态或新消息已变化，本次联系已取消。",
  offline_clock_regression: "系统时间向后调整，等待时间恢复后再判断离线时长。",
  offline_storage_corrupt: "存档读取异常，请退出程序并保留存档文件，先诊断；反复点击或刷新不能修复存档。",
  offline_storage_busy: "存档暂时被占用，请稍后点击刷新状态，再手动保存。",
  offline_storage_unavailable: "存档无法写入，请检查可用空间和存档目录权限。",
  offline_storage_schema: "当前存档结构与程序不一致，请退出并使用完整的新程序包。",
  offline_settings_integrity: "设置未通过存档完整性检查，请保留存档并反馈此错误。",
  offline_storage_value_invalid: "设置数据格式未通过检查，请保留存档并反馈此错误。",
  offline_internal_attribute: "核心保存逻辑发生属性错误，请反馈错误码 offline_internal_attribute。",
  offline_internal_type: "核心保存逻辑发生类型错误，请反馈错误码 offline_internal_type。",
  offline_internal_key: "核心保存逻辑缺少必需字段，请反馈错误码 offline_internal_key。",
  offline_request_failed: "核心未能完成设置请求，请保留存档并反馈错误码 offline_request_failed。",
};
export function offlineContactErrorMessage(error: unknown): string {
  if (!(error instanceof CoreRequestError)) return "未能连接核心，请检查连接后点击刷新状态。";
  if (error.code && errors[error.code]) return errors[error.code];
  if (error.status === 401) return "核心连接已失效，请重新打开程序。";
  if (error.status === 422) return "设置格式不正确，请输入1至168之间的整数小时。";
  return `核心请求未完成（HTTP ${error.status}${error.code ? `，${error.code}` : ""}），请点击刷新状态核对。`;
}

/** Read-only refresh and one explicit mutation; stale reads never replace a saved revision. */
export function useOfflineContact(client: CoreClient, worldId: string, playerId: string | null) {
  const scope = `${worldId}:${playerId ?? ""}`;
  const currentScope = useRef(scope); currentScope.current = scope;
  const currentClient = useRef(client); currentClient.current = client;
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const serial = useRef(0);
  const reading = useRef<{ scope: string; request: number } | null>(null);
  const writing = useRef<{ scope: string; request: number } | null>(null);
  const confirmed = useRef<{ scope: string; client: CoreClient; value: OfflineContactStatus } | null>(null);
  const polling = useRef<{ scope: string; resume: () => void } | null>(null);
  const [status, setStatus] = useState<OfflineContactStatus | null>(null);
  const [readError, setReadError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const read = useCallback(async (): Promise<boolean | null> => {
    if (!worldId || !playerId || writing.current?.scope === scope || reading.current?.scope === scope) return null;
    const job = { scope, request: ++serial.current }; reading.current = job;
    setRefreshing(true);
    const valid = () => alive.current && currentScope.current === scope && currentClient.current === client && job.request === serial.current;
    try {
      const next = await client.offlineContactStatus(worldId);
      if (!valid()) return null;
      confirmed.current = { scope, client, value: next }; setStatus(next); setReadError("");
      return true;
    } catch (failure) {
      if (!valid()) return null;
      setReadError(offlineContactErrorMessage(failure)); return false;
    } finally {
      if (reading.current === job) reading.current = null;
      if (valid()) setRefreshing(false);
    }
  }, [client, worldId, playerId, scope]);
  const refresh = useCallback(async () => {
    const result = await read();
    if (result === true) {
      setSaveError("");
      if (polling.current?.scope === scope) polling.current.resume();
    }
    return result;
  }, [read, scope]);
  const save = useCallback(async (enabled: boolean, hours: number, consent: boolean): Promise<boolean> => {
    const previous = confirmed.current;
    if (!previous || previous.scope !== scope || previous.client !== client || writing.current?.scope === scope) return false;
    const job = { scope, request: ++serial.current }; writing.current = job;
    setBusy(true); setRefreshing(false); setSaveError(""); setReadError("");
    const valid = () => alive.current && currentScope.current === scope && currentClient.current === client && job.request === serial.current;
    try {
      const next = await client.configureOfflineContact(worldId, previous.value, enabled, hours, consent);
      if (!valid()) return false;
      confirmed.current = { scope, client, value: next }; setStatus(next); setSaveError("");
      if (polling.current?.scope === scope) polling.current.resume();
      return true;
    } catch (failure) {
      if (valid()) setSaveError(offlineContactErrorMessage(failure));
      return false;
    } finally {
      if (writing.current === job) writing.current = null;
      if (valid()) setBusy(false);
    }
  }, [client, worldId, scope]);
  useEffect(() => {
    ++serial.current; confirmed.current = null; reading.current = writing.current = null;
    setStatus(null); setReadError(""); setSaveError(""); setBusy(false); setRefreshing(false);
    if (!worldId || !playerId) return;
    let active = true; let timer: number | undefined; let failures = 0;
    const poll = async () => {
      timer = undefined;
      const result = await read();
      if (result === false) failures += 1; else if (result === true) failures = 0;
      if (active && failures < 2 && timer === undefined) timer = window.setTimeout(() => void poll(), 10000);
    };
    const owner = { scope, resume: () => {
      failures = 0;
      if (active && timer === undefined) timer = window.setTimeout(() => void poll(), 10000);
    } };
    polling.current = owner;
    void poll();
    return () => {
      active = false; window.clearTimeout(timer); ++serial.current;
      if (polling.current === owner) polling.current = null;
    };
  }, [read, scope, worldId, playerId]);
  return {
    status: confirmed.current?.scope === scope && confirmed.current.client === client ? status : null,
    busy, refreshing, error: saveError || readError, refresh, save,
  };
}
