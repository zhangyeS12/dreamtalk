import { useEffect, useRef, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import type { ContentExportInfo, CoreClient, FileExportRequest, LibraryCardItem } from "@dreamtalk/api-client";
import { CardDialog } from "./CardDialog";
import { CardPresentationPreview } from "./CardPresentationPreview";
import { defaultDesign } from "./cardDesign";
import { libraryFailure } from "./libraryFeedback";
import styles from "./Cards.module.css";

export function CardShare({ client, card, onClose }: { client: CoreClient; card: LibraryCardItem; onClose: () => void }) {
  const [info, setInfo] = useState<ContentExportInfo | null>(null), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false), [reading, setReading] = useState(true), [attempt, setAttempt] = useState(0);
  const lock = useRef(false), alive = useRef(true);
  useEffect(() => {
    alive.current = true; const controller = new AbortController(); setReading(true); setInfo(null); setError("");
    void client.libraryShareInfo(card, controller.signal).then(value => { if (!controller.signal.aborted) setInfo(value); }).catch(failure => { if (!controller.signal.aborted) setError(libraryFailure(failure)); }).finally(() => { if (!controller.signal.aborted) setReading(false); });
    return () => { alive.current = false; controller.abort(); };
  }, [client, card, attempt]);
  const save = async () => {
    if (lock.current || !info) return;
    lock.current = true; setBusy(true); setError(""); setNotice("");
    const request: FileExportRequest = { kind: "library_card", item_id: card.card_id, expected_revision: Number(card.revision), expected_digest: info.digest };
    try {
      if (isTauri()) {
        const path = await invoke<string | null>("save_file_export", { request, filename: info.filename });
        if (alive.current && path) setNotice("角色卡已保存，可以将这个 CHARX 文件发送给其他用户。");
      } else {
        const blob = await client.fileExport(request);
        if (!alive.current) return;
        const url = URL.createObjectURL(blob), link = document.createElement("a"); link.href = url; link.download = info.filename;
        document.body.append(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
        setNotice("已交给浏览器下载。将下载的 CHARX 文件发送给其他用户即可。");
      }
    } catch (failure) { if (alive.current) setError(typeof failure === "string" ? "文件未能保存。请重新选择保存位置，并使用 .charx 扩展名。" : libraryFailure(failure)); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  };
  return <CardDialog title="分享角色卡" onClose={onClose} busy={busy}>
    <p>保存完整角色卡，接收方从“新建角色卡 → 从文件导入”预览并收藏。</p>
    <CardPresentationPreview client={client} cardId={card.card_id} design={defaultDesign(card)} />
    <p>包含角色设定、卡片自带世界书、双面设计，以及当前使用的图片原图和裁剪信息。各世界的聊天、记忆和位置不在分享范围内。</p>
    <p>导入 dreamtalk 后可继续旋转、设计或加入世界。其他应用对卡面设计的支持取决于其实现。</p>
    {reading && <p role="status">正在准备分享文件…</p>}
    {info && <p>{info.filename} · {(Number(info.size) / 1024 / 1024).toFixed(2)} MiB</p>}
    {error && <p role="alert" className={styles.error}>{error}</p>}{notice && <p role="status">{notice}</p>}
    <footer><button type="button" disabled={busy} onClick={onClose}>关闭</button>{error && !info && <button type="button" disabled={reading} onClick={() => setAttempt(value => value + 1)}>重新准备</button>}<button type="button" className={styles.gold} disabled={reading || busy || !info} onClick={() => void save()}>{busy ? "正在保存…" : "保存完整角色卡"}</button></footer>
  </CardDialog>;
}
