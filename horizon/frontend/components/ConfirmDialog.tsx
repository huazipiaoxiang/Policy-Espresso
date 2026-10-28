"use client";

import { useEffect, useState } from "react";

type Props = {
  title: string;
  description: React.ReactNode;
  acknowledgeLabel: string;
  confirmLabel: string;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

// 危险操作的双重确认：勾选确认项后「确认」按钮才可用，避免单次点击直接删除。
export default function ConfirmDialog({
  title, description, acknowledgeLabel, confirmLabel, busy, onCancel, onConfirm,
}: Props) {
  const [acknowledged, setAcknowledged] = useState(false);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div className="confirm-backdrop" role="presentation" onClick={busy ? undefined : onCancel}>
      <div className="confirm-modal" role="dialog" aria-modal="true" aria-label={title}
           onClick={(event) => event.stopPropagation()}>
        <h2>{title}</h2>
        <div className="confirm-body">{description}</div>
        <label className="confirm-ack">
          <input type="checkbox" checked={acknowledged} disabled={busy}
                 onChange={(event) => setAcknowledged(event.target.checked)} />
          <span>{acknowledgeLabel}</span>
        </label>
        <div className="confirm-actions">
          <button className="btn" type="button" onClick={onCancel} disabled={busy}>取消</button>
          <button className="btn danger" type="button" onClick={onConfirm}
                  disabled={!acknowledged || busy}>{busy ? "处理中…" : confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}
