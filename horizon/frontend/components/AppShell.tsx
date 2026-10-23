"use client";

import { useState } from "react";
import Sidebar from "@/components/Sidebar";
import Topbar from "@/components/Topbar";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [role, setRole] = useState("operations");

  return (
    <>
      <Sidebar role={role} />
      <Topbar role={role} onRoleChange={setRole} />
      <div className="ml-[232px] pt-14">{children}</div>
    </>
  );
}
