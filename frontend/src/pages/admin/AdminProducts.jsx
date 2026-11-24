import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Field from "../../components/layout/Field.jsx";
import { adminApi, shopApi } from "../../services/api.js";
import { money } from "../../utils/money.js";

const blank = () => ({
  name: "", brand: "", category_id: "", description: "", price: "", sale: "", status: "active", material: "", care: "",
  tags: "", return_eligible: true, images: "", variants: [{ sku: "", size: "", color: "", stock_quantity: 0 }],
});

const fromApi = (p) => ({
  id: p.id, name: p.name, brand: p.brand || "", category_id: p.category_id, description: p.description || "",
  price: p.price_minor / 100, sale: p.sale_price_minor ? p.sale_price_minor / 100 : "", status: p.status,
  material: p.material || "", care: p.care || "", tags: (p.tags || []).join(", "), return_eligible: p.return_eligible,
  images: p.images.map((i) => i.image_url).join("\n"),
  variants: p.variants.map((v) => ({ id: v.id, sku: v.sku, size: v.size || "", color: v.color || "", stock_quantity: v.stock_quantity })),
});

const toApi = (f) => ({
  category_id: Number(f.category_id), name: f.name, brand: f.brand || null, description: f.description || null,
  price_minor: Math.round(Number(f.price) * 100), sale_price_minor: f.sale === "" ? null : Math.round(Number(f.sale) * 100),
  status: f.status, material: f.material || null, care: f.care || null, return_eligible: f.return_eligible,
  tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean),
  images: f.images.split("\n").map((u) => u.trim()).filter(Boolean).map((image_url) => ({ image_url })),
  variants: f.variants.map((v) => ({ id: v.id ?? null, sku: v.sku, size: v.size || null, color: v.color || null, stock_quantity: Number(v.stock_quantity) })),
});

// Turns nested marshmallow errors into "field: message" lines.
const flatten = (d, path = "") =>
  Array.isArray(d) ? d.map((m) => (path ? `${path}: ${m}` : m)).join(" ")
    : Object.entries(d).map(([k, v]) => flatten(v, path ? `${path} ${k}` : k)).join(" ");

