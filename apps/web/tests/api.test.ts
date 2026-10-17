import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/lib/api";

describe("api client", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/login");
    Object.defineProperty(document, "cookie", { configurable: true, value: "orvexadb_csrf=csrf-test" });
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => vi.restoreAllMocks());

  it("sends the CSRF cookie value only as a mutation header", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    await api("/products", { method: "POST", body: JSON.stringify({ name: "Demo" }) });
    const [, request] = vi.mocked(fetch).mock.calls[0];
    expect(new Headers((request as RequestInit).headers).get("X-CSRF-Token")).toBe("csrf-test");
    expect(localStorage.getItem("orvexadb_csrf")).toBeNull();
    expect(sessionStorage.getItem("orvexadb_csrf")).toBeNull();
  });

  it("marks unauthenticated responses so the UI can redirect to login", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "private detail" }), { status: 401 }));
    let error: { status: number } | undefined;
    try { await api("/dashboard/summary"); } catch (value) { error = value as { status: number }; }
    expect(error).toBeDefined();
    expect(error?.status).toBe(401);
  });

  it("turns rate limits into a user-facing wait message", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "too many" }), { status: 429 }));
    await expect(api("/auth/login", { method: "POST", body: "{}" })).rejects.toThrow("Demasiados intentos");
  });

  it("preserves forbidden and conflict statuses for the UI", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "forbidden" }), { status: 403 }));
    await expect(api("/admin/users")).rejects.toMatchObject({ status: 403 });
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "conflict" }), { status: 409 }));
    await expect(api("/products", { method: "POST", body: "{}" })).rejects.toMatchObject({ status: 409 });
  });
});
