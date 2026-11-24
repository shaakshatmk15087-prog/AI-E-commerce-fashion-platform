import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Field from "../../components/layout/Field.jsx";
import { adminApi } from "../../services/api.js";
import { money } from "../../utils/money.js";

const flat = (d, path = "") =>
  Array.isArray(d) ? d.map((m) => (path ? `${path}: ${m}` : m)).join(" ")
    : Object.entries(d || {}).map(([k, v]) => flat(v, path ? `${path} ${k}` : k)).join(" ");

function Note({ n }) {
  return n ? <p role={n.ok ? "status" : "alert"} className={`text-sm ${n.ok ? "text-green-800" : "text-red-700"}`}>{n.text}</p> : null;
}
const fail = (e) => ({ ok: false, text: e.details ? flat(e.details) : e.message });

function SettingsForm() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-credit-settings"], queryFn: adminApi.creditSettings });
  const [f, setF] = useState(null);
  const [note, setNote] = useState(null);
  useEffect(() => {
    if (!data) return;
    const s = data.settings, c = s.services.ai_chat;
    setF({ daily_allowance: s.daily_allowance, reset_timezone: s.reset_timezone, reset_hour: s.reset_hour, spend_priority: s.spend_priority,
      cost: c.cost, daily: c.credit_types.includes("daily"), sup: c.credit_types.includes("super") });
  }, [data]);
  if (!f) return <p>Loading…</p>;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  async function save(e) {
    e.preventDefault(); setNote(null);
    try {
      await adminApi.saveCreditSettings({
        daily_allowance: Number(f.daily_allowance), reset_timezone: f.reset_timezone, reset_hour: Number(f.reset_hour),
        spend_priority: f.spend_priority,
        services: { ai_chat: { cost: Number(f.cost), credit_types: [f.daily && "daily", f.sup && "super"].filter(Boolean) } },
      });
      qc.invalidateQueries({ queryKey: ["admin-credit-settings"] }); qc.invalidateQueries({ queryKey: ["admin-audit"] });
      setNote({ ok: true, text: "Saved. Applies to new grants and spends." });
    } catch (x) { setNote(fail(x)); }
  }

  return (
    <form onSubmit={save} className="space-y-4 rounded-2xl border border-black/10 p-6">
      <h2 className="font-serif text-xl">Credit rules</h2>
      <p className="text-sm text-black/60">Placeholder defaults for open business decisions. Changes are audited.</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Daily Credits per day" id="allow" type="number" min="0" value={f.daily_allowance} onChange={set("daily_allowance")} />
        <Field label="Reset timezone (IANA)" id="tz" value={f.reset_timezone} onChange={set("reset_timezone")} />
        <Field label="Reset hour (0–23, local)" id="rh" type="number" min="0" max="23" value={f.reset_hour} onChange={set("reset_hour")} />
        <div>
          <label htmlFor="prio" className="mb-1 block text-sm font-medium">Spend priority</label>
          <select id="prio" value={f.spend_priority} onChange={set("spend_priority")} className="w-full rounded-lg border border-black/20 px-3 py-2">
            <option value="daily_first">Daily Credits first</option><option value="super_first">Super Credits first</option>
          </select>
        </div>
        <Field label="AI chat cost (credits, 0 = free)" id="cost" type="number" min="0" value={f.cost} onChange={set("cost")} />
        <fieldset><legend className="mb-1 text-sm font-medium">AI chat can spend</legend>
          <label className="mr-4 text-sm"><input type="checkbox" checked={f.daily} onChange={set("daily")} /> Daily</label>
          <label className="text-sm"><input type="checkbox" checked={f.sup} onChange={set("sup")} /> Super</label>
        </fieldset>
      </div>
      <Note n={note} />
      <button className="rounded-full bg-ink px-6 py-2 text-white hover:bg-accent">Save rules</button>
    </form>
  );
}

