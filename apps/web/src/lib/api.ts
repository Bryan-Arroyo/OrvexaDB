export type ApiError = Error & { status?: number };

function csrfToken(): string | undefined {
  return document.cookie.split("; ").find((item) => item.startsWith("orvexadb_csrf="))?.split("=")[1];
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (method !== "GET" && method !== "HEAD") {
    const token = csrfToken();
    if (token) headers.set("X-CSRF-Token", decodeURIComponent(token));
  }
  const response = await fetch(`/api/v1${path}`, { ...init, headers, credentials: "same-origin" });
  if (response.status === 401 && typeof window !== "undefined" && window.location.pathname !== "/login" && !path.startsWith("/auth/login")) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
  }
  if (!response.ok) {
    let detail = "No se pudo completar la operación.";
    try { const payload = await response.json(); detail = typeof payload.detail === "string" ? payload.detail : detail; } catch { /* empty body */ }
    const error = new Error(response.status === 429 ? "Demasiados intentos. Espera unos minutos." : detail) as ApiError;
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function invalidatePreviousSession(): Promise<void> {
  await api<void>("/auth/logout", { method: "POST" }).catch(() => undefined);
}

export type User = { id: string; username: string; email: string; is_active: boolean; must_change_password: boolean; role: string | null; permissions: string[] };
export type Page<T> = { items: T[]; page: number; page_size: number; total: number };
export type Category = { id: string; code: string; name: string; is_active: boolean; created_at: string; updated_at: string };
export type Supplier = Category;
export type Product = { id: string; sku: string; name: string; category_id: string | null; supplier_id: string | null; stock_current: string; minimum_stock: string; unit_cost: string; is_active: boolean };
export type Movement = { id: string; product_id: string; product_name?: string | null; product_sku?: string | null; quantity: string; direction: string; reason: string; description?: string | null; occurred_at: string };
export type Dashboard = { active_products: number; active_suppliers: number; total_stock: string; low_stock_products: number; recent_movements: Movement[] };
export type PurchaseLine = { id: string; product_id: string; product_sku: string; product_name: string; quantity: string; unit_cost: string; line_total: string };
export type PurchaseOrder = { id: string; number: string; supplier_id: string; supplier_name: string; status: "draft" | "confirmed" | "received" | "canceled"; created_at: string; lines: PurchaseLine[]; total: string };
