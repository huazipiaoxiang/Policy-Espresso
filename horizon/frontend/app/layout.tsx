import type { Metadata } from "next";
import "./globals.css";
import AppShell from "@/components/AppShell";
import AuthProvider from "@/components/AuthProvider";

export const metadata: Metadata = {
  title: "Policy Espresso · 政策智能平台",
  description: "区域性金融政策监测与影响分析",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hans">
      <body className="font-sans antialiased">
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
