import { useEffect, useState } from "react";
import { useAuth } from "../../context/AuthContext.jsx";
import { Link, useNavigate } from "react-router-dom";
import { privacyApi, profileApi, tokenStore } from "../../services/api.js";
import Field from "../../components/layout/Field.jsx";

const TAGS = [
  ["preferred_styles", "Preferred styles", "casual, formal, streetwear"],
  ["preferred_colors", "Preferred colours", "black, beige"],
  ["preferred_brands", "Preferred brands", ""],
  ["preferred_categories", "Preferred categories", "shirts, shoes"],
  ["occasion_preferences", "Occasions", "college, office, party"],
];
const SIZES = ["top", "bottom", "shoe"];
const csv = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);
const toRupees = (m) => (m == null ? "" : String(m / 100));
const toPaise = (r) => (r === "" ? null : Math.round(Number(r) * 100));

function Notice({ n }) {
  if (!n) return null;
  return <p role={n.ok ? "status" : "alert"} className={`text-sm ${n.ok ? "text-green-800" : "text-red-700"}`}>{n.text}</p>;
}

function AccountForm() {
  const { user, setUser } = useAuth();
  const [name, setName] = useState(user.name);
  const [phone, setPhone] = useState(user.phone || "");
  const [note, setNote] = useState(null);

  async function save(e) {
    e.preventDefault();
    try {
      const r = await profileApi.update({ name, phone: phone || null });
      setUser(r.user); setNote({ ok: true, text: "Saved." });
    } catch (x) { setNote({ ok: false, text: x.message }); }
  }

  return (
    <form onSubmit={save} className="space-y-4">
      <h2 className="font-serif text-2xl">Account</h2>
      <Field label="Name" id="acc-name" value={name} onChange={(e) => setName(e.target.value)} required />
      <Field label="Email" id="acc-email" value={user.email} disabled />
      <Field label="Phone (optional)" id="acc-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
      <Notice n={note} />
      <button className="rounded-full bg-ink px-6 py-2 text-white hover:bg-accent">Save account</button>
    </form>
  );
}

function FashionForm() {
  const [f, setF] = useState(null);
  const [note, setNote] = useState(null);

  useEffect(() => {
    profileApi.getFashion().then(({ fashion: d }) => setF({
      ...Object.fromEntries(TAGS.map(([k]) => [k, d[k].join(", ")])),
      min: toRupees(d.budget_min_minor), max: toRupees(d.budget_max_minor),
      fit: d.fit_preferences || "",
      sizes: Object.fromEntries(SIZES.map((s) => [s, d.size_preferences[s] || ""])),
    })).catch((x) => setNote({ ok: false, text: x.message }));
  }, []);

  if (!f) return <p>Loading…</p>;

  async function save(e) {
    e.preventDefault();
    try {
      await profileApi.saveFashion({
        ...Object.fromEntries(TAGS.map(([k]) => [k, csv(f[k])])),
        budget_min_minor: toPaise(f.min), budget_max_minor: toPaise(f.max),
        fit_preferences: f.fit || null,
        size_preferences: Object.fromEntries(Object.entries(f.sizes).filter(([, v]) => v.trim())),
      });
      setNote({ ok: true, text: "Fashion profile saved." });
    } catch (x) {
      setNote({ ok: false, text: x.details ? Object.values(x.details).flat().join(" ") : x.message });
    }
  }

  async function remove() {
    if (!window.confirm("Delete your fashion profile? This cannot be undone.")) return;
    await profileApi.deleteFashion();
    setF({ ...Object.fromEntries(TAGS.map(([k]) => [k, ""])), min: "", max: "", fit: "", sizes: { top: "", bottom: "", shoe: "" } });
    setNote({ ok: true, text: "Fashion profile deleted." });
  }

  return (
    <form onSubmit={save} className="space-y-4">
      <h2 className="font-serif text-2xl">Fashion profile</h2>
      <p className="text-sm text-black/60">All fields are optional. Separate multiple values with commas. Used only to personalise suggestions.</p>
      {TAGS.map(([k, label, ph]) => (
        <Field key={k} label={label} id={k} placeholder={ph} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
      ))}
      <div className="grid grid-cols-2 gap-4">
        <Field label="Budget min (₹)" id="bmin" type="number" min="0" value={f.min} onChange={(e) => setF({ ...f, min: e.target.value })} />
        <Field label="Budget max (₹)" id="bmax" type="number" min="0" value={f.max} onChange={(e) => setF({ ...f, max: e.target.value })} />
      </div>
      <Field label="Fit preference" id="fit" placeholder="relaxed, slim…" value={f.fit} onChange={(e) => setF({ ...f, fit: e.target.value })} />
      <fieldset>
        <legend className="mb-1 text-sm font-medium">Sizes (optional)</legend>
        <div className="grid grid-cols-3 gap-4">
          {SIZES.map((s) => (
            <Field key={s} label={s[0].toUpperCase() + s.slice(1)} id={`size-${s}`} value={f.sizes[s]}
              onChange={(e) => setF({ ...f, sizes: { ...f.sizes, [s]: e.target.value } })} />
          ))}
        </div>
      </fieldset>
      <Notice n={note} />
      <div className="flex gap-3">
        <button className="rounded-full bg-ink px-6 py-2 text-white hover:bg-accent">Save fashion profile</button>
        <button type="button" onClick={remove} className="rounded-full border border-red-700 px-6 py-2 text-red-700 hover:bg-red-50">Delete</button>
      </div>
    </form>
  );
}