function Catalogue({ title, queryKey, fetcher, saver, blank, columns, fields }) {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: [queryKey], queryFn: fetcher });
  const items = data ? Object.values(data)[0] : [];
  const [draft, setDraft] = useState(blank);
  const [note, setNote] = useState(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: [queryKey] }); qc.invalidateQueries({ queryKey: ["admin-audit"] }); };

  async function add(e) {
    e.preventDefault(); setNote(null);
    try { await saver(null, fields.toApi(draft)); setDraft(blank); refresh(); setNote({ ok: true, text: "Added." }); } catch (x) { setNote(fail(x)); }
  }
  async function toggle(item) {
    try { await saver(item.id, { ...fields.itemToBody(item), is_active: !item.is_active }); refresh(); } catch (x) { setNote(fail(x)); }
  }

  return (
    <section className="rounded-2xl border border-black/10 p-6">
      <h2 className="font-serif text-xl">{title}</h2>
      <table className="mt-3 w-full text-left text-sm">
        <thead><tr className="border-b border-black/20">{columns.map((c) => <th key={c.h} className="py-2">{c.h}</th>)}<th>Active</th></tr></thead>
        <tbody>{items.map((it) => (
          <tr key={it.id} className="border-b border-black/10">
            {columns.map((c) => <td key={c.h} className="py-2">{c.v(it)}</td>)}
            <td><label className="text-xs"><input type="checkbox" checked={it.is_active} onChange={() => toggle(it)} aria-label={`${it.name} active`} /> {it.is_active ? "Yes" : "No"}</label></td>
          </tr>))}</tbody>
      </table>
      <form onSubmit={add} className="mt-4 grid gap-3 sm:grid-cols-4">
        {fields.inputs.map(([k, label, type, extra]) => (
          extra?.options ? (
            <div key={k}><label htmlFor={`${queryKey}-${k}`} className="mb-1 block text-sm font-medium">{label}</label>
              <select id={`${queryKey}-${k}`} value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} className="w-full rounded-lg border border-black/20 px-3 py-2">
                {extra.options.map((o) => <option key={o}>{o}</option>)}</select></div>
          ) : <Field key={k} label={label} id={`${queryKey}-${k}`} type={type || "text"} min={type === "number" ? "1" : undefined} required value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
        ))}
        <div className="flex items-end"><button className="rounded-full bg-ink px-5 py-2 text-white hover:bg-accent">Add</button></div>
      </form>
      <Note n={note} />
    </section>
  );
}

function Adjust() {
  const qc = useQueryClient();
  const { data: users } = useQuery({ queryKey: ["admin-users"], queryFn: () => adminApi.users({ per_page: 200 }) });
  const [f, setF] = useState({ user: "", credit_type: "super", amount: "", reason: "" });
  const [view, setView] = useState(null);
  const [note, setNote] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function load(id) { setView(id ? await adminApi.userWallet(id) : null); }
  async function submit(e) {
    e.preventDefault(); setNote(null);
    try {
      await adminApi.adjust(f.user, { credit_type: f.credit_type, amount: Number(f.amount), reason: f.reason });
      setNote({ ok: true, text: "Adjustment recorded." }); setF({ ...f, amount: "", reason: "" });
      await load(f.user); qc.invalidateQueries({ queryKey: ["admin-audit"] });
    } catch (x) { setNote(fail(x)); }
  }

  return (
    <section className="rounded-2xl border border-black/10 p-6">
      <h2 className="font-serif text-xl">Adjust a customer's credits</h2>
      <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-4">
        <div><label htmlFor="adj-user" className="mb-1 block text-sm font-medium">Customer</label>
          <select id="adj-user" required value={f.user} onChange={(e) => { set("user")(e); load(e.target.value); }} className="w-full rounded-lg border border-black/20 px-3 py-2">
            <option value="">Select…</option>{users?.users.filter((u) => u.role === "customer").map((u) => <option key={u.id} value={u.id}>{u.email}</option>)}</select></div>
        <div><label htmlFor="adj-type" className="mb-1 block text-sm font-medium">Credits</label>
          <select id="adj-type" value={f.credit_type} onChange={set("credit_type")} className="w-full rounded-lg border border-black/20 px-3 py-2"><option value="super">Super</option><option value="daily">Daily</option></select></div>
        <Field label="Amount (+/−)" id="adj-amt" type="number" required value={f.amount} onChange={set("amount")} />
        <Field label="Reason (required)" id="adj-reason" required minLength={3} value={f.reason} onChange={set("reason")} />
        <div className="sm:col-span-4"><button className="rounded-full bg-ink px-5 py-2 text-white hover:bg-accent">Apply adjustment</button></div>
      </form>
      <Note n={note} />
      {view && (
        <div className="mt-4 text-sm">
          <p>Balances: Daily <strong>{view.wallet.daily.balance}</strong> · Super <strong>{view.wallet.super.balance}</strong>
            {Object.keys(view.ledger_mismatch).length > 0 && <span className="ml-2 text-red-700">Ledger mismatch detected!</span>}</p>
        </div>
      )}
    </section>
  );
}

