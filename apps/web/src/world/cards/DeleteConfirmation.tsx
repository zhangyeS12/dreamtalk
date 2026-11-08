import { useRef, useState } from "react";
import { CoreRequestError } from "@dreamtalk/api-client";
import { CardDialog } from "./CardDialog";
import styles from "./Removal.module.css";

export function DeleteConfirmation({ kind, name, onConfirm, onClose, onReload }: {
  kind: "角色卡" | "卡包"; name: string; onConfirm: () => Promise<void>; onClose: () => void; onReload: () => void;
}) {
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const inFlight = useRef(false);
  const confirm = async () => {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try { await onConfirm(); }
    catch (failure) { setError(failure instanceof CoreRequestError && failure.status === 409 ? `${kind}已发生变化，请重新核对后再删除。` : "删除结果暂未确认。可以重试同一次删除，或重新读取核对；不会自动重试。"); }
    finally { inFlight.current = false; setBusy(false); }
  };
  return <CardDialog title={`删除${kind}？`} onClose={onClose} busy={busy} className={styles.confirm}>
    <p className={styles.name}>确定删除「{name}」吗？</p>
    <p>{kind === "卡包" ? "将删除这个卡包的外观和装卡清单。里面的角色卡仍保留在“全部角色卡”，已加入世界的角色也会保留。" : "将从卡库删除这张原卡，并从所有卡包中移除。已加入各世界的角色、聊天和记忆会保留。"}</p>
    <p>删除后无法在这里撤销。</p>
    {error && <p className={styles.error} role="alert">{error}</p>}
    <footer><button type="button" autoFocus disabled={busy} onClick={onClose}>取消，保留{kind}</button>{error && <button type="button" disabled={busy} onClick={onReload}>重新读取</button>}<button type="button" className={styles.danger} disabled={busy} onClick={() => void confirm()}>{busy ? "正在删除…" : `确认删除${kind}`}</button></footer>
  </CardDialog>;
}
