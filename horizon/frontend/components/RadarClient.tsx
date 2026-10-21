"use client";

import { useState } from "react";
import ChatButton from "@/components/ChatButton";
import ChatPanel from "@/components/ChatPanel";

export default function RadarClient({ children }: { children: React.ReactNode }) {
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <>
      {children}
      <ChatButton onClick={() => setChatOpen(true)} />
      {chatOpen && <ChatPanel onClose={() => setChatOpen(false)} />}
    </>
  );
}
