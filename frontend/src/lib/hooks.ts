"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type {
  DashboardOverview,
  DashboardSummary,
  AlertsResponse,
  Client,
  Invoice,
  ITCSummary,
} from "@/types";

// Dashboard
export function useDashboardOverview() {
  return useQuery<DashboardOverview>({
    queryKey: ["dashboard", "overview"],
    queryFn: () => api.get("/dashboard/overview"),
  });
}

export function useDashboardSummary(period: string) {
  return useQuery<DashboardSummary>({
    queryKey: ["dashboard", "summary", period],
    queryFn: () => api.get(`/dashboard/summary?period=${period}`),
    enabled: !!period,
  });
}

export function useAlerts() {
  return useQuery<AlertsResponse>({
    queryKey: ["dashboard", "alerts"],
    queryFn: () => api.get("/dashboard/alerts"),
    refetchInterval: 30000,
  });
}

// Clients
export function useClients() {
  return useQuery<Client[]>({
    queryKey: ["clients"],
    queryFn: () => api.get("/clients/"),
  });
}

export function useClientITCSummary(clientId: string, period: string) {
  return useQuery<ITCSummary>({
    queryKey: ["clients", clientId, "itc", period],
    queryFn: () => api.get(`/clients/${clientId}/itc-summary?period=${period}`),
    enabled: !!clientId && !!period,
  });
}

// Invoices
export function useInvoices(params?: {
  status?: string;
  client_id?: string;
  skip?: number;
  limit?: number;
}) {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set("status", params.status);
  if (params?.client_id) searchParams.set("client_id", params.client_id);
  if (params?.skip) searchParams.set("skip", String(params.skip));
  if (params?.limit) searchParams.set("limit", String(params.limit));
  const qs = searchParams.toString();

  return useQuery<Invoice[]>({
    queryKey: ["invoices", params],
    queryFn: () => api.get(`/invoices/?${qs}`),
  });
}

export function useBulkAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { invoice_ids: string[]; action: string }) =>
      api.post("/invoices/bulk-action", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invoices"] }),
  });
}
