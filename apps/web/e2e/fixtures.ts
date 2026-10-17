import { expect, type Page, type TestInfo } from "@playwright/test";

export function credentials() {
  const username = process.env.E2E_ADMIN_USERNAME ?? process.env.E2E_USERNAME;
  const password = process.env.E2E_ADMIN_PASSWORD ?? process.env.E2E_PASSWORD;
  if (!username || !password) {
    throw new Error("E2E_USERNAME y E2E_PASSWORD son obligatorias solo en runtime para las pruebas aisladas.");
  }
  return { username, password };
}

export function uniqueName(prefix: string, testInfo: TestInfo) {
  const run = process.env.E2E_RUN_ID ?? String(Date.now());
  const testMarker = testInfo.title.replace(/[^a-zA-Z0-9_-]/g, "-").slice(0, 16);
  const projectMarker = testInfo.project.name.replace(/[^a-zA-Z0-9_-]/g, "-").slice(0, 6);
  return `${prefix}-${projectMarker}-${run.slice(-8)}-${testMarker}`.replace(/[^a-zA-Z0-9_-]/g, "-").slice(0, 48);
}

export async function login(page: Page, username?: string, password?: string, options: { expectPasswordChange?: boolean } = {}) {
  const admin = credentials();
  await page.goto("/login");
  await page.getByLabel("Usuario o correo").fill(username ?? admin.username);
  await page.getByLabel("Contraseña", { exact: true }).fill(password ?? admin.password);
  await page.getByRole("button", { name: "Entrar" }).click();
  if (options.expectPasswordChange) {
    await expect(page.getByRole("heading", { name: "Cambia tu contraseña" })).toBeVisible();
  } else {
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByRole("heading", { name: /Resumen( de inventario)?/ })).toBeVisible();
  }
}

export async function navigate(page: Page, name: string) {
  const menu = page.getByRole("button", { name: "Abrir menú" });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name }).click();
}

export async function createCategory(page: Page, testInfo: TestInfo) {
  const code = uniqueName("cat", testInfo).slice(0, 24).toUpperCase();
  const name = uniqueName("Categoría", testInfo);
  await navigate(page, "Categorías");
  await expect(page.getByRole("heading", { name: "Categorías" })).toBeVisible();
  await page.getByLabel("Código").fill(code);
  await page.getByLabel("Nombre").fill(name);
  const createResponse = page.waitForResponse((response) => response.url().includes("/api/v1/categories") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Crear" }).click();
  await expect((await createResponse).status()).toBe(201);
  return { code, name };
}

export async function createProduct(page: Page, testInfo: TestInfo) {
  const category = await createCategory(page, testInfo);
  await navigate(page, "Productos");
  await expect(page.getByRole("heading", { name: "Productos" })).toBeVisible();
  const sku = uniqueName("sku", testInfo).slice(0, 24).toUpperCase();
  const name = uniqueName("Producto", testInfo);
  await page.getByLabel("SKU").fill(sku);
  await page.getByLabel("Nombre", { exact: true }).fill(name);
  await page.getByLabel("Categoría").selectOption({ label: category.name });
  await page.getByLabel("Coste unitario").fill("12.50");
  await page.getByLabel("Stock mínimo").fill("2");
  const createResponse = page.waitForResponse((response) => response.url().includes("/api/v1/products") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Crear producto" }).click();
  await expect((await createResponse).status()).toBe(201);
  return { sku, name };
}
