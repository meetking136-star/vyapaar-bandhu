"use client";

import { useState } from "react";
import {
  FileJson,
  FileText,
  Download,
  Check,
  Loader2,
  ChevronDown,
} from "lucide-react";
import AppShell from "@/components/layout/app-shell";
import { useClients } from "@/lib/hooks";
import { api } from "@/lib/api";

function getCurrentPeriod(): string {
  const d = new Date();
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${d.getFullYear()}`;
}

export default function ExportsPage() {
  const { data: clients } = useClients();
  const [selectedClient, setSelectedClient] = useState("");
  const [period, setPeriod] = useState(getCurrentPeriod());
  const [gstr3bStatus, setGstr3bStatus] = useState<
    "idle" | "loading" | "done" | "error"
  >("idle");
  const [pdfStatus, setPdfStatus] = useState<
    "idle" | "loading" | "done" | "error"
  >("idle");
  const [gstr3bData, setGstr3bData] = useState<object | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function handleGSTR3B() {
    if (!selectedClient || !period) return;
    setGstr3bStatus("loading");
    setError("");
    try {
      const data = await api.get<object>(
        `/exports/gstr3b?client_id=${selectedClient}&period=${period}`
      );
      setGstr3bData(data);
      setGstr3bStatus("done");
    } catch (err: any) {
      setError(err.message);
      setGstr3bStatus("error");
    }
  }

  async function handlePDF() {
    if (!selectedClient || !period) return;
    setPdfStatus("loading");
    setError("");
    try {
      const data = await api.get<{ presigned_url: string }>(
        `/exports/pdf?client_id=${selectedClient}&period=${period}`
      );
      setPdfUrl(data.presigned_url);
      setPdfStatus("done");
    } catch (err: any) {
      setError(err.message);
      setPdfStatus("error");
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Exports</h1>
          <p className="text-white/50 text-sm">
            Generate GSTR-3B JSON and PDF reports
          </p>
        </div>

        {/* Client + Period Selector */}
        <div className="glass-card p-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-white/50 mb-2">
                Client
              </label>
              <div className="relative">
                <select
                  value={selectedClient}
                  onChange={(e) => {
                    setSelectedClient(e.target.value);
                    setGstr3bStatus("idle");
                    setPdfStatus("idle");
                    setGstr3bData(null);
                    setPdfUrl(null);
                  }}
                  className="w-full px-4 py-2.5 bg-bg-surface border border-white/10 rounded-lg text-white appearance-none focus:outline-none focus:border-gold/50 transition-colors text-sm"
                >
                  <option value="">Select a client</option>
                  {clients?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.business_name} ({c.gstin || "No GSTIN"})
                    </option>
                  ))}
                </select>
                <ChevronDown
                  size={16}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 pointer-events-none"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm text-white/50 mb-2">
                Period (MM-YYYY)
              </label>
              <input
                type="text"
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
                placeholder="03-2026"
                className="w-full px-4 py-2.5 bg-bg-surface border border-white/10 rounded-lg text-white placeholder:text-white/30 focus:outline-none focus:border-gold/50 transition-colors text-sm font-mono"
              />
            </div>
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Export Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* GSTR-3B JSON */}
          <div className="glass-card p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-lg bg-blue-500/10">
                <FileJson size={24} className="text-blue-400" />
              </div>
              <div>
                <h3 className="font-semibold">GSTR-3B JSON</h3>
                <p className="text-xs text-white/40">
                  GSTN portal-compatible format
                </p>
              </div>
            </div>
            <p className="text-sm text-white/60">
              Generate GSTR-3B JSON with confirmed ITC amounts, RCM
              liability, and all required GSTN fields.
            </p>
            <button
              onClick={handleGSTR3B}
              disabled={!selectedClient || gstr3bStatus === "loading"}
              className="w-full py-2.5 rounded-lg font-medium text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-30 bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20"
            >
              {gstr3bStatus === "loading" ? (
                <Loader2 size={16} className="animate-spin" />
              ) : gstr3bStatus === "done" ? (
                <Check size={16} />
              ) : (
                <FileJson size={16} />
              )}
              {gstr3bStatus === "done"
                ? "Generated"
                : "Generate GSTR-3B"}
            </button>
            {gstr3bData && (
              <div className="bg-bg-primary rounded-lg p-3 max-h-48 overflow-y-auto">
                <pre className="text-xs font-mono text-white/60">
                  {JSON.stringify(gstr3bData, null, 2)}
                </pre>
              </div>
            )}
          </div>

          {/* PDF Report */}
          <div className="glass-card p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-lg bg-gold/10">
                <FileText size={24} className="text-gold" />
              </div>
              <div>
                <h3 className="font-semibold">PDF Report</h3>
                <p className="text-xs text-white/40">
                  Filing summary with ITC breakdown
                </p>
              </div>
            </div>
            <p className="text-sm text-white/60">
              Generate a PDF report with ITC summary, invoice details,
              flagged items, and RCM liability breakdown.
            </p>
            <button
              onClick={handlePDF}
              disabled={!selectedClient || pdfStatus === "loading"}
              className="w-full py-2.5 rounded-lg font-medium text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-30 gold-gradient text-black hover:opacity-90"
            >
              {pdfStatus === "loading" ? (
                <Loader2 size={16} className="animate-spin" />
              ) : pdfStatus === "done" ? (
                <Check size={16} />
              ) : (
                <FileText size={16} />
              )}
              {pdfStatus === "done" ? "Generated" : "Generate PDF"}
            </button>
            {pdfUrl && (
              <a
                href={pdfUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-2 py-2.5 rounded-lg bg-green-500/10 text-green-400 border border-green-500/20 text-sm font-medium hover:bg-green-500/20 transition-colors"
              >
                <Download size={16} />
                Download PDF
              </a>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
