import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App, { Login } from "../src/app/App";
import type { PurchaseOrder } from "../src/lib/api";

const baseUser = { id: "u1", username: "ana", email: "ana@example.test", is_active: true, must_change_password: false, role: "employee", permissions: ["inventory.read", "product.read", "product.create", "product.update", "product.deactivate", "inventory.move"] };
const page = { items: [], page: 1, page_size: 25, total: 0 };
function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } }); }

describe("flujos de aplicación", () => {
  beforeEach(() => { vi.stubGlobal("fetch", vi.fn()); window.sessionStorage.setItem("orvexa:authenticated-visit", "1"); window.history.pushState({}, "", "/dashboard"); });
  afterEach(() => { cleanup(); window.sessionStorage.clear(); vi.restoreAllMocks(); });

  it("muestra login para una sesión no autenticada", async () => {
    window.history.pushState({}, "", "/login");
    vi.mocked(fetch).mockResolvedValue(response({ detail: "unauthorized" }, 401));
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Iniciar sesión" })).toBeVisible();
    expect(screen.getByLabelText("Usuario o correo")).toBeEnabled();
  });

  it("muestra login en /login aunque exista cookie y no consulta auth/me", async () => {
    window.history.pushState({}, "", "/login");
    document.cookie = "orvexadb_session=previous";
    vi.mocked(fetch).mockResolvedValue(response({ detail: "unauthorized" }, 401));
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Iniciar sesión" })).toBeVisible();
    expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input).includes("auth/me"))).toBe(false);
  });

  it("no pide datos protegidos sin marcador de visita", async () => {
    window.sessionStorage.clear();
    window.history.pushState({}, "", "/dashboard");
    vi.mocked(fetch).mockResolvedValue(response({ detail: "unauthorized" }, 401));
    render(<App />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input).includes("auth/me"))).toBe(false);
  });

  it("login exitoso establece marcador de visita y entrega usuario", async () => {
    const onLogin = vi.fn();
    vi.mocked(fetch).mockResolvedValue(response(baseUser));
    render(<Login onLogin={onLogin} />);
    fireEvent.change(screen.getByLabelText("Usuario o correo"), { target: { value: "ana" } });
    fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "correct horse battery" } });
    fireEvent.submit(screen.getByRole("button", { name: "Entrar" }).closest("form")!);
    await waitFor(() => expect(onLogin).toHaveBeenCalledWith(baseUser));
    expect(window.sessionStorage.getItem("orvexa:authenticated-visit")).toBe("1");
  });

  it("bloquea la aplicación hasta cambiar una contraseña temporal", async () => {
    vi.mocked(fetch).mockResolvedValue(response({ ...baseUser, must_change_password: true }));
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Cambia tu contraseña" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Cerrar sesión" })).toBeVisible();
  });

  it("muestra acceso denegado y oculta navegación no autorizada", async () => {
    window.history.pushState({}, "", "/admin/users");
    vi.mocked(fetch).mockResolvedValue(response(baseUser));
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Acceso denegado" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Usuarios" })).not.toBeInTheDocument();
  });

  it("expone el formulario de producto con sus campos de negocio", async () => {
    window.history.pushState({}, "", "/products");
    vi.mocked(fetch).mockImplementation(async (input) => String(input).includes("auth/me") ? response(baseUser) : response(page));
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Productos" })).toBeVisible();
    expect(screen.getByLabelText("SKU")).toBeVisible();
    expect(screen.getByLabelText("Coste unitario")).toBeVisible();
    expect(screen.getByLabelText("Stock mínimo")).toBeVisible();
  });

  it("expone el formulario de movimientos con dirección y motivo", async () => {
    window.history.pushState({}, "", "/inventory");
    vi.mocked(fetch).mockImplementation(async (input) => String(input).includes("auth/me") ? response(baseUser) : response(page));
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Movimientos" })).toBeVisible();
    expect(screen.getByLabelText("Dirección")).toBeVisible();
    expect(screen.getByLabelText("Motivo")).toBeVisible();
  });

  it("presenta los indicadores del dashboard", async () => {
    const dashboard = { active_products: 3, active_suppliers: 2, total_stock: "14.00", low_stock_products: 1, recent_movements: [] };
    vi.mocked(fetch).mockImplementation(async (input) => String(input).includes("auth/me") ? response(baseUser) : response(dashboard));
    render(<App />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Resumen de inventario" })).toBeVisible());
    expect(await screen.findByText("Productos activos")).toBeVisible();
    expect(await screen.findByText("Stock total")).toBeVisible();
  });

  it("muestra y permite ocultar la contraseña temporal de un usuario creado", async () => {
    window.history.pushState({}, "", "/admin/users");
    const administrator = { ...baseUser, role: "administrator", permissions: ["inventory.read", "user.manage"] };
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("auth/me")) return response(administrator);
      if (url.endsWith("/admin/users") && init?.method === "POST") return response({ user: { ...administrator, id: "u2" }, temporary_password: "Temp-pass-123456" }, 201);
      return response({ ...page, items: [administrator] });
    });
    render(<App />);
    await screen.findByRole("heading", { name: "Usuarios" });
    fireEvent.change(screen.getByLabelText("Usuario"), { target: { value: "employee" } });
    fireEvent.change(screen.getByLabelText("Correo"), { target: { value: "employee@example.test" } });
    fireEvent.submit(screen.getByRole("button", { name: "Crear usuario" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Temp-pass-123456");
    fireEvent.click(screen.getByRole("button", { name: "Ocultar" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("refleja en la tabla el nombre actualizado tras editar un producto", async () => {
    window.history.pushState({}, "", "/products");
    let productName = "Producto inicial";
    const product = () => ({ id: "p1", sku: "SKU-1", name: productName, category_id: "c1", supplier_id: null, stock_current: "0", minimum_stock: "1", unit_cost: "2.00", is_active: true });
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("auth/me")) return response(baseUser);
      if (url.endsWith("/products/p1") && init?.method === "PATCH") { productName = "Producto actualizado"; return response(product()); }
      if (url.endsWith("/products")) return response({ items: [product()], page: 1, page_size: 25, total: 1 });
      return response(page);
    });
    render(<App />);
    await screen.findByRole("cell", { name: "Producto inicial" });
    fireEvent.change(screen.getByLabelText("Producto"), { target: { value: "p1" } });
    fireEvent.change(screen.getAllByLabelText("Nombre", { exact: true }).at(-1)!, { target: { value: "Producto actualizado" } });
    fireEvent.submit(screen.getByRole("button", { name: "Guardar cambios" }).closest("form")!);
    expect(await screen.findByRole("cell", { name: "Producto actualizado" })).toBeVisible();
  });

  it("muestra la descripción del movimiento creado", async () => {
    window.history.pushState({}, "", "/inventory");
    let created = false;
    const product = { id: "p1", sku: "SKU-1", name: "Producto", category_id: "c1", supplier_id: null, stock_current: "0", minimum_stock: "0", unit_cost: "1.00", is_active: true };
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("auth/me")) return response(baseUser);
      if (url.endsWith("/products")) return response({ items: [product], page: 1, page_size: 25, total: 1 });
      if (url.endsWith("/inventory-movements") && init?.method === "POST") { created = true; return response({ id: "m1", product_id: "p1", quantity: "4", direction: "in", reason: "purchase", description: "Entrada aislada", occurred_at: new Date().toISOString() }, 201); }
      return response({ items: created ? [{ id: "m1", product_id: "p1", quantity: "4", direction: "in", reason: "purchase", description: "Entrada aislada", occurred_at: new Date().toISOString() }] : [], page: 1, page_size: 25, total: created ? 1 : 0 });
    });
    render(<App />);
    await screen.findByRole("heading", { name: "Movimientos" });
    fireEvent.change(screen.getByLabelText("Producto"), { target: { value: "p1" } });
    fireEvent.change(screen.getByLabelText("Cantidad"), { target: { value: "4" } });
    fireEvent.change(screen.getByLabelText("Descripción"), { target: { value: "Entrada aislada" } });
    fireEvent.submit(screen.getByRole("button", { name: "Registrar" }).closest("form")!);
    expect(await screen.findByRole("cell", { name: "Entrada aislada" })).toBeVisible();
  });

  it("carga y crea una categoría desde el formulario", async () => {
    window.history.pushState({}, "", "/categories");
    let created = false;
    const administrator = { ...baseUser, role: "administrator", permissions: ["product.read", "category.manage"] };
    const category = () => ({ id: "c1", code: created ? "CAT-2" : "CAT-1", name: created ? "Nueva categoría" : "Categoría inicial", is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" });
    vi.mocked(fetch).mockImplementation(async (input, init) => { const url = String(input); if (url.includes("auth/me")) return response(administrator); if (url.endsWith("/categories") && init?.method === "POST") { created = true; return response(category(), 201); } if (url.endsWith("/categories")) return response({ items: [category()], page: 1, page_size: 25, total: 1 }); return response(page); });
    render(<App />);
    expect(await screen.findByRole("cell", { name: "Categoría inicial" })).toBeVisible();
    fireEvent.change(screen.getByLabelText("Código"), { target: { value: "CAT-2" } });
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Nueva categoría" } });
    fireEvent.submit(screen.getByRole("button", { name: "Crear" }).closest("form")!);
    expect(await screen.findByRole("cell", { name: "Nueva categoría" })).toBeVisible();
  });

  it("carga y crea un proveedor desde el formulario", async () => {
    window.history.pushState({}, "", "/suppliers");
    let created = false;
    const administrator = { ...baseUser, role: "administrator", permissions: ["product.read", "supplier.manage"] };
    const supplier = () => ({ id: "s1", code: created ? "SUP-2" : "SUP-1", name: created ? "Nuevo proveedor" : "Proveedor inicial", is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" });
    vi.mocked(fetch).mockImplementation(async (input, init) => { const url = String(input); if (url.includes("auth/me")) return response(administrator); if (url.endsWith("/suppliers") && init?.method === "POST") { created = true; return response(supplier(), 201); } if (url.endsWith("/suppliers")) return response({ items: [supplier()], page: 1, page_size: 25, total: 1 }); return response(page); });
    render(<App />);
    expect(await screen.findByRole("cell", { name: "Proveedor inicial" })).toBeVisible();
    fireEvent.change(screen.getByLabelText("Código"), { target: { value: "SUP-2" } });
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Nuevo proveedor" } });
    fireEvent.submit(screen.getByRole("button", { name: "Crear" }).closest("form")!);
    expect(await screen.findByRole("cell", { name: "Nuevo proveedor" })).toBeVisible();
  });

  it("crea, confirma y recibe una orden de compra", async () => {
    window.history.pushState({}, "", "/purchases");
    const administrator = { ...baseUser, role: "administrator", permissions: ["purchase.read", "purchase.manage", "purchase.receive"] };
    const supplier = { id: "s1", code: "SUP-1", name: "Proveedor", is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" };
    const product = { id: "p1", sku: "SKU-1", name: "Producto", category_id: "c1", supplier_id: null, stock_current: "0", minimum_stock: "0", unit_cost: "2.00", is_active: true };
    let order: PurchaseOrder = { id: "o1", number: "OC-1", supplier_id: "s1", supplier_name: "Proveedor", status: "draft", created_at: "2026-01-01T00:00:00Z", lines: [{ id: "l1", product_id: "p1", product_sku: "SKU-1", product_name: "Producto", quantity: "4", unit_cost: "2.00", line_total: "8.00" }], total: "8.00" };
    vi.mocked(fetch).mockImplementation(async (input, init) => { const url = String(input); if (url.includes("auth/me")) return response(administrator); if (url.includes("/suppliers") && init?.method !== "POST") return response({ items: [supplier], page: 1, page_size: 25, total: 1 }); if (url.includes("/products")) return response({ items: [product], page: 1, page_size: 25, total: 1 }); if (url.endsWith("/purchase-orders") && init?.method === "POST") return response(order, 201); if (url.endsWith("/confirm")) { order = { ...order, status: "confirmed" }; return response(order); } if (url.endsWith("/receive")) { order = { ...order, status: "received" }; return response(order); } return response({ items: [order], page: 1, page_size: 50, total: 1 }); });
    render(<App />);
    await screen.findByRole("heading", { name: "Compras" });
    fireEvent.click(screen.getByRole("button", { name: "Nueva compra" }));
    fireEvent.change(await screen.findByLabelText("Proveedor"), { target: { value: "s1" } });
    fireEvent.change(screen.getByLabelText("Producto"), { target: { value: "p1" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear borrador" }));
    await screen.findByText("OC-1");
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    expect((await screen.findAllByText("Confirmada")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Recibir compra" }));
    expect((await screen.findAllByText("Recibida")).length).toBeGreaterThan(0);
  });

  it("busca proveedores y productos fuera de la primera página al crear una compra", async () => {
    window.history.pushState({}, "", "/purchases");
    const administrator = { ...baseUser, role: "administrator", permissions: ["purchase.read", "purchase.manage", "purchase.receive"] };
    const firstSupplier = { id: "s1", code: "SUP-1", name: "Proveedor inicial", is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" };
    const remoteSupplier = { id: "s99", code: "SUP-99", name: "Proveedor remoto", is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" };
    const firstProduct = { id: "p1", sku: "SKU-1", name: "Producto inicial", category_id: "c1", supplier_id: null, stock_current: "0", minimum_stock: "0", unit_cost: "2.00", is_active: true };
    const remoteProduct = { id: "p99", sku: "SKU-99", name: "Producto remoto", category_id: "c1", supplier_id: null, stock_current: "0", minimum_stock: "0", unit_cost: "3.00", is_active: true };
    const requests: string[] = [];
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input); requests.push(url);
      if (url.includes("auth/me")) return response(administrator);
      if (url.includes("/suppliers")) return response({ items: url.includes("REMOTO") ? [remoteSupplier] : [firstSupplier], page: 1, page_size: 100, total: 1 });
      if (url.includes("/products")) return response({ items: url.includes("REMOTO") ? [remoteProduct] : [firstProduct], page: 1, page_size: 100, total: 1 });
      return response({ items: [], page: 1, page_size: 25, total: 0 });
    });
    render(<App />);
    await screen.findByRole("heading", { name: "Compras" });
    fireEvent.click(screen.getByRole("button", { name: "Nueva compra" }));
    fireEvent.change(await screen.findByLabelText("Buscar proveedor"), { target: { value: "REMOTO" } });
    expect(await screen.findByRole("option", { name: "SUP-99 · Proveedor remoto" })).toBeVisible();
    expect(requests.some((url) => url.includes("/suppliers?search=REMOTO") && url.includes("active=true") && url.includes("page_size=100"))).toBe(true);
    fireEvent.change(screen.getByLabelText("Proveedor"), { target: { value: "s99" } });
    fireEvent.change(screen.getByLabelText("Buscar producto"), { target: { value: "REMOTO" } });
    expect(await screen.findByRole("option", { name: "SKU-99 · Producto remoto" })).toBeVisible();
    expect(requests.some((url) => url.includes("/products?search=REMOTO") && url.includes("active=true") && url.includes("page_size=100"))).toBe(true);
    fireEvent.change(screen.getByLabelText("Producto"), { target: { value: "p99" } });
    expect(screen.getByLabelText("Producto")).toHaveValue("p99");
  });
});
