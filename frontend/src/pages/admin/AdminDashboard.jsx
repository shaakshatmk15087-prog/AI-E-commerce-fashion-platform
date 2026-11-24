import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { adminApi } from "../../services/api.js";
import { money, statusLabel } from "../../utils/money.js";

function Tile({ label, value, hint, tone = "bg-sand" }) {
  return (
    <div className={`rounded-xl p-4 ${tone}`}>
      <dt className="text-xs uppercase tracking-widest text-black/60">{label}</dt>
      <dd className="mt-1">
        <span className="block font-serif text-3xl">{value}</span>
        {hint && <span className="mt-1 block text-xs text-black/60">{hint}</span>}
      </dd>
    </div>
  );
}

function Card({ title, children }) {
  return <section className="rounded-2xl border border-black/10 p-5"><h2 className="mb-3 font-serif text-xl">{title}</h2>{children}</section>;
}

function Rows({ rows, empty = "Nothing in this period." }) {
  if (!rows.length) return <p className="text-sm text-black/60">{empty}</p>;
  return <table className="w-full text-sm"><tbody>{rows.map(([k, v]) => <tr key={k} className="border-b border-black/10 last:border-0"><th scope="row" className="py-1.5 pr-3 text-left font-normal">{k}</th><td className="py-1.5 text-right font-medium">{v}</td></tr>)}</tbody></table>;
}

export default function AdminDashboard() {
  const [days, setDays] = useState(30);
  const { data: d, isLoading, isError, refetch } = useQuery({ queryKey: ["admin-dashboard", days], queryFn: () => adminApi.dashboard(days), placeholderData: (p) => p });

  if (isError) return <p role="alert" className="p-10 text-center">Could not load the dashboard. <button className="underline" onClick={() => refetch()}>Retry</button></p>;
  if (isLoading || !d) return <p role="status" className="p-10 text-center">Loading…</p>;
  const peak = Math.max(1, ...d.daily.map((x) => x.amount_minor));

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-serif text-3xl">Dashboard</h1>
        <label className="text-sm">Period{" "}
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-lg border border-black/20 px-2 py-1">
            {[7, 30, 90, 365].map((n) => <option key={n} value={n}>Last {n} days</option>)}
          </select>
        </label>
      </div>

      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label="Net revenue" value={money(d.revenue.net_minor)} hint={`${money(d.revenue.gross_minor)} gross − ${money(d.revenue.refunded_minor)} refunded`} />
        <Tile label="Orders" value={d.orders.total} hint={`${d.orders.by_status.pending_payment || 0} awaiting payment`} />
        <Tile label="New customers" value={d.users.new} hint={`${d.users.customers} customers total`} />
        <Tile label="Active subscriptions" value={d.subscriptions.active} />
      </dl>

      {(d.inventory.low_stock_variants > 0 || d.inventory.out_of_stock_variants > 0) && (
        <p role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm">
          <strong>Stock alert:</strong> {d.inventory.out_of_stock_variants} variant(s) out of stock and {d.inventory.low_stock_variants} running low (1–{d.inventory.threshold} left).{" "}
          <Link to="/admin/catalogue" className="underline">Review inventory</Link>
        </p>
      )}

      <div className="grid gap-5 md:grid-cols-2">
        <Card title="Payments received">
          <Rows rows={Object.entries(d.revenue.by_purpose).map(([k, v]) => [`${statusLabel(k)} (${v.count})`, money(v.amount_minor)])} />
          <div className="mt-4" role="img" aria-label={`Daily payments: ${d.daily.map((x) => `${x.date} ${money(x.amount_minor)}`).join(", ") || "none"}`}>
            <div className="flex h-16 items-end gap-0.5" aria-hidden="true">
              {d.daily.map((x) => <div key={x.date} title={`${x.date}: ${money(x.amount_minor)}`} style={{ height: `${Math.max(4, (x.amount_minor / peak) * 100)}%` }} className="min-w-[3px] flex-1 rounded-t bg-accent" />)}
            </div>
            <p className="mt-1 text-xs text-black/60">Daily payments (hover a bar for the day)</p>
          </div>
        </Card>
        <Card title="Orders by status"><Rows rows={Object.entries(d.orders.by_status).map(([k, v]) => [statusLabel(k), v])} /></Card>
        <Card title="Top products"><Rows rows={d.top_products.map((p) => [`${p.name} × ${p.units}`, money(p.revenue_minor)])} empty="No paid orders in this period." /></Card>
        <Card title="Consultations"><Rows rows={Object.entries(d.consultations.by_status).map(([k, v]) => [statusLabel(k), v])} /></Card>
        <Card title="Credits in circulation">
          <Rows rows={[["Daily Credits (unspent today)", d.credits.daily_outstanding], ["Super Credits (liability)", d.credits.super_outstanding]]} />
        </Card>
        <Card title="AI stylist usage">
          <Rows rows={[["Assistant messages", d.ai.messages], ["Answered by AI", d.ai.ai_mode], ["Rule-based fallback", d.ai.fallback_mode],
            ["Input tokens", d.ai.input_tokens.toLocaleString()], ["Output tokens", d.ai.output_tokens.toLocaleString()]]} />
          {d.ai.messages > 0 && d.ai.fallback_mode / d.ai.messages > 0.2 && <p className="mt-2 text-sm text-amber-800">More than 20% of replies used the fallback. Check the AI service and API key.</p>}
          {d.ai.truncated && <p className="mt-2 text-xs text-black/60">Counts are truncated at 50,000 messages.</p>}
        </Card>
      </div>
    </div>
  );
}