function Editor({ initial, cats, onClose }) {
  const qc = useQueryClient();
  const [f, setF] = useState(initial);
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const setVar = (i, k, v) => setF({ ...f, variants: f.variants.map((x, j) => (j === i ? { ...x, [k]: v } : x)) });

  const save = useMutation({
    mutationFn: () => (f.id ? adminApi.updateProduct(f.id, toApi(f)) : adminApi.createProduct(toApi(f))),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-products"] }); qc.invalidateQueries({ queryKey: ["products"] }); onClose(); },
    onError: (e) => setErr(e.details ? flatten(e.details) : e.message),
  });

  return (
    <form onSubmit={(e) => { e.preventDefault(); setErr(""); save.mutate(); }} className="space-y-4 rounded-2xl border border-black/15 p-6">
      <h2 className="font-serif text-2xl">{f.id ? "Edit product" : "New product"}</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" id="p-name" value={f.name} onChange={set("name")} required />
        <Field label="Brand" id="p-brand" value={f.brand} onChange={set("brand")} />
        <div>
          <label htmlFor="p-cat" className="mb-1 block text-sm font-medium">Category</label>
          <select id="p-cat" required value={f.category_id} onChange={set("category_id")} className="w-full rounded-lg border border-black/20 px-3 py-2">
            <option value="">Select…</option>{cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="p-status" className="mb-1 block text-sm font-medium">Status</label>
          <select id="p-status" value={f.status} onChange={set("status")} className="w-full rounded-lg border border-black/20 px-3 py-2">
            <option>active</option><option>draft</option><option>archived</option>
          </select>
        </div>
        <Field label="Price (₹)" id="p-price" type="number" min="1" step="0.01" value={f.price} onChange={set("price")} required />
        <Field label="Sale price (₹, optional)" id="p-sale" type="number" min="1" step="0.01" value={f.sale} onChange={set("sale")} />
        <Field label="Material" id="p-mat" value={f.material} onChange={set("material")} />
        <Field label="Care" id="p-care" value={f.care} onChange={set("care")} />
      </div>
      <div>
        <label htmlFor="p-desc" className="mb-1 block text-sm font-medium">Description</label>
        <textarea id="p-desc" rows="3" value={f.description} onChange={set("description")} className="w-full rounded-lg border border-black/20 px-3 py-2" />
      </div>
      <Field label="Tags (comma separated)" id="p-tags" value={f.tags} onChange={set("tags")} />
      <div>
        <label htmlFor="p-img" className="mb-1 block text-sm font-medium">Image URLs (one per line, https)</label>
        <textarea id="p-img" rows="2" value={f.images} onChange={set("images")} className="w-full rounded-lg border border-black/20 px-3 py-2 font-mono text-xs" />
      </div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.return_eligible} onChange={set("return_eligible")} /> Return eligible</label>

      <fieldset>
        <legend className="mb-2 text-sm font-medium">Variants & stock</legend>
        {f.variants.map((v, i) => (
          <div key={i} className="mb-2 grid grid-cols-[1.5fr_1fr_1fr_80px_auto] gap-2">
            {[["sku", "SKU"], ["size", "Size"], ["color", "Colour"], ["stock_quantity", "Stock"]].map(([k, l]) => (
              <input key={k} aria-label={`${l} ${i + 1}`} placeholder={l} type={k === "stock_quantity" ? "number" : "text"} min="0" required={k === "sku" || k === "stock_quantity"}
                value={v[k]} onChange={(e) => setVar(i, k, e.target.value)} className="rounded-lg border border-black/20 px-2 py-1.5 text-sm" />
            ))}
            <button type="button" aria-label={`Remove variant ${i + 1}`} disabled={f.variants.length === 1}
              onClick={() => setF({ ...f, variants: f.variants.filter((_, j) => j !== i) })} className="px-2 text-red-700 disabled:opacity-30">✕</button>
          </div>
        ))}
        <button type="button" onClick={() => setF({ ...f, variants: [...f.variants, { sku: "", size: "", color: "", stock_quantity: 0 }] })} className="text-sm underline">+ Add variant</button>
      </fieldset>

      {err && <p role="alert" className="break-words text-sm text-red-700">{err}</p>}
      <div className="flex gap-3">
        <button disabled={save.isPending} className="rounded-full bg-ink px-6 py-2 text-white hover:bg-accent disabled:opacity-60">{save.isPending ? "Saving…" : "Save product"}</button>
        <button type="button" onClick={onClose} className="rounded-full border border-ink px-6 py-2">Cancel</button>
      </div>
    </form>
  );
}

export default function AdminProducts() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-products"], queryFn: adminApi.products });
  const { data: cats } = useQuery({ queryKey: ["categories"], queryFn: shopApi.categories });
  const [editing, setEditing] = useState(null);

  const edit = async (id) => setEditing(fromApi((await adminApi.product(id)).product));
  const archive = useMutation({ mutationFn: adminApi.archiveProduct, onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-products"] }) });

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-serif text-3xl">Products</h1>
        {!editing && <button onClick={() => setEditing(blank())} className="rounded-full bg-ink px-5 py-2 text-white hover:bg-accent">New product</button>}
      </div>
      {editing && <div className="mb-8"><Editor key={editing.id || "new"} initial={editing} cats={cats?.categories || []} onClose={() => setEditing(null)} /></div>}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead><tr className="border-b border-black/20"><th className="py-2">Name</th><th>Category</th><th>Price</th><th>Stock</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>
            {data?.products.map((p) => (
              <tr key={p.id} className="border-b border-black/10">
                <td className="py-2">{p.name}</td><td>{p.category}</td><td>{money(p.effective_price_minor)}</td>
                <td className={p.stock_total === 0 ? "text-red-700" : ""}>{p.stock_total}</td><td>{p.status}</td>
                <td className="space-x-3 text-right">
                  <button className="underline" onClick={() => edit(p.id)}>Edit</button>
                  {p.status !== "archived" && <button className="underline" onClick={() => window.confirm(`Archive ${p.name}?`) && archive.mutate(p.id)}>Archive</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
