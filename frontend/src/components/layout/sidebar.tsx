"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  FileText,
  Download,
  LogOut,
} from "lucide-react";
import { clearToken } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/clients", icon: Users, label: "Clients" },
  { href: "/invoices", icon: FileText, label: "Invoices" },
  { href: "/exports", icon: Download, label: "Exports" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 h-screen w-64 bg-bg-surface border-r border-white/5 flex flex-col z-10">
      {/* Brand */}
      <div className="p-6 border-b border-white/5">
        <h1 className="text-xl font-bold">
          <span className="gold-text">Vyapaar</span>
          <span className="text-white">Bandhu</span>
        </h1>
        <p className="text-xs text-white/40 mt-1">CA Dashboard</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1">
        {NAV_ITEMS.map(({ href, icon: Icon, label }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200",
                active
                  ? "bg-gold/10 text-gold border border-gold/20"
                  : "text-white/60 hover:text-white hover:bg-white/5"
              )}
            >
              <Icon size={18} />
              <span className="text-sm font-medium">{label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Logout */}
      <div className="p-4 border-t border-white/5">
        <button
          onClick={() => {
            clearToken();
            window.location.href = "/login";
          }}
          className="flex items-center gap-3 px-4 py-3 w-full rounded-lg text-white/40 hover:text-red-400 hover:bg-red-400/5 transition-all"
        >
          <LogOut size={18} />
          <span className="text-sm">Logout</span>
        </button>
      </div>
    </aside>
  );
}
