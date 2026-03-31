"use client";

import Sidebar from "./sidebar";

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 ml-64 p-8 relative z-[1]">{children}</main>
    </div>
  );
}
