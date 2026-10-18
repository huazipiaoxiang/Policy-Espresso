import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "HORIZON · 政策雷达",
  description: "区域性金融政策监测与影响分析",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hans" className="dark">
      <body className="font-sans antialiased">
        <Sidebar />
        <div className="ml-[232px]">{children}</div>
      </body>
    </html>
  );
}
