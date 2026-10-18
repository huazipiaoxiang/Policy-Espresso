import type { Config } from "tailwindcss";

// Design Token 见 docs/08 §1；颜色统一走 CSS 变量，dark 用 class 切换
const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
        text: "var(--text)",
        "text-2": "var(--text-2)",
        "text-3": "var(--text-3)",
        accent: "var(--accent)",
        p0: "var(--p0)",
        p1: "var(--p1)",
        p2: "var(--p2)",
        p3: "var(--p3)",
        ok: "var(--ok)",
        warn: "var(--warn)",
        danger: "var(--danger)",
        info: "var(--info)",
      },
      fontFamily: {
        sans: ['Inter', '"Noto Sans SC"', '"PingFang SC"', "system-ui", "sans-serif"],
        serif: ['"Source Serif 4"', '"Noto Serif SC"', "serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      borderRadius: { card: "8px", btn: "6px" },
      maxWidth: { content: "1600px" },
    },
  },
  plugins: [],
};

export default config;
