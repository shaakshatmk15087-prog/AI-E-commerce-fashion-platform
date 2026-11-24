import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Field from "../../components/layout/Field.jsx";
import { adminApi } from "../../services/api.js";

const flat = (d) => Object.entries(d || {}).map(([k, v]) => `${k}: ${[].concat(v).join(" ")}`).join(" ");
const fail = (e) => ({ ok: false, text: e.details ? flat(e.details) : e.message });
const Note = ({ n }) => (n ? <p role={n.ok ? "status" : "alert"} className={`text-sm ${n.ok ? "text-green-800" : "text-red-700"}`}>{n.text}</p> : null);

const toBody = (s, over = {}) => ({ bio: s.bio, expertise: s.expertise, languages: s.languages, price_credits_text: s.price_credits_text,
  is_approved: s.is_approved, is_available: s.is_available, ...over });

function Stylists() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-stylists"], queryFn: adminApi.stylists });
  const { data: users } = useQuery({ queryKey: ["admin-users"], queryFn: () => adminApi.users({ per_page: 200 }) });
  const [f, setF] = useState({ user_id: "", approved: true, price: "" });
  const [note, setNote] = useState(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-stylists"] });
  const candidates = (users?.users || []).filter((u) => u.role === "customer");

  async function update(s, over) { try { await adminApi.updateStylist(s.id, toBody(s, over)); refresh(); } catch (e) { setNote(fail(e)); } }
  async function create(e) {
    e.preventDefault(); setNote(null);
    try {
      await adminApi.createStylist({ user_id: Number(f.user_id), is_approved: f.approved, price_credits_text: f.price === "" ? null : Number(f.price) });
      setF({ user_id: "", approved: true, price: "" }); refresh(); qc.invalidateQueries({ queryKey: ["admin-users"] }); setNote({ ok: true, text: "Stylist created." });
    } catch (x) { setNote(fail(x)); }
  }

  return (
    <section className="rounded-2xl border border-black/10 p-6">
      <h2 className="font-serif text-xl">Stylists</h2>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead><tr className="border-b border-black/20"><th className="py-2">Stylist</th><th>Approved</th><th>Available</th><th>Price override</th></tr></thead>
          <tbody>
            {data?.stylists.map((s) => (
              <tr key={s.id} className="border-b border-black/10">
                <td className="py-2">{s.name}<span className="block text-xs text-black/60">{s.email}</span></td>
                <td><label><input type="checkbox" checked={s.is_approved} onChange={(e) => update(s, { is_approved: e.target.checked })} aria-label={`${s.name} approved`} /> {s.is_approved ? "Yes" : "No"}</label></td>
                <td><label><input type="checkbox" checked={s.is_available} onChange={(e) => update(s, { is_available: e.target.checked })} aria-label={`${s.name} available`} /> {s.is_available ? "Yes" : "No"}</label></td>
                <td><input type="number" min="0" aria-label={`${s.name} price in credits`} defaultValue={s.price_credits_text ?? ""} placeholder="default"
                  onBlur={(e) => { const v = e.target.value === "" ? null : Number(e.target.value); if (v !== s.price_credits_text) update(s, { price_credits_text: v }); }}
                  className="w-24 rounded-lg border border-black/20 px-2 py-1" /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {data?.stylists.length === 0 && <p className="mt-2 text-sm text-black/60">No stylists yet.</p>}
      </div>
      <form onSubmit={create} className="mt-4 grid gap-3 sm:grid-cols-4">
        <div className="sm:col-span-2">
          <label htmlFor="new-sty" className="mb-1 block text-sm font-medium">Make this customer a stylist</label>
          <select id="new-sty" required value={f.user_id} onChange={(e) => setF({ ...f, user_id: e.target.value })} className="w-full rounded-lg border border-black/20 px-3 py-2">
            <option value="">Select…</option>{candidates.map((u) => <option key={u.id} value={u.id}>{u.email}</option>)}
          </select>
        </div>
        <Field label="Price override (credits)" id="new-price" type="number" min="0" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} />
        <div className="flex items-end gap-3"><label className="text-sm"><input type="checkbox" checked={f.approved} onChange={(e) => setF({ ...f, approved: e.target.checked })} /> Approved</label>
          <button className="rounded-full bg-ink px-5 py-2 text-white hover:bg-accent">Create</button></div>
      </form>
      <Note n={note} />
    </section>
  );
}

const LABELS = {
  stylist_share_percent: "Stylist share of credits (%)", cancel_full_refund_hours: "Full refund if cancelled this many hours before",
  late_cancel_refund_percent: "Refund % for later cancellations", request_expiry_hours: "Unanswered requests expire after (hours)",
  min_notice_hours: "Minimum booking notice (hours)", reminder_minutes: "Reminder before session (minutes)",
  points_per_100_inr: "Points per ₹100 (delivered orders)", referrer_points: "Referrer reward (points)",
  referred_points: "Referred friend reward (points)", max_rewarded_referrals: "Max rewarded referrals per person",
};

function SectionForm({ title, sectionKey }) {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-section", sectionKey], queryFn: () => adminApi.section(sectionKey) });
  const [f, setF] = useState(null);
  const [note, setNote] = useState(null);
  useEffect(() => { if (data) setF(data.settings); }, [data]);
  if (!f) return <p>Loading…</p>;

  async function save(e) {
    e.preventDefault(); setNote(null);
    try {
      await adminApi.saveSection(sectionKey, Object.fromEntries(Object.entries(f).map(([k, v]) => [k, Number(v)])));
      qc.invalidateQueries({ queryKey: ["admin-section", sectionKey] }); setNote({ ok: true, text: "Saved." });
    } catch (x) { setNote(fail(x)); }
  }

  return (
    <form onSubmit={save} className="space-y-3 rounded-2xl border border-black/10 p-6">
      <h2 className="font-serif text-xl">{title}</h2>
      <p className="text-sm text-black/60">Placeholder defaults for open business decisions. Changes are audited.</p>
      <div className="grid gap-4 sm:grid-cols-2">
        {Object.keys(f).map((k) => <Field key={k} label={LABELS[k] || k} id={`${sectionKey}-${k}`} type="number" min="0" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />)}
      </div>
      <Note n={note} />
      <button className="rounded-full bg-ink px-6 py-2 text-white hover:bg-accent">Save</button>
    </form>
  );
}

function Offers() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-offers"], queryFn: adminApi.offers });
  const [d, setD] = useState({ name: "", points_cost: "", super_credits: "" });
  const [note, setNote] = useState(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-offers"] });
  const body = (o, over = {}) => ({ name: o.name, points_cost: o.points_cost, super_credits: o.super_credits, is_active: o.is_active, ...over });

  async function add(e) {
    e.preventDefault(); setNote(null);
    try { await adminApi.saveOffer(null, { name: d.name, points_cost: Number(d.points_cost), super_credits: Number(d.super_credits), is_active: true }); setD({ name: "", points_cost: "", super_credits: "" }); refresh(); }
    catch (x) { setNote(fail(x)); }
  }

  return (
    <section className="rounded-2xl border border-black/10 p-6">
      <h2 className="font-serif text-xl">Reward offers</h2>
      <table className="mt-3 w-full text-left text-sm">
        <thead><tr className="border-b border-black/20"><th className="py-2">Offer</th><th>Points</th><th>Super Credits</th><th>Active</th></tr></thead>
        <tbody>{data?.offers.map((o) => (
          <tr key={o.id} className="border-b border-black/10"><td className="py-2">{o.name}</td><td>{o.points_cost}</td><td>{o.super_credits}</td>
            <td><label><input type="checkbox" checked={o.is_active} aria-label={`${o.name} active`} onChange={async () => { await adminApi.saveOffer(o.id, body(o, { is_active: !o.is_active })); refresh(); }} /> {o.is_active ? "Yes" : "No"}</label></td></tr>))}</tbody>
      </table>
      <form onSubmit={add} className="mt-4 grid gap-3 sm:grid-cols-4">
        <Field label="Name" id="of-name" required value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} />
        <Field label="Points cost" id="of-pts" type="number" min="1" required value={d.points_cost} onChange={(e) => setD({ ...d, points_cost: e.target.value })} />
        <Field label="Super Credits" id="of-cr" type="number" min="1" required value={d.super_credits} onChange={(e) => setD({ ...d, super_credits: e.target.value })} />
        <div className="flex items-end"><button className="rounded-full bg-ink px-5 py-2 text-white hover:bg-accent">Add</button></div>
      </form>
      <Note n={note} />
    </section>
  );
}

export default function AdminStylists() {
  return (
    <div className="mx-auto max-w-5xl space-y-8 px-4 py-10">
      <div><h1 className="font-serif text-3xl">Stylists &amp; rewards</h1></div>
      <Stylists />
      <SectionForm title="Consultation policy" sectionKey="consultations" />
      <SectionForm title="Rewards rules" sectionKey="rewards" />
      <Offers />
    </div>
  );
}
