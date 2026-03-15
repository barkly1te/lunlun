import type { Metadata } from "next";

import { ChatWorkbench } from "../components/chat-workbench";

export const metadata: Metadata = {
  title: "agent控制台",
  description: "进入即对话的论文审美控制台，包含 Chat、Control、Agent、Settings 模块。",
};

export default function HomePage() {
  return <ChatWorkbench />;
}

