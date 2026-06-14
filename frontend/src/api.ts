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
};

export type Bucket = {
  id: string;
  name: string;
  target_amount: number;
  saved_amount: number;
  image_key: string;
  is_default: boolean;
};

export type Transaction = {
  id: string;
  merchant: string;
  amount: number;
  category_id: string;
  category_name: string;
  tax_rate: number;
  tax_amount: number;
  bucket_id: string;
  bucket_name: string;
  note?: string | null;
  created_at: string;
};

export type Summary = {
  total_spent: number;
  total_taxed: number;
  transactions: number;
  by_category: { name: string; spent: number; taxed: number; count: number }[];
  by_day: { date: string; spent: number; taxed: number }[];
  streak_days_no_impulse: number;
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

  transactions: (limit = 100) => req<Transaction[]>(`/transactions?limit=${limit}`),
  createTransaction: (data: {
    merchant: string;
    amount: number;
    category_id: string;
    note?: string;
    bucket_id?: string;
  }) => req<Transaction>("/transactions", { method: "POST", body: JSON.stringify(data) }),
  deleteTransaction: (id: string) => req<{ ok: boolean }>(`/transactions/${id}`, { method: "DELETE" }),

  summary: () => req<Summary>("/insights/summary"),
};
