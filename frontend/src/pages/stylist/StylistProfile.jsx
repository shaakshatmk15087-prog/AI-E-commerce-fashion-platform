import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import Field from "../../components/layout/Field.jsx";
import { stylistApi } from "../../services/api.js";
import { fmtDateTime } from "../../utils/money.js";

const csv = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);
const flat = (d) => Object.values(d || {}).flat(Infinity).join(" ");

function ProfileForm() {
  const { data } = useQuery({ queryKey: ["stylist-me"], queryFn: stylistApi.myProfile });
  const qc = useQueryClient();
  const [f, setF] = useState(null);
  const [note, setNote] = useState(null);
  useEffect(() => {
    if (data) { const s = data.stylist; setF({ bio: s.bio || "", expertise: s.expertise.join(", "), languages: s.languages.join(", "), is_available: s.is_available }); }
  }, [data]);
  if (!f) return <p>Loading…</p>;

  async function save(e) {
    e.preventDefault(); setNote(null);
    try {
      await stylistApi.saveProfile({ bio: f.bio || null, expertise: csv(f.expertise), languages: csv(f.languages), is_available: f.is_available });
      qc.invalidateQueries({ queryKey: ["stylist-me"] }); setNote({ ok: true, text: "Saved." });
    } catch (x) { setNote({ ok: false, text: x.details ? flat(x.details) : x.message }); }
  }

  return (
    <form onSubmit={save} className="space-y-4">
      <h2 className="font-serif text-2xl">Profile</h2>
      <p className="text-sm text-black/60">Price: <strong>{data.stylist.price_credits} Super Credits</strong> per consultation (set by the platform). {data.stylist.is_approved ? "Your profile is approved." : "Awaiting approval."}</p>
      <div>
        <label htmlFor="bio" className="mb-1 block text-sm font-medium">Biography</label>
        <textarea id="bio" rows={4} maxLength={2000} value={f.bio} onChange={(e) => setF({ ...f, bio: e.target.value })} className="w-full rounded-lg border border-black/20 px-3 py-2" />
      </div>
      <Field label="Areas of expertise (comma separated)" id="exp" value={f.expertise} onChange={(e) => setF({ ...f, expertise: e.target.value })} />
      <Field label="Languages (comma separated)" id="lang" value={f.languages} onChange={(e) => setF({ ...f, languages: e.target.value })} />
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_available} onChange={(e) => setF({ ...f, is_available: e.target.checked })} /> Accepting new bookings</label>
      {note && <p role={note.ok ? "status" : "alert"} className={`text-sm ${note.ok ? "text-green-800" : "text-red-700"}`}>{note.text}</p>}
      <button className="rounded-full bg-ink px-6 py-2 text-white hover:bg-accent">Save profile</button>
    </form>
  );
}

function Availability() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["stylist-slots-mine"], queryFn: stylistApi.mySlots });
  const [start, setStart] = useState("");
  const [minutes, setMinutes] = useState(30);
  const [note, setNote] = useState(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["stylist-slots-mine"] });

  async function add(e) {
    e.preventDefault(); setNote(null);
    try {
      await stylistApi.addSlot(new Date(start).toISOString(), Number(minutes));   // datetime-local is the stylist's local time
      refresh(); setNote({ ok: true, text: "Slot added." });
    } catch (x) { setNote({ ok: false, text: x.details ? flat(x.details) : x.message }); }
  }
  async function remove(id) {
    try { await stylistApi.deleteSlot(id); refresh(); } catch (x) { setNote({ ok: false, text: x.message }); }
  }

  return (
    <section>
      <h2 className="font-serif text-2xl">Availability</h2>
      <form onSubmit={add} className="mt-3 flex flex-wrap items-end gap-3">
        <Field label="Start (your local time)" id="slot-start" type="datetime-local" required value={start} onChange={(e) => setStart(e.target.value)} />
        <div>
          <label htmlFor="slot-min" className="mb-1 block text-sm font-medium">Length</label>
          <select id="slot-min" value={minutes} onChange={(e) => setMinutes(e.target.value)} className="rounded-lg border border-black/20 px-3 py-2">
            {[15, 30, 45, 60].map((m) => <option key={m} value={m}>{m} min</option>)}
          </select>
        </div>
        <button className="rounded-full bg-ink px-5 py-2 text-white hover:bg-accent">Add slot</button>
      </form>
      {note && <p role={note.ok ? "status" : "alert"} className={`mt-2 text-sm ${note.ok ? "text-green-800" : "text-red-700"}`}>{note.text}</p>}
      <ul className="mt-4 divide-y divide-black/10 text-sm">
        {data?.slots.map((s) => (
          <li key={s.id} className="flex items-center justify-between py-2">
            <span>{fmtDateTime(s.start_at)} – {new Date(s.end_at).toLocaleTimeString([], { timeStyle: "short" })} · {s.status === "booked" ? "Booked" : "Open"}</span>
            {s.status === "open" && <button className="underline" onClick={() => remove(s.id)} aria-label={`Remove slot at ${fmtDateTime(s.start_at)}`}>Remove</button>}
          </li>
        ))}
        {data?.slots.length === 0 && <li className="py-2 text-black/60">No upcoming slots. Add some so customers can book you.</li>}
      </ul>
    </section>
  );
}

export default function StylistProfile() {
  return (
    <div className="mx-auto grid max-w-5xl gap-12 px-4 py-10 md:grid-cols-2">
      <div className="md:col-span-2"><Link to="/stylist" className="text-sm underline">← Dashboard</Link></div>
      <ProfileForm />
      <Availability />
    </div>
  );
}
