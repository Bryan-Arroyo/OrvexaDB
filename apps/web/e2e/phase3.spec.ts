import { test, expect, type Page, type TestInfo } from "@playwright/test";
import { createProduct, login, navigate, uniqueName } from "./fixtures";

test.describe.configure({ mode: "serial" });

async function createSupplier(page: Page, testInfo: TestInfo) {
  const code = uniqueName("sup", testInfo).slice(0, 24).toUpperCase();
  const name = uniqueName("Proveedor", testInfo);
  await navigate(page, "Proveedores");
  await expect(page.getByRole("heading", { name: "Proveedores" })).toBeVisible();
  await page.getByLabel("Código").fill(code);
  await page.getByLabel("Nombre").fill(name);
  const createResponse = page.waitForResponse((response) => response.url().includes("/api/v1/suppliers") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Crear" }).click();
  await expect((await createResponse).status()).toBe(201);
  return { code, name };
}

test.describe("Fase 3: compra y recepción", () => {
  test("crea, confirma, recibe y verifica stock y movimiento", async ({ page }, testInfo) => {
    test.setTimeout(30_000);
    await login(page);
    const supplier = await createSupplier(page, testInfo);
    const product = await createProduct(page, testInfo);
    await navigate(page, "Compras");
    await expect(page.getByRole("heading", { name: "Compras" })).toBeVisible();
    await page.getByRole("button", { name: "Nueva compra" }).click();
    await page.getByLabel("Proveedor", { exact: true }).selectOption({ label: `${supplier.code} · ${supplier.name}` });
    await page.getByLabel("Producto", { exact: true }).selectOption({ label: `${product.sku} · ${product.name}` });
    await page.getByLabel("Cantidad").fill("5");
    await page.getByLabel("Coste unitario").fill("12.50");
    await page.getByRole("button", { name: "Crear borrador" }).click();
    await expect(page.getByRole("button", { name: "Confirmar" })).toBeVisible();
    await page.getByRole("button", { name: "Confirmar" }).click();
    await expect(page.getByRole("heading", { name: "Confirmada" })).toBeVisible();
    await page.getByRole("button", { name: "Recibir compra" }).click();
    await expect(page.getByRole("heading", { name: "Recibida" })).toBeVisible();
    await navigate(page, "Productos");
    const productRow = page.getByRole("row").filter({ hasText: product.sku });
    await expect(productRow).toBeVisible();
    await expect(productRow).toContainText("5");
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: /Resumen de inventario/ })).toBeVisible();
    const movementRow = page.getByRole("row").filter({ hasText: product.sku });
    await expect(movementRow).toContainText(product.name);
    await expect(movementRow).toContainText("Compra");
    const layout = await page.evaluate(() => ({ innerWidth: window.innerWidth, scrollWidth: document.documentElement.scrollWidth, widest: [...document.querySelectorAll<HTMLElement>("*")].map((element) => ({ tag: element.tagName, className: element.className, right: element.getBoundingClientRect().right })).filter((item) => item.right > window.innerWidth + 1).sort((a, b) => b.right - a.right).slice(0, 3) }));
    expect(layout.scrollWidth, JSON.stringify(layout)).toBeLessThanOrEqual(layout.innerWidth + 1);
    await page.screenshot({ path: "test-results/phase3-dashboard-mobile.png", fullPage: true });
  });

  test("muestra la compra usable en móvil", async ({ page }) => {
    await login(page);
    await navigate(page, "Compras");
    await expect(page.getByRole("heading", { name: "Compras" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Nueva compra" })).toBeVisible();
  });
});
