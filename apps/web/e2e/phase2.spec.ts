import { test, expect, type Page, type TestInfo } from "@playwright/test";
import { credentials, login, navigate, uniqueName } from "./fixtures";

test.describe.configure({ mode: "serial" });

test.describe("Fase 2: recorrido empresarial completo", () => {
  let employeeUsername = "";
  let employeeEmail = "";
  let temporaryPassword = "";
  let employeePassword = "";
  let categoryName = "";
  let productSku = "";
  let productName = "";
  let updatedProductName = "";
  let entryDescription = "";
  let exitDescription = "";

  async function createCategory(page: Page, testInfo: TestInfo) {
    categoryName = uniqueName("Categoría", testInfo);
    await navigate(page, "Categorías");
    await expect(page.getByRole("heading", { name: "Categorías" })).toBeVisible();
    await page.getByLabel("Código").fill(uniqueName("cat", testInfo).slice(0, 24));
    await page.getByLabel("Nombre").fill(categoryName);
    const createResponse = page.waitForResponse((response) => response.url().includes("/api/v1/categories") && response.request().method() === "POST");
    await page.getByRole("button", { name: "Crear" }).click();
    await expect((await createResponse).status()).toBe(201);
  }

  async function createEmployee(page: Page, testInfo: TestInfo) {
    await navigate(page, "Usuarios");
    await expect(page.getByRole("heading", { name: "Usuarios" })).toBeVisible();
    employeeUsername = uniqueName("employee", testInfo).slice(0, 32);
    employeeEmail = `${employeeUsername}@example.test`;
    await page.locator("#new_username").fill(employeeUsername);
    await page.locator("#new_email").fill(employeeEmail);
    await page.locator("#role").selectOption("employee");
    await page.getByRole("button", { name: "Crear usuario" }).click();
    const secretPanel = page.getByRole("alert").filter({ hasText: "Contraseña temporal" });
    await expect(secretPanel).toBeVisible();
    temporaryPassword = (await secretPanel.locator("code").innerText()).trim();
    expect(temporaryPassword, "Debe existir una contraseña temporal runtime").toMatch(/^\S{12,}$/);
  }

  test("la portada muestra el formulario de login", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Iniciar sesión" })).toBeVisible();
    await expect(page.getByLabel("Usuario o correo")).toBeVisible();
    await expect(page.getByLabel("Contraseña", { exact: true })).toBeVisible();
    await page.getByLabel("Usuario o correo").fill(credentials().username);
    await page.getByLabel("Contraseña", { exact: true }).fill(credentials().password);
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page).toHaveURL(/\/dashboard$/);
  });

  test("cookie válida no salta formulario y visita protegida exige marcador", async ({ page }) => {
    await login(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Iniciar sesión" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Resumen" })).not.toBeVisible();
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Iniciar sesión" })).toBeVisible();
    await login(page);
    await page.evaluate(() => sessionStorage.removeItem("orvexa:authenticated-visit"));
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login\?next=%2Fdashboard$/);
    await expect(page.getByRole("heading", { name: "Resumen" })).not.toBeVisible();
  });

  test("sesión caduca tras cinco minutos sin actividad real", async ({ page }) => {
    await page.clock.install();
    await login(page);
    await page.clock.fastForward(5 * 60 * 1000);
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("heading", { name: "Resumen" })).not.toBeVisible();
    expect((await page.request.get("/api/v1/auth/me")).status()).toBe(401);
    expect((await page.context().cookies()).filter((cookie) => ["orvexadb_session", "orvexadb_csrf"].includes(cookie.name))).toHaveLength(0);
  });

  test("1. administrador inicia sesión y crea empleado con contraseña temporal", async ({ page }, testInfo) => {
    await login(page);
    await expect.poll(() => page.evaluate(() => sessionStorage.getItem("orvexa:authenticated-visit"))).toBe("1");
    const cookies = await page.context().cookies();
    const sessionCookie = cookies.find((cookie) => cookie.name === "orvexadb_session");
    const csrfCookie = cookies.find((cookie) => cookie.name === "orvexadb_csrf");
    expect(sessionCookie).toMatchObject({ httpOnly: true, sameSite: "Lax", path: "/", secure: false });
    expect(csrfCookie).toMatchObject({ httpOnly: false, sameSite: "Lax", path: "/" });
    const storageKeys = await page.evaluate(() => ({
      local: Object.keys(window.localStorage).filter((key) => /token|session|csrf/i.test(key)),
      session: Object.keys(window.sessionStorage).filter((key) => /token|session|csrf/i.test(key)),
    }));
    expect(storageKeys).toEqual({ local: [], session: [] });
    await createCategory(page, testInfo);
    await expect.poll(() => page.evaluate(() => sessionStorage.getItem("orvexa:authenticated-visit"))).toBe("1");
    await createEmployee(page, testInfo);
  });

  test("2. empleado cambia la contraseña temporal", async ({ browser }, testInfo) => {
    const page = await browser.newPage();
    employeePassword = `${uniqueName("Pass", testInfo)}!A9z#2026`;
    await login(page, employeeUsername, temporaryPassword, { expectPasswordChange: true });
    await page.getByLabel("Contraseña actual").fill(temporaryPassword);
    await page.getByLabel(/Nueva contraseña/).fill(employeePassword);
    await page.getByLabel("Repite la nueva contraseña").fill(employeePassword);
    await page.getByRole("button", { name: "Guardar contraseña" }).click();
    await expect(page).toHaveURL(/\/login\?changed=1$/);
    await page.close();
  });

  test("3. empleado crea un producto", async ({ browser }, testInfo) => {
    const page = await browser.newPage();
    await login(page, employeeUsername, employeePassword);
    await navigate(page, "Productos");
    await expect(page.getByRole("heading", { name: "Productos" })).toBeVisible();
    productSku = uniqueName("sku", testInfo).slice(0, 24).toUpperCase();
    productName = uniqueName("Producto", testInfo);
    await page.getByLabel("SKU").fill(productSku);
    await page.getByLabel("Nombre", { exact: true }).fill(productName);
    await page.getByLabel("Categoría").selectOption({ label: categoryName });
    await page.getByLabel("Coste unitario").fill("12.50");
    await page.getByLabel("Stock mínimo").fill("2");
    const createResponse = page.waitForResponse((response) => response.url().includes("/api/v1/products") && response.request().method() === "POST");
    await page.getByRole("button", { name: "Crear producto" }).click();
    await expect((await createResponse).status()).toBe(201);
    await page.close();
  });

  test("4. empleado actualiza el producto", async ({ browser }) => {
    const page = await browser.newPage();
    await login(page, employeeUsername, employeePassword);
    await navigate(page, "Productos");
    await page.getByLabel("Producto").selectOption({ label: `${productSku} · ${productName}` });
    updatedProductName = `${productName}-actualizado`;
    await page.getByLabel("Nombre", { exact: true }).last().fill(updatedProductName);
    await page.locator("#product-edit-minimum").fill("3");
    await page.getByRole("button", { name: "Guardar cambios" }).click();
    await expect(page.getByRole("cell", { name: updatedProductName })).toBeVisible();
    await page.close();
  });

  test("5. empleado registra una entrada y una salida", async ({ browser }, testInfo) => {
    const page = await browser.newPage();
    await login(page, employeeUsername, employeePassword);
    await navigate(page, "Movimientos");
    entryDescription = uniqueName("Entrada", testInfo);
    exitDescription = uniqueName("Salida", testInfo);
    await page.getByLabel("Producto").selectOption({ label: `${productSku} · ${updatedProductName}` });
    await page.getByLabel("Dirección").selectOption("in");
    await page.getByLabel("Cantidad").fill("10");
    await page.getByLabel("Motivo").selectOption("purchase");
    await page.getByLabel("Descripción").fill(entryDescription);
    await page.getByRole("button", { name: "Registrar" }).click();
    await expect(page.getByRole("row").filter({ hasText: entryDescription })).toBeVisible();
    await page.getByLabel("Dirección").selectOption("out");
    await page.getByLabel("Cantidad").fill("3");
    await page.getByLabel("Motivo").selectOption("sale");
    await page.getByLabel("Descripción").fill(exitDescription);
    await page.getByRole("button", { name: "Registrar" }).click();
    await expect(page.getByRole("row").filter({ hasText: exitDescription })).toBeVisible();
    await navigate(page, "Productos");
    const productRow = page.getByRole("row").filter({ hasText: productSku });
    await expect(productRow).toBeVisible();
    await expect(productRow).toContainText("7");
    await page.close();
  });

  test("6. empleado recibe denegación al abrir gestión de usuarios", async ({ browser }) => {
    const page = await browser.newPage();
    await login(page, employeeUsername, employeePassword);
    await page.goto("/admin/users");
    await expect(page.getByRole("heading", { name: "Acceso denegado" })).toBeVisible();
    await page.close();
  });

  test("7. administrador desactiva y reactiva el empleado", async ({ page }) => {
    await login(page);
    await navigate(page, "Usuarios");
    await page.locator("#user-edit-select").selectOption({ label: `${employeeUsername} · ${employeeEmail}` });
    await page.getByRole("button", { name: "Desactivar" }).click();
    await expect(page.getByRole("button", { name: "Activar" })).toBeVisible();
    await page.getByRole("button", { name: "Activar" }).click();
    await expect(page.getByRole("button", { name: "Desactivar" })).toBeVisible();
    await page.getByRole("button", { name: "Cerrar sesión" }).click();
    await expect.poll(() => new URL(page.url()).pathname).toBe("/login");
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: "Iniciar sesión" })).toBeVisible();
    const meResponse = await page.request.get("/api/v1/auth/me");
    expect(meResponse.status()).toBe(401);
    expect((await page.context().cookies()).filter((cookie) => ["orvexadb_session", "orvexadb_csrf"].includes(cookie.name))).toHaveLength(0);
  });
});
