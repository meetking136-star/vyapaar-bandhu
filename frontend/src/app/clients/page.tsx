"use client";

import { useState } from "react";
import { Search, ChevronRight, Phone, MapPin } from "lucide-react";
import AppShell from "@/components/layout/app-shell";
import ReadinessRing from "@/components/shared/readiness-ring";
import { TableSkeleton } from "@/components/shared/loading-skeleton";
import { useClients, useClientITCSummary } from "@/lib/hooks";
import { formatINR } from "@/lib/format";
import type { Client } from "@/types";

function getCurrentPeriod(): string {
  const d = new Date();
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${d.getFullYear()}`;
}

export default function ClientsPage() {
  const { data: clients, isLoading } = useClients();
  const [search, setSearch] = useState("");
  const [selectedClient, setSelectedClient] = useState<Client | null>(null);

  const filtered = (clients || []).filter(
    (c) =>
      c.business_name.toLowerCase().includes(search.toLowerCase()) ||
      c.owner_name.toLowerCase().includes(search.toLowerCase()) ||
      (c.gstin || "").toLowerCase().includes(search.toLowerCase())
  );

  return (
    <AppShell>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Clients</h1>
            <p className="text-white/50 text-sm">
              {clients?.length || 0} active clients
            </p>
          </div>
        </div>

        {/* Search */}
        <div className="relative max-w-md">
          <Search
            size={18}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30"
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search clients by name, GSTIN..."
            className="w-full pl-10 pr-4 py-2.5 bg-bg-surface border border-white/10 rounded-lg text-white placeholder:text-white/30 focus:outline-none focus:border-gold/50 transition-colors text-sm"
          />
        </div>

        {isLoading ? (
          <TableSkeleton rows={8} />
        ) : (
          <div className="flex gap-4">
            {/* Client Table */}
            <div className="glass-card flex-1 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-white/40 text-left border-b border-white/5">
                    <th className="p-4 font-medium">Business</th>
                    <th className="p-4 font-medium">GSTIN</th>
                    <th className="p-4 font-medium">Type</th>
                    <th className="p-4 font-medium">Phone</th>
                    <th className="p-4 font-medium text-center">
                      Readiness
                    </th>
                    <th className="p-4 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((client, i) => (
                    <tr
                      key={client.id}
                      onClick={() => setSelectedClient(client)}
                      className={`border-b border-white/5 cursor-pointer transition-colors animate-fade-in ${
                        selectedClient?.id === client.id
                          ? "bg-gold/5"
                          : "hover:bg-white/[0.02]"
                      }`}
                      style={{ animationDelay: `${i * 30}ms` }}
                    >
                      <td className="p-4">
                        <div className="font-medium">
                          {client.business_name}
                        </div>
                        <div className="text-white/40 text-xs">
                          {client.owner_name}
                        </div>
                      </td>
                      <td className="p-4 font-mono text-xs text-white/60">
                        {client.gstin || "N/A"}
                      </td>
                      <td className="p-4">
                        <span className="status-pill status-yellow">
                          {client.business_type}
                        </span>
                      </td>
                      <td className="p-4 text-white/60 text-xs">
                        {client.whatsapp_phone}
                      </td>
                      <td className="p-4 flex justify-center">
                        <ReadinessRing percentage={75} size={36} />
                      </td>
                      <td className="p-4">
                        <ChevronRight
                          size={16}
                          className="text-white/20"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filtered.length === 0 && (
                <div className="p-12 text-center text-white/30">
                  No clients found
                </div>
              )}
            </div>

            {/* Detail Drawer */}
            {selectedClient && (
              <ClientDetailDrawer
                client={selectedClient}
                onClose={() => setSelectedClient(null)}
              />
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}

function ClientDetailDrawer({
  client,
  onClose,
}: {
  client: Client;
  onClose: () => void;
}) {
  const period = getCurrentPeriod();
  const { data: itc } = useClientITCSummary(client.id, period);

  return (
    <div className="glass-card w-96 p-6 space-y-5 animate-fade-in flex-shrink-0">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">{client.business_name}</h3>
        <button
          onClick={onClose}
          className="text-white/30 hover:text-white transition-colors"
        >
          &times;
        </button>
      </div>

      <div className="space-y-3 text-sm">
        <div className="flex items-center gap-2 text-white/60">
          <Phone size={14} />
          {client.whatsapp_phone}
        </div>
        {client.gstin && (
          <div className="flex items-center gap-2 text-white/60">
            <MapPin size={14} />
            GSTIN: {client.gstin}
          </div>
        )}
      </div>

      {itc && (
        <div className="space-y-3">
          <h4 className="text-sm text-white/50">
            ITC Summary ({period})
          </h4>
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: "Confirmed", value: itc.total_confirmed, color: "text-green-400" },
              { label: "Pending", value: itc.total_pending, color: "text-yellow-400" },
              { label: "Rejected", value: itc.total_rejected, color: "text-red-400" },
              { label: "RCM", value: itc.rcm_liability, color: "text-orange-400" },
            ].map((item) => (
              <div key={item.label} className="bg-white/[0.02] rounded-lg p-3">
                <div className="text-xs text-white/40">{item.label}</div>
                <div className={`font-mono text-sm ${item.color}`}>
                  {formatINR(item.value)}
                </div>
              </div>
            ))}
          </div>
          <div className="text-xs text-white/30 text-center">
            {itc.invoice_count} invoices this period
          </div>
        </div>
      )}
    </div>
  );
}
