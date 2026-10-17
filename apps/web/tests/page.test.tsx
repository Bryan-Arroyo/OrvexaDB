import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Home from "../src/app/page";

beforeEach(() => { vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true })); });
afterEach(() => { document.body.innerHTML = ""; vi.restoreAllMocks(); });
it("renders only the login form on the portada", () => { render(<Home />); expect(screen.getByRole("heading", { name: "Iniciar sesión" })).toBeInTheDocument(); expect(screen.getByLabelText("Usuario o correo")).toBeInTheDocument(); expect(screen.getByLabelText("Contraseña")).toBeInTheDocument(); expect(screen.queryByRole("status")).not.toBeInTheDocument(); expect(screen.queryByText(/API/i)).not.toBeInTheDocument(); expect(screen.queryByText("OrvexaDB")).not.toBeInTheDocument(); });
