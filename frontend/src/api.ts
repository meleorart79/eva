import { storage } from "./utils/storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;
const TOKEN_KEY = "eva_token";

export type User = {
  id: string;
  email: string;
  name: string;
  currency: string;
  default_bucket_id?: string | null;
};

export type Category = {
  id: string;
  name: string;
  icon: string;
  tax_rate: number;
  merchant_keywords: string[];
  rep_increment: number;
  max_tax_rate: number;
  daily_cap_amount: number;
};

export type Bucket = {
  id: string;
  name: string;
  target_amount: number;
  saved_amount: number;
  image_key: string;
  is_default: boolean;
};

export type LinkedAccount = {
  id: string;
  provider: "revolut" | "spuerkeess";
  is_active: boolean;
  linked_at: string;
  consent_url?: string | null;
};

export type Settings = {
  profile_type: "balanced" | "aggressive" | "ethical" | "mindful" | "savings_beast";
  transfer_frequency: "instant" | "daily" | "weekly";
  pause_all_taxes: boolean;
  transfer_last_run_at?: string | null;
};

export type SavingsDestination = {
  id: string;
  type: "external_iban" | "revolut_pocket";
  label: string;
  identifier: string;
  currency: string;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
};

export type MonthlyReport = {
  year: number;
  month: number;
  totals: { spent: number; taxed: number; events: number; overridden: number; requires_review: number };
  by_category: { name: string; taxed: number }[];
  by_profile: { name: string; taxed: number }[];
  by_destination: { label: string; taxed: number }[];
  by_transfer_status: { status: string; count: number }[];
  events: {
    transacted_at: string;
    merchant: string;
    category?: string;
    original_amount: number;
    currency: string;
    profile?: string;
    tax_rate: number;
    tax_amount: number;
    source_label?: string;
    destination_label?: string;
    transfer_status?: string;
    transfer_provider_ref?: string;
    status?: string;
  }[];
};

export type ActivityRow = {
  raw_txn_id: string;
  merchant_name: string;
  amount: number;
  currency: string;
  transacted_at: string;
  category_id?: string | null;
  category_name?: string | null;
  tax_event_id?: string | null;
  tax_amount: number;
  tax_rate_applied: number;
  repetition_number: number;
  status: "saved" | "skipped" | "overridden" | "unmatched" | "pending";
  created_at?: string | null;
  can_override: boolean;
  profile_applied?: string | null;
  source_account_id?: string | null;
  source_label?: string | null;
  source_type?: string | null;
  source_currency?: string | null;
  destination_id?: string | null;
  destination_label?: string | null;
  destination_currency?: string | null;
  transfer_status?: "pending" | "executed" | "failed" | "requires_review" | null;
  transfer_provider_ref?: string | null;
  requires_review?: boolean;
};

export type Summary = {
  total_spent: number;
  total_taxed: number;
  transactions: number;
  by_category: { name: string; spent: number; taxed: number; count: number }[];
  by_day: { date: string; spent: number; taxed: number }[];
  streak_days_no_impulse: number;
  profile_type: string;
};

export async function getToken(): Promise<string | null> {
  return (await storage.secureGet<string>(TOKEN_KEY, "")) || null;
}
export async function setToken(t: string) {
  await storage.secureSet(TOKEN_KEY, t);
}
export async function clearToken() {
  await storage.secureRemove(TOKEN_KEY);
}

