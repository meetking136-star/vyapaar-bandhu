"use client";

import { useMemo } from "react";
import {
  FileText,
  Users,
  IndianRupee,
  Clock,
  AlertTriangle,
  TrendingUp,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";

import AppShell from "@/components/layout/app-shell";
import AnimatedCounter from "@/components/shared/animated-counter";
import ReadinessRing from "@/components/shared/readiness-ring";
import { CardSkeleton, TableSkeleton } from "@/components/shared/loading-skeleton";
import { useDashboardOverview, useAlerts } from "@/lib/hooks";
import { formatINR } from "@/lib/format";

const DONUT_COLORS = ["#22C55E", "#EAB308", "#EF4444"];

export default function DashboardPage() {
  const { data: overview, isLoading } = useDashboardOverview();
  const { data: alertsData } = useAlerts();

  const statusCounts = useMemo(() => {
    if (!overview) return { green: 0, yellow: 0, red: 0 };
    return overview.clients.reduce(
      (acc, c) => {
        acc[c.status_color]++;
        return acc;
      },
      { green: 0, yellow: 0, red: 0 }
    );
  }, [overview]);

  const donutData = [
    { name: "Ready", value: statusCounts.green },
    { name: "Attention", value: statusCounts.yellow },
    { name: "Critical", value: statusCounts.red },
  ];

  const chartData = useMemo(() => {
    if (!overview) return [];
    return overview.clients.slice(0, 8).map((c) => ({
      name: c.business_name.slice(0, 12),
      confirmed: parseFloat(c.confirmed_itc_total || "0"),
      draft: parseFloat(c.draft_itc_total || "0"),
    }));
  }, [overview]);

  if (isLoading) {
    return (
      <AppShell>
        <div className="space-y-6">
          <div className="grid grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
          <TableSkeleton rows={6} />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Dashboard</h1>
            <p className="text-white/50 text-sm">
              Filing period overview
            </p>
          </div>
        </div>

        {/* Stat Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            {
              label: "Total Clients",
              value: overview?.total_clients || 0,
              icon: Users,
              color: "text-blue-400",
            },
            {
              label: "Total Invoices",
              value: overview?.total_invoices || 0,
              icon: FileText,
              color: "text-purple-400",
            },
            {
              label: "Confirmed ITC",
              value: overview?.total_confirmed_itc || "0",
              icon: IndianRupee,
              color: "text-green-400",
              isCurrency: true,
            },
            {
              label: "Draft ITC",
              value: overview?.total_draft_itc || "0",
              icon: TrendingUp,
              color: "text-gold",
              isCurrency: true,
            },
          ].map((stat, i) => (
            <div
              key={stat.label}
              className="glass-card p-5 animate-fade-in-up"
              style={{ animationDelay: `${i * 100}ms` }}
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-white/50 text-sm">{stat.label}</span>
                <stat.icon size={18} className={stat.color} />
              </div>
              <div className="text-2xl font-semibold font-mono">
                {stat.isCurrency ? (
                  formatINR(stat.value as string)
                ) : (
                  <AnimatedCounter value={stat.value as number} />
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Bar Chart */}
          <div className="glass-card p-5 lg:col-span-2">
            <h3 className="text-sm text-white/50 mb-4">
              ITC by Client (Top 8)
            </h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <XAxis
                    dataKey="name"
                    tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "#0D1528",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: 8,
                      color: "#fff",
                    }}
                  />
                  <Bar dataKey="confirmed" fill="#22C55E" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="draft" fill="#F5A623" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Donut Chart */}
          <div className="glass-card p-5">
            <h3 className="text-sm text-white/50 mb-4">Client Status</h3>
            <div className="h-48 flex items-center justify-center">
              <PieChart width={180} height={180}>
                <Pie
                  data={donutData}
                  cx={90}
                  cy={90}
                  innerRadius={55}
                  outerRadius={80}
                  paddingAngle={3}
                  dataKey="value"
                >
                  {donutData.map((_, i) => (
                    <Cell key={i} fill={DONUT_COLORS[i]} />
                  ))}
                </Pie>
              </PieChart>
            </div>
            <div className="flex justify-center gap-4 text-xs mt-2">
              {donutData.map((d, i) => (
                <div key={d.name} className="flex items-center gap-1.5">
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{ background: DONUT_COLORS[i] }}
                  />
                  <span className="text-white/50">
                    {d.name} ({d.value})
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Client Readiness Table + Alert Panel */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Client Table */}
          <div className="glass-card p-5 lg:col-span-2 overflow-x-auto">
            <h3 className="text-sm text-white/50 mb-4">
              Client Readiness
            </h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-white/40 text-left border-b border-white/5">
                  <th className="pb-3 font-medium">Client</th>
                  <th className="pb-3 font-medium">Status</th>
                  <th className="pb-3 font-medium text-right">Invoices</th>
                  <th className="pb-3 font-medium text-right">
                    Confirmed ITC
                  </th>
                  <th className="pb-3 font-medium text-center">
                    Readiness
                  </th>
                </tr>
              </thead>
              <tbody>
                {overview?.clients.map((client, i) => {
                  const total = client.invoice_count || 1;
                  const reviewed =
                    total -
                    client.pending_ca_review_count -
                    client.flagged_low_confidence_count;
                  const pct = Math.round((reviewed / total) * 100);

                  return (
                    <tr
                      key={client.client_id}
                      className="border-b border-white/5 hover:bg-white/[0.02] transition-colors animate-fade-in"
                      style={{ animationDelay: `${i * 50}ms` }}
                    >
                      <td className="py-3">
                        <div className="font-medium">
                          {client.business_name}
                        </div>
                        <div className="text-white/40 text-xs">
                          {client.owner_name}
                        </div>
                      </td>
                      <td className="py-3">
                        <span
                          className={`status-pill status-${client.status_color}`}
                        >
                          {client.status_reason}
                        </span>
                      </td>
                      <td className="py-3 text-right font-mono">
                        {client.invoice_count}
                      </td>
                      <td className="py-3 text-right font-mono text-green-400">
                        {formatINR(client.confirmed_itc_total)}
                      </td>
                      <td className="py-3 flex justify-center">
                        <ReadinessRing percentage={pct} size={40} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Alert Panel */}
          <div className="glass-card p-5">
            <div className="flex items-center gap-2 mb-4">
              <AlertTriangle size={16} className="text-gold" />
              <h3 className="text-sm text-white/50">Alerts</h3>
              {alertsData && alertsData.total > 0 && (
                <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse-dot" />
              )}
            </div>
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {alertsData?.alerts.map((alert, i) => (
                <div
                  key={i}
                  className={`p-3 rounded-lg border text-sm ${
                    alert.severity === "red"
                      ? "bg-red-500/5 border-red-500/20 text-red-300"
                      : "bg-yellow-500/5 border-yellow-500/20 text-yellow-300"
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <div
                      className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${
                        alert.severity === "red"
                          ? "bg-red-500 animate-pulse-dot"
                          : "bg-yellow-500"
                      }`}
                    />
                    <span>{alert.message}</span>
                  </div>
                </div>
              ))}
              {(!alertsData || alertsData.total === 0) && (
                <p className="text-white/30 text-sm text-center py-8">
                  No alerts
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
