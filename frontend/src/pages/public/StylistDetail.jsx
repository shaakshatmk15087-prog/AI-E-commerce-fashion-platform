import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";
import { stylistApi } from "../../services/api.js";
import { fmtDateTime } from "../../utils/money.js";

export default function StylistDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const { data, isError } = useQuery({ queryKey: ["stylist", id], queryFn: () => stylistApi.get(id), retry: false });
  const { data: slotData } = useQuery({ queryKey: ["stylist-slots", id], queryFn: () => stylistApi.slots(id) });
  const [picked, setPicked] = useState(null);
  const [quote, setQuote] = useState(null);
  const [notes, setNotes] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  if (isError) return <p className="p-10 text-center">Stylist not found. <Link className="underline" to="/stylists">All stylists</Link></p>;
  if (!data) return <p className="p-10 text-center" role="status">Loading…</p>;
  const s = data.stylist;

  async function choose(slot) {
    setErr(""); setQuote(null);
    if (!user) return navigate("/login", { state: { from: location } });
    setPicked(slot);
    try { setQuote((await stylistApi.quote(slot.id)).quote); } catch (e) { setErr(e.message); setPicked(null); }
  }

  async function confirm() {
    setBusy(true); setErr("");
    try {
      const r = await stylistApi.book(picked.id, notes);
      ["wallet", "wallet-tx", "stylist-slots", "consultations"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      navigate(`/consultations/${r.consultation.id}`);
    } catch (e) {
      setErr(e.message);
      if (e.status === 409) { qc.invalidateQueries({ queryKey: ["stylist-slots", id] }); setPicked(null); setQuote(null); }
    } finally { setBusy(false); }
  }

  const byDay = {};
  (slotData?.slots || []).forEach((sl) => { (byDay[new Date(sl.start_at).toDateString()] ||= []).push(sl); });

  return (
    <div className="mx-auto grid max-w-5xl gap-10 px-4 py-10 md:grid-cols-[1fr_340px]">
      <section>
        <Link to="/stylists" className="text-sm underline">← All stylists</Link>
        <h1 className="mt-2 font-serif text-3xl">{s.name}</h1>
        <p className="mt-3 text-black/70">{s.bio}</p>
        <ul className="mt-3 flex flex-wrap gap-2 text-xs">{s.expertise.map((e) => <li key={e} className="rounded-full bg-sand px-2.5 py-1">{e}</li>)}</ul>
        <p className="mt-3 text-sm text-black/60">Languages: {s.languages.join(", ") || "—"} · Text chat consultation</p>

        <h2 className="mb-3 mt-8 font-serif text-xl">Choose a time <span className="text-sm font-sans text-black/60">(your local time)</span></h2>
        {Object.keys(byDay).length === 0 && <p className="text-sm text-black/60">No open slots right now.</p>}
        {Object.entries(byDay).map(([day, slots]) => (
          <div key={day} className="mb-4">
            <p className="mb-2 text-sm font-medium">{day}</p>
            <div className="flex flex-wrap gap-2">
              {slots.map((sl) => (
                <button key={sl.id} onClick={() => choose(sl)} aria-pressed={picked?.id === sl.id}
                  className={`rounded-full border px-4 py-1.5 text-sm ${picked?.id === sl.id ? "border-ink bg-ink text-white" : "border-black/20 hover:border-ink"}`}>
                  {new Date(sl.start_at).toLocaleTimeString([], { timeStyle: "short" })}
                </button>
              ))}
            </div>
          </div>
        ))}
      </section>

      <aside aria-label="Booking summary" className="h-fit rounded-2xl bg-sand p-6">
        <h2 className="font-serif text-xl">Booking</h2>
        {!picked && <p className="mt-2 text-sm text-black/60">Pick a time to see the exact cost.</p>}
        {err && <p role="alert" className="mt-3 text-sm text-red-700">{err}</p>}
        {picked && quote && (
          <div className="mt-3 space-y-3 text-sm">
            <p><strong>{fmtDateTime(picked.start_at)}</strong> with {s.name}</p>
            <p>Cost: <strong>{quote.cost} Super Credits</strong>{quote.credit_types.length === 1 && " (Super Credits only)"}</p>
            <p>You have {quote.available} usable credits. After booking: <strong>{quote.balances_after.super}</strong> Super.</p>
            {!quote.sufficient && <p role="alert" className="text-red-700">Not enough Super Credits. <Link to="/wallet" className="underline">Top up</Link></p>}
            <div>
              <label htmlFor="notes" className="mb-1 block font-medium">What would you like help with? (optional)</label>
              <textarea id="notes" rows={3} maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} className="w-full rounded-lg border border-black/20 px-3 py-2" />
            </div>
            <p className="text-xs text-black/60">Credits are held now. Free cancellation until {quote.policy.full_refund_hours}h before the start; after that {quote.policy.late_refund_percent}% is refunded. If the stylist declines or does not respond within {quote.policy.request_expiry_hours}h, you get everything back.</p>
            <button disabled={!quote.sufficient || busy} onClick={confirm} className="w-full rounded-full bg-ink py-2.5 text-white hover:bg-accent disabled:opacity-50">{busy ? "Booking…" : `Confirm and pay ${quote.cost} credits`}</button>
          </div>
        )}
      </aside>
    </div>
  );
}