async function req<T>(path: string, opts: RequestInit = {}, auth = true): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts.headers as Record<string, string> | undefined),
  };
  if (auth) {
    const t = await getToken();
    if (t) headers.Authorization = `Bearer ${t}`;
  }
  const res = await fetch(`${BASE}/api${path}`, { ...opts, headers });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || `Request failed (${res.status})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data as T;
}

export const api = {
  register: (email: string, password: string, name: string, currency: string) =>
    req<{ access_token: string; user: User }>(
      "/auth/register",
      { method: "POST", body: JSON.stringify({ email, password, name, currency }) },
      false,
    ),
  login: (email: string, password: string) =>
    req<{ access_token: string; user: User }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      false,
    ),
  me: () => req<User>("/auth/me"),
  updateMe: (params: { currency?: string; name?: string; default_bucket_id?: string }) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && qs.append(k, String(v)));
    return req<User>(`/auth/me?${qs.toString()}`, { method: "PATCH" });
  },

  categories: () => req<Category[]>("/categories"),
  createCategory: (data: Omit<Category, "id">) =>
    req<Category>("/categories", { method: "POST", body: JSON.stringify(data) }),
  updateCategory: (id: string, data: Omit<Category, "id">) =>
    req<Category>(`/categories/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteCategory: (id: string) => req<{ ok: boolean }>(`/categories/${id}`, { method: "DELETE" }),

  buckets: () => req<Bucket[]>("/buckets"),
  createBucket: (data: { name: string; target_amount: number; image_key: string; is_default?: boolean }) =>
    req<Bucket>("/buckets", { method: "POST", body: JSON.stringify(data) }),
  updateBucket: (id: string, data: { name: string; target_amount: number; image_key: string; is_default?: boolean }) =>
    req<Bucket>(`/buckets/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteBucket: (id: string) => req<{ ok: boolean }>(`/buckets/${id}`, { method: "DELETE" }),

  // Bank linking
  linkBank: (provider: "revolut" | "spuerkeess", access_token?: string) =>
    req<LinkedAccount>("/bank/link", {
      method: "POST",
      body: JSON.stringify(
        access_token ? { provider, access_token } : { provider },
      ),
    }),
  listAccounts: () => req<LinkedAccount[]>("/bank/accounts"),
  unlinkBank: (id: string) => req<{ ok: boolean }>(`/bank/accounts/${id}`, { method: "DELETE" }),
  syncBank: () =>
    req<{ ingested: number; duplicates: number; accounts: number }>(`/bank/sync`, { method: "POST" }),

  // Settings
  getSettings: () => req<Settings>("/settings"),
  patchSettings: (data: Partial<Settings>) =>
    req<Settings>("/settings", { method: "PATCH", body: JSON.stringify(data) }),

  // Savings destinations
  listDestinations: () => req<SavingsDestination[]>("/destinations"),
  createDestination: (data: Omit<SavingsDestination, "id" | "is_active" | "created_at">) =>
    req<SavingsDestination>("/destinations", { method: "POST", body: JSON.stringify(data) }),
  updateDestination: (id: string, data: Omit<SavingsDestination, "id" | "is_active" | "created_at">) =>
    req<SavingsDestination>(`/destinations/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteDestination: (id: string) => req<{ ok: boolean }>(`/destinations/${id}`, { method: "DELETE" }),

  // Scheduler + monthly resume
  runScheduler: () => req<{ ok: boolean; transfers: unknown[] }>("/scheduler/run", { method: "POST" }),
  monthlyReport: (year: number, month: number) =>
    req<MonthlyReport>(`/reports/monthly?year=${year}&month=${month}`),
  monthlyReportCsvUrl: (year: number, month: number) =>
    `${BASE}/api/reports/monthly/export.csv?year=${year}&month=${month}`,

  // Tax engine
  processTax: () =>
    req<{ processed: number; taxed: number; skipped: number; unmatched: number }>(
      `/tax/process`, { method: "POST" }
    ),
  overrideTax: (event_id: string) =>
    req<{ ok: boolean }>(`/tax/override/${event_id}`, { method: "POST" }),
  transferTax: () =>
    req<{ transferred: number; total_amount: number; transfer_id?: string }>(
      `/tax/transfer`, { method: "POST" }
    ),

  // Activity / insights
  activity: (limit = 100) => req<ActivityRow[]>(`/activity?limit=${limit}`),
  summary: () => req<Summary>("/insights/summary"),
};
