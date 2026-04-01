export interface ClientStatus {
  client_id: string;
  business_name: string;
  owner_name: string;
  status_color: "green" | "yellow" | "red";
  status_reason: string;
  invoice_count: number;
  pending_ca_review_count: number;
  flagged_low_confidence_count: number;
  draft_itc_total: string;
  confirmed_itc_total: string;
  gstr3b_deadline: string;
  days_to_deadline: number;
}

export interface DashboardOverview {
  clients: ClientStatus[];
  total_clients: number;
  total_invoices: number;
  total_draft_itc: string;
  total_confirmed_itc: string;
}

export interface DashboardSummary {
  period: string;
  cgst_confirmed: string;
  sgst_confirmed: string;
  igst_confirmed: string;
  total_confirmed: string;
  total_pending: string;
  total_rejected: string;
  rcm_liability: string;
  invoice_count: number;
}

export interface Alert {
  type: string;
  severity: "red" | "yellow" | "green";
  message: string;
  client_id: string | null;
  client_name: string | null;
  created_at: string;
}

export interface AlertsResponse {
  alerts: Alert[];
  total: number;
}

export interface Client {
  id: string;
  business_name: string;
  owner_name: string;
  gstin: string | null;
  whatsapp_phone: string;
  business_type: string;
  is_active: boolean;
  created_at: string;
}

export interface Invoice {
  id: string;
  client_id: string;
  ca_id: string;
  source_type: string;
  seller_gstin: string | null;
  seller_name: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  taxable_amount: string | null;
  cgst_amount: string | null;
  sgst_amount: string | null;
  igst_amount: string | null;
  total_amount: string | null;
  category: string | null;
  is_itc_eligible_draft: boolean | null;
  is_rcm: boolean;
  rcm_category: string | null;
  status: string;
  ca_reviewed_at: string | null;
  created_at: string;
}

export interface ITCSummary {
  client_id: string;
  period: string;
  cgst_confirmed: string;
  sgst_confirmed: string;
  igst_confirmed: string;
  total_confirmed: string;
  total_pending: string;
  total_rejected: string;
  rcm_liability: string;
  invoice_count: number;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}
