import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Field from "../../components/layout/Field.jsx";
import { adminApi } from "../../services/api.js";

const Note = ({ n }) => (n ? <p role={n.ok ? "status" : "alert"} className={`text-sm ${n.ok ? "text-green-800" : "text-red-700"}`}>{n.text}</p> : null);

function Categories() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-categories"], queryFn: adminApi.categories });
  const [name, setName] = useState("");
  const [parent, setParent] = useState("");
  const [note, setNote] = useState(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["admin-categories"] }); qc.invalidateQueries({ queryKey: ["categories"] }); };
  const cats = data?.categories || [];
  const body = (c, over = {}) => ({ name: c.name, parent_id: c.parent_id, description: c.description, is_active: c.is_active, ...over });

  async function add(e) {
    e.preventDefault(); setNote(null);
    try { await adminApi.saveCategory(null, { name, parent_id: parent ? Number(parent) : null, description: null, is_active: true }); setName(""); setParent(""); refresh(); setNote({ ok: true, text: "Category added." }); }
    catch (x) { setNote({ ok: false, text: x.details ? Object.values(x.details).flat().join(" ") : x.message }); }
  }
  async function rename(c, value) {
    if (!value.trim() || value === c.name) return;
    try { await adminApi.saveCategory(c.id, body(c, { name: value.trim() })); refresh(); } catch (x) { setNote({ ok: false, text: x.message }); }
  }

  return (
    <section aria-labelledby="cat-h" className="rounded-2xl border border-black/10 p-6">
      <h2 id="cat-h" className="font-serif text-xl">Categories</h2>
      <table className="mt-3 w-full text-left text-sm">
        <thead><tr className="border-b border-black/20"><th className="py-2">Name</th><th>Parent</th><th>Active</th></tr></thead>
        <tbody>
          {cats.map((c) => (
            <tr key={c.id} className="border-b border-black/10">
              <td className="py-1.5"><input aria-label={`Name of category ${c.name}`} defaultValue={c.name} onBlur={(e) => rename(c, e.target.value)} className="rounded border border-transparent px-2 py-1 hover:border-black/20" /></td>
              <td>{cats.find((p) => p.id === c.parent_id)?.name || "—"}</td>
              <td><label><input type="checkbox" checked={c.is_active} aria-label={`${c.name} active`} onChange={async () => { await adminApi.saveCategory(c.id, body(c, { is_active: !c.is_active })); refresh(); }} /> {c.is_active ? "Yes" : "No"}</label></td>
            </tr>
          ))}
        </tbody>
      </table>
      <form onSubmit={add} className="mt-4 flex flex-wrap items-end gap-3">
        <Field label="New category" id="cat-name" required value={name} onChange={(e) => setName(e.target.value)} />
        <div><label htmlFor="cat-parent" className="mb-1 block text-sm font-medium">Parent (optional)</label>
          <select id="cat-parent" value={parent} onChange={(e) => setParent(e.target.value)} className="rounded-lg border border-black/20 px-3 py-2"><option value="">None</option>{cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
        <button className="rounded-full bg-ink px-5 py-2 text-white hover:bg-accent">Add</button>
      </form>
      <Note n={note} />
    </section>
  );
}

function Inventory() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [low, setLow] = useState(false);
  const [page, setPage] = useState(1);
  const [note, setNote] = useState(null);
  const params = { q, low: low ? "true" : "", page, per_page: 15 };
  const { data } = useQuery({ queryKey: ["admin-inventory", params], queryFn: () => adminApi.inventory(params), placeholderData: (p) => p });
  const pages = data ? Math.max(1, Math.ceil(data.total / data.per_page)) : 1;

  async function save(item, value) {
    const n = Number(value);
    if (value === "" || !Number.isInteger(n) || n < 0) return setNote({ ok: false, text: "Stock must be a whole number, 0 or more." });
    if (n === item.stock_quantity) return;
    try { await adminApi.setStock(item.variant_id, n); setNote({ ok: true, text: `${item.sku} set to ${n}.` }); qc.invalidateQueries({ queryKey: ["admin-inventory"] }); qc.invalidateQueries({ queryKey: ["admin-dashboard"] }); }
    catch (x) { setNote({ ok: false, text: x.message }); }
  }

  return (
    <section aria-labelledby="inv-h" className="rounded-2xl border border-black/10 p-6">
      <h2 id="inv-h" className="font-serif text-xl">Inventory</h2>
      <div className="mt-3 flex flex-wrap items-end gap-4">
        <Field label="Search product or SKU" id="inv-q" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <label className="pb-2 text-sm"><input type="checkbox" checked={low} onChange={(e) => { setLow(e.target.checked); setPage(1); }} /> Low stock only (≤ {data?.low_stock_threshold ?? 5})</label>
      </div>
      <Note n={note} />
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <caption className="sr-only">Stock by variant, lowest first</caption>
          <thead><tr className="border-b border-black/20"><th className="py-2 pr-3">Product</th><th className="pr-3">SKU</th><th className="pr-3">Variant</th><th>Stock</th></tr></thead>
          <tbody>
            {data?.items.map((i) => (
              <tr key={i.variant_id} className="border-b border-black/10">
                <td className="py-1.5 pr-3">{i.product}{i.status !== "active" && <span className="ml-2 text-xs text-black/60">({i.status})</span>}</td>
                <td className="pr-3 font-mono text-xs">{i.sku}</td><td className="pr-3">{[i.color, i.size].filter(Boolean).join(" · ") || "—"}</td>
                <td>
                  <input type="number" min="0" aria-label={`Stock for ${i.sku}`} defaultValue={i.stock_quantity} key={`${i.variant_id}-${i.stock_quantity}`}
                    onBlur={(e) => save(i, e.target.value)} onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
                    className={`w-24 rounded-lg border px-2 py-1 ${i.stock_quantity === 0 ? "border-red-400" : i.stock_quantity <= (data.low_stock_threshold ?? 5) ? "border-amber-400" : "border-black/20"}`} />
                  {i.stock_quantity === 0 && <span className="ml-2 text-xs text-red-700">Out of stock</span>}
                  {i.stock_quantity > 0 && i.stock_quantity <= data.low_stock_threshold && <span className="ml-2 text-xs text-amber-800">Low</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data?.items.length === 0 && <p className="mt-3 text-sm text-black/60">No variants match.</p>}
      </div>
      {pages > 1 && (
        <nav aria-label="Pagination" className="mt-3 flex items-center justify-center gap-4 text-sm">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="underline disabled:opacity-40">Previous</button>
          <span>Page {page} of {pages}</span>
          <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="underline disabled:opacity-40">Next</button>
        </nav>
      )}
      <p className="mt-3 text-xs text-black/60">Editing a stock level replaces the current value (saved when you leave the field) and is recorded in the audit log.</p>
    </section>
  );
}

export default function AdminCatalogue() {
  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-8">
      <h1 className="font-serif text-3xl">Catalogue &amp; stock</h1>
      <Categories />
      <Inventory />
    </div>
  );
}