function PrivacyData() {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const [note, setNote] = useState(null);
  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  async function download() {
    setNote(null);
    try { await privacyApi.exportData(); setNote({ ok: true, text: "Your data download has started." }); } catch (x) { setNote({ ok: false, text: x.message }); }
  }

  async function remove(e) {
    e.preventDefault(); setNote(null); setBusy(true);
    try {
      await privacyApi.deleteAccount(pw, confirm);
      tokenStore.clear(); setUser(null); navigate("/", { replace: true });
    } catch (x) { setNote({ ok: false, text: x.details ? Object.values(x.details).flat().join(" ") : x.message }); } finally { setBusy(false); }
  }

  return (
    <section aria-labelledby="priv-h" className="space-y-4 md:col-span-2">
      <h2 id="priv-h" className="font-serif text-2xl">Privacy &amp; data</h2>
      <p className="text-sm text-black/70">See our <Link className="underline" to="/privacy">Privacy Policy</Link>. You can download everything we hold about you, or permanently delete your account.</p>
      <button onClick={download} className="rounded-full border border-ink px-5 py-2 text-sm hover:bg-ink hover:text-white">Download my data (JSON)</button>
      <div>
        {!open ? (
          <button onClick={() => setOpen(true)} className="text-sm text-red-700 underline">Delete my account…</button>
        ) : (
          <form onSubmit={remove} className="max-w-md space-y-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm">
            <p><strong>This is permanent.</strong> Your personal data is erased. Remaining credits, reward points and any subscription are forfeited without refund. Orders in progress or upcoming consultations must be finished or cancelled first.</p>
            <Field label="Your password" id="del-pw" type="password" required autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} />
            <Field label='Type DELETE to confirm' id="del-confirm" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            <div className="flex gap-3">
              <button disabled={busy || confirm !== "DELETE"} className="rounded-full bg-red-700 px-5 py-2 text-white disabled:opacity-50">{busy ? "Deleting…" : "Delete account"}</button>
              <button type="button" onClick={() => { setOpen(false); setPw(""); setConfirm(""); }} className="underline">Keep my account</button>
            </div>
          </form>
        )}
      </div>
      <Notice n={note} />
    </section>
  );
}

export default function Account() {
  return (
    <div className="mx-auto grid max-w-5xl gap-12 px-4 py-12 md:grid-cols-2">
      <AccountForm />
      <FashionForm />
      <PrivacyData />
    </div>
  );
}
