"use client";
import { FormEvent, useEffect, useState } from "react";
import { api, Page, Product, User } from "../lib/api";

export default function ProductActions({ user }: { user: User }) {
  const [items, setItems] = useState<Product[]>([]); const [selected, setSelected] = useState(""); const [name, setName] = useState(""); const [minimum, setMinimum] = useState(""); const [error, setError] = useState("");
  async function load() { try { setItems((await api<Page<Product>>("/products")).items); window.dispatchEvent(new Event("orvexa:products-refresh")); } catch (e) { setError((e as Error).message); } }
  useEffect(() => { void load(); }, []); const item = items.find((entry) => entry.id === selected);
  function choose(value: string) { const picked = items.find((entry) => entry.id === value); setSelected(value); setName(picked?.name ?? ""); setMinimum(picked?.minimum_stock ?? ""); }
  async function save(event: FormEvent) { event.preventDefault(); try { await api(`/products/${selected}`, { method: "PATCH", body: JSON.stringify({ name, minimum_stock: Number(minimum) }) }); await load(); } catch (e) { setError((e as Error).message); } }
  async function toggle() { if (!item) return; try { await api(`/products/${item.id}/${item.is_active ? "deactivate" : "activate"}`, { method: "POST" }); await load(); } catch (e) { setError((e as Error).message); } }
  if (!user.permissions.includes("product.update") && !user.permissions.includes("product.deactivate")) return null;
  return <section className="panel compact"><h2>Editar producto</h2><div className="field"><label htmlFor="product-edit-select">Producto</label><select id="product-edit-select" value={selected} onChange={(e) => choose(e.target.value)}><option value="">Selecciona</option>{items.map((entry) => <option key={entry.id} value={entry.id}>{entry.sku} · {entry.name}</option>)}</select></div>{item && <form className="form-grid" onSubmit={save}>{user.permissions.includes("product.update") && <><div className="field"><label htmlFor="product-edit-name">Nombre</label><input id="product-edit-name" value={name} onChange={(e) => setName(e.target.value)} required /></div><div className="field"><label htmlFor="product-edit-minimum">Stock mínimo</label><input id="product-edit-minimum" type="number" min="0" step="0.01" value={minimum} onChange={(e) => setMinimum(e.target.value)} required /></div><button className="button primary">Guardar cambios</button></>}{user.permissions.includes("product.deactivate") && <button type="button" className="button secondary" onClick={toggle}>{item.is_active ? "Desactivar" : "Activar"}</button>}</form>}{error && <p className="form-error" role="alert">{error}</p>}</section>;
}
