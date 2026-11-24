import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import ConsultStatus from "../../components/stylists/ConsultStatus.jsx";
import { stylistApi } from "../../services/api.js";
import { fmtDateTime } from "../../utils/money.js";

const TABS = [["requested", "Requests"], ["accepted", "Upcoming"], ["completed,declined,cancelled,expired", "History"]];

export default function StylistDashboard() {
  const [tab, setTab] = useState(TABS[0][0]);
  const { data: earn } = useQuery({ queryKey: ["stylist-earnings"], queryFn: stylistApi.earnings });
  const { data: me } = useQuery({ queryKey: ["stylist-me"], queryFn: stylistApi.myProfile });
  const { data, isLoading } = useQuery({
    queryKey: ["consultations", "stylist", tab], queryFn: () => stylistApi.consultations({ as: "stylist", status: tab }), refetchInterval: 15000,
  });
  const e = earn?.earnings;

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-serif text-3xl">Stylist dashboard</h1>
        <Link to="/stylist/profile" className="rounded-full border border-ink px-4 py-1.5 text-sm hover:bg-ink hover:text-white">Profile &amp; availability</Link>
      </div>
      {me && !me.stylist.is_approved && <p role="status" className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm">Your profile is awaiting approval. Customers can't book you yet.</p>}

      {e && (
        <dl className="mt-6 grid gap-3 sm:grid-cols-4">
          {[["Pending requests", e.pending_requests], ["Upcoming", e.upcoming], ["Completed", e.completed], ["Earned (credits)", e.earned_credits]].map(([k, v]) => (
            <div key={k} className="rounded-xl bg-sand p-4"><dt className="text-xs uppercase tracking-widest text-black/60">{k}</dt><dd className="font-serif text-3xl">{v}</dd></div>
          ))}
        </dl>
      )}
      {e && <p className="mt-2 text-xs text-black/60">Earnings are a record of your {e.share_percent}% share of completed consultations; payout arrangements are set by the platform.</p>}

      <div role="tablist" aria-label="Consultations" className="mt-8 flex gap-2 border-b border-black/10">
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`-mb-px border-b-2 px-4 py-2 text-sm ${tab === k ? "border-ink font-medium" : "border-transparent text-black/60"}`}>{label}</button>
        ))}
      </div>
      {isLoading && <p role="status" className="mt-4">Loading…</p>}
      {data?.consultations.length === 0 && <p className="mt-4 text-sm text-black/60">Nothing here.</p>}
      <ul className="divide-y divide-black/10">
        {data?.consultations.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div>
              <Link to={`/stylist/consultations/${c.id}`} className="font-medium underline">{c.customer.name}</Link>
              <p className="text-sm text-black/60">{fmtDateTime(c.scheduled_start)} · {c.credit_cost} credits</p>
              {c.customer_notes && <p className="mt-1 max-w-xl text-sm text-black/70">"{c.customer_notes}"</p>}
            </div>
            <ConsultStatus status={c.status} />
          </li>
        ))}
      </ul>
    </div>
  );
}
