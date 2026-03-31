"use client";

import { useState } from "react";
import {
  Search,
  Filter,
  CheckSquare,
  Square,
  ArrowUpDown,
  RotateCcw,
} from "lucide-react";
import AppShell from "@/components/layout/app-shell";
import { TableSkeleton } from "@/components/shared/loading-skeleton";
import { useInvoices, useBulkAction } from "@/lib/hooks";
import { formatINR, formatStatus, getStatusColor } from "@/lib/format";
import type { Invoice } from "@/types";

const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "pending_ca_review", label: "Pending Review" },
  { value: "ca_approved", label: "Approved" },
  { value: "ca_rejected", label: "Rejected" },
  { value: "flagged_low_confidence", label: "Flagged" },
  { value: "processing", label: "Processing" },
];

export default function InvoicesPage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const { data: invoices, isLoading } = useInvoices({
    status: statusFilter || undefined,
    limit: 100,
  });
  const bulkAction = useBulkAction();

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (!invoices) return;
    if (selected.size === invoices.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(invoices.map((i) => i.id)));
    }
  }

  async function handleBulkAction(action: string) {
    if (selected.size === 0) return;
    if (selected.size > 50) {
      alert("Maximum 50 invoices per bulk action");
      return;
    }
    await bulkAction.mutateAsync({
      invoice_ids: Array.from(selected),
      action,
    });
    setSelected(new Set());
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Invoices</h1>
            <p className="text-white/50 text-sm">
              {invoices?.length || 0} invoices
            </p>
          </div>
        </div>

        {/* Filters + Bulk Actions */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1 bg-bg-surface rounded-lg p-1">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => {
                  setStatusFilter(f.value);
                  setSelected(new Set());
                }}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  statusFilter === f.value
                    ? "bg-gold/20 text-gold"
                    : "text-white/50 hover:text-white"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {selected.size > 0 && (
            <div className="flex items-center gap-2 ml-auto animate-fade-in">
              <span className="text-sm text-white/50">
                {selected.size} selected
              </span>
              <button
                onClick={() => handleBulkAction("approve")}
                disabled={bulkAction.isPending}
                className="px-3 py-1.5 bg-green-500/10 text-green-400 border border-green-500/20 rounded-lg text-xs font-medium hover:bg-green-500/20 transition-colors"
              >
                Approve
              </button>
              <button
                onClick={() => handleBulkAction("reject")}
                disabled={bulkAction.isPending}
                className="px-3 py-1.5 bg-red-500/10 text-red-400 border border-red-500/20 rounded-lg text-xs font-medium hover:bg-red-500/20 transition-colors"
              >
                Reject
              </button>
              <button
                onClick={() => handleBulkAction("flag")}
                disabled={bulkAction.isPending}
                className="px-3 py-1.5 bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 rounded-lg text-xs font-medium hover:bg-yellow-500/20 transition-colors"
              >
                Flag
              </button>
            </div>
          )}
        </div>

        {/* Table */}
        {isLoading ? (
          <TableSkeleton rows={10} />
        ) : (
          <div className="glass-card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-white/40 text-left border-b border-white/5">
                  <th className="p-4 font-medium w-10">
                    <button onClick={toggleAll}>
                      {invoices &&
                      selected.size === invoices.length &&
                      invoices.length > 0 ? (
                        <CheckSquare
                          size={16}
                          className="text-gold"
                        />
                      ) : (
                        <Square size={16} />
                      )}
                    </button>
                  </th>
                  <th className="p-4 font-medium">Invoice</th>
                  <th className="p-4 font-medium">Seller</th>
                  <th className="p-4 font-medium">Date</th>
                  <th className="p-4 font-medium text-right">Amount</th>
                  <th className="p-4 font-medium">Status</th>
                  <th className="p-4 font-medium">ITC</th>
                  <th className="p-4 font-medium">RCM</th>
                </tr>
              </thead>
              <tbody>
                {invoices?.map((inv, i) => (
                  <tr
                    key={inv.id}
                    className={`border-b border-white/5 transition-colors animate-fade-in ${
                      selected.has(inv.id)
                        ? "bg-gold/5"
                        : "hover:bg-white/[0.02]"
                    }`}
                    style={{ animationDelay: `${i * 20}ms` }}
                  >
                    <td className="p-4">
                      <button onClick={() => toggleSelect(inv.id)}>
                        {selected.has(inv.id) ? (
                          <CheckSquare
                            size={16}
                            className="text-gold"
                          />
                        ) : (
                          <Square
                            size={16}
                            className="text-white/20"
                          />
                        )}
                      </button>
                    </td>
                    <td className="p-4">
                      <div className="font-mono text-xs">
                        {inv.invoice_number || "N/A"}
                      </div>
                    </td>
                    <td className="p-4">
                      <div className="text-white/80">
                        {inv.seller_name?.slice(0, 25) || "Unknown"}
                      </div>
                      <div className="text-white/30 text-xs font-mono">
                        {inv.seller_gstin || ""}
                      </div>
                    </td>
                    <td className="p-4 text-white/60 text-xs">
                      {inv.invoice_date || "N/A"}
                    </td>
                    <td className="p-4 text-right font-mono">
                      {formatINR(inv.total_amount)}
                    </td>
                    <td className="p-4">
                      <span
                        className={`status-pill ${getStatusColor(inv.status)}`}
                      >
                        {formatStatus(inv.status)}
                      </span>
                    </td>
                    <td className="p-4">
                      {inv.is_itc_eligible_draft === true ? (
                        <span className="text-green-400 text-xs">
                          Eligible
                        </span>
                      ) : inv.is_itc_eligible_draft === false ? (
                        <span className="text-red-400 text-xs">
                          Blocked
                        </span>
                      ) : (
                        <span className="text-white/30 text-xs">--</span>
                      )}
                    </td>
                    <td className="p-4">
                      {inv.is_rcm && (
                        <span className="px-2 py-0.5 bg-orange-500/10 text-orange-400 border border-orange-500/20 rounded text-xs font-medium">
                          RCM
                          {inv.rcm_category
                            ? `: ${inv.rcm_category}`
                            : ""}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(!invoices || invoices.length === 0) && (
              <div className="p-12 text-center text-white/30">
                No invoices found
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
