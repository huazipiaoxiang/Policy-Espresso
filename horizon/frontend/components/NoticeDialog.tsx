"use client";

import { useEffect } from "react";

type Props = {
  message: string;
  onClose: () => void;
};

// 操作成功提示框：复用 confirm 弹窗样式，展示一句成功信息，点「确定」或遮罩关闭。
export default function NoticeDialog({ message, onClose }: Props) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="confirm-backdrop" role="presentation" onClick={onClose}>
      <div className="confirm-modal" role="dialog" aria-modal="true" aria-label="操作成功"
           onClick={(event) => event.stopPropagation()}>
        <h2>操作成功</h2>
        <div className="confirm-body">{message}</div>
        <div className="confirm-actions">
          <button className="btn primary" type="button" onClick={onClose}>确定</button>
        </div>
      </div>
    </div>
  );
}
