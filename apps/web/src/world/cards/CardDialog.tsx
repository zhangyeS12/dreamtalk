import { useEffect, useRef, type ReactNode } from "react";
import styles from "./Cards.module.css";

export function CardDialog({ title, onClose, busy = false, wide = false, children, className = "" }: { title: string; onClose: () => void; busy?: boolean; wide?: boolean; children: ReactNode; className?: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { const node = dialog.current!; node.showModal(); return () => node.close(); }, []);
  return <dialog ref={dialog} className={`${styles.dialog} ${className}`} data-wide={wide || undefined} aria-label={title} onKeyDown={event => { if (event.key === "Escape") event.stopPropagation(); }} onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <header><h2>{title}</h2><button type="button" aria-label="关闭" disabled={busy} onClick={onClose}>×</button></header>{children}
  </dialog>;
}