function Audit() {
  const { data } = useQuery({ queryKey: ["admin-audit"], queryFn: adminApi.audit });
  return (
    <section className="rounded-2xl border border-black/10 p-6">
      <h2 className="font-serif text-xl">Audit log</h2>
      <div className="mt-3 max-h-80 overflow-auto">
        <table className="w-full text-left text-xs">
          <thead><tr className="border-b border-black/20"><th className="py-1">When</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
          <tbody>{data?.logs.map((l) => (
            <tr key={l.id} className="border-b border-black/10 align-top">
              <td className="py-1 pr-2 whitespace-nowrap">{new Date(l.created_at).toLocaleString()}</td><td className="pr-2">{l.action}</td>
              <td className="pr-2">{l.target_type} {l.target_id}</td><td className="break-all text-black/60">{JSON.stringify(l.details)}</td></tr>))}</tbody>
        </table>
        {data?.logs.length === 0 && <p className="text-sm text-black/60">Nothing yet.</p>}
      </div>
    </section>
  );
}

export default function AdminCredits() {
  const packFields = {
    inputs: [["name", "Name"], ["credits", "Credits", "number"], ["price", "Price (₹)", "number"]],
    toApi: (d) => ({ name: d.name, credits: Number(d.credits), price_minor: Math.round(Number(d.price) * 100), is_active: true }),
    itemToBody: (i) => ({ name: i.name, credits: i.credits, price_minor: i.price_minor }),
  };
  const planFields = {
    inputs: [["name", "Name"], ["price", "Price (₹)", "number"], ["credits", "Super Credits", "number"],
      ["frequency", "Grant", "select", { options: ["renewal", "daily"] }], ["interval", "Interval", "select", { options: ["month", "year"] }]],
    toApi: (d) => ({ name: d.name, price_minor: Math.round(Number(d.price) * 100), super_credit_amount: Number(d.credits),
      grant_frequency: d.frequency, billing_interval: d.interval, is_active: true }),
    itemToBody: (i) => ({ name: i.name, description: i.description, price_minor: i.price_minor, billing_interval: i.billing_interval,
      super_credit_amount: i.super_credit_amount, grant_frequency: i.grant_frequency, benefits: i.benefits }),
  };
  return (
    <div className="mx-auto max-w-5xl space-y-8 px-4 py-10">
      <div><h1 className="font-serif text-3xl">Credits &amp; plans</h1></div>
      <SettingsForm />
      <Catalogue title="Super Credit packs" queryKey="admin-packs" fetcher={adminApi.packs} saver={adminApi.savePack}
        blank={{ name: "", credits: "", price: "" }} fields={packFields}
        columns={[{ h: "Name", v: (i) => i.name }, { h: "Credits", v: (i) => i.credits }, { h: "Price", v: (i) => money(i.price_minor) }]} />
      <Catalogue title="Subscription plans" queryKey="admin-plans" fetcher={adminApi.plans} saver={adminApi.savePlan}
        blank={{ name: "", price: "", credits: "", frequency: "renewal", interval: "month" }} fields={planFields}
        columns={[{ h: "Name", v: (i) => i.name }, { h: "Price", v: (i) => `${money(i.price_minor)}/${i.billing_interval}` },
          { h: "Credits", v: (i) => `${i.super_credit_amount} (${i.grant_frequency})` }]} />
      <Adjust />
      <Audit />
    </div>
  );
}
