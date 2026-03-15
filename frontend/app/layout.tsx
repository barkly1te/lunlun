import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "论论控制台",
  description: "一个基于 AgentScope 的本地论文审美与投稿判断控制台。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

