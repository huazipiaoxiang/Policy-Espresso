"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

// Studio 项目创建（经 BFF 代理，API Key 不暴露）
export default function StudioCreateForm({ themes }: { themes: string[] }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [theme, setTheme] = useState(themes[0] ?? "跨境金融");
  const [busy, setBusy] = useState(false);

  const create = async () => {
    setBusy(true);
    try {
      const resp = await fetch("/api/proxy/studio/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name || "未命名推演", theme }),
      });
      if (resp.ok) router.refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-4 flex flex-wrap items-center gap-2">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="项目名称，如：CEPA 金融开放推演"
        className="h-9 w-64 rounded-btn border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[12px]"
      />
      <select
        value={theme}
        onChange={(e) => setTheme(e.target.value)}
        className="h-9 rounded-btn border border-[var(--border)] bg-[var(--surface-2)] px-2 text-[12px] text-[var(--text)]"
      >
        {themes.map((t) => (
          <option key={t} value={t}>{t}</option>
        ))}
        <option value="跨境金融">跨境金融</option>
      </select>
      <button
        onClick={create}
        disabled={busy}
        className="rounded-btn bg-[var(--accent)] px-4 py-1.5 text-[12px] font-medium text-[var(--bg)] disabled:opacity-50"
      >
        {busy ? "创建中…" : "创建项目"}
      </button>
    </div>
  );
}
