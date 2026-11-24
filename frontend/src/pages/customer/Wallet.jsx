import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import PaymentSimulator from "../../components/payments/PaymentSimulator.jsx";
import { walletApi } from "../../services/api.js";
import { money } from "../../utils/money.js";

const fmt = (iso) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

function untilText(iso, now) {
  const mins = Math.max(0, Math.round((new Date(iso) - now) / 60000));
  const h = Math.floor(mins / 60);
  return h > 0 ? `${h}h ${mins % 60}m` : `${mins}m`;
}

const TYPE_LABEL = {
  grant: "Granted", purchase: "Purchased", subscription: "Subscription", spend: "Spent", refund: "Refunded",
  expiry: "Expired", adjustment: "Adjustment", reservation: "Reserved", release: "Released",
};

function CreditCard({ kind, title, balance, children }) {
  return (
    <section aria-labelledby={`${kind}-h`} className={`rounded-2xl border p-6 ${kind === "daily" ? "border-sky-200 bg-sky-50" : "border-amber-200 bg-amber-50"}`}>
      <h2 id={`${kind}-h`} className="text-sm font-semibold uppercase tracking-widest text-black/60">{title}</h2>
      <p className="mt-2 font-serif text-5xl" aria-label={`${balance} ${title}`}>{balance}</p>
      <div className="mt-3 space-y-1 text-sm text-black/70">{children}</div>
    </section>
  );
}

export default function Wallet() {
  const qc = useQueryClient();
  const [now, setNow] = useState(() => new Date());
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const [buying, setBuying] = useState(null);
  const [msg, setMsg] = useState(null);

  useEffect(() => { const t = setInterval(() => setNow(new Date()), 30000); return () => clearInterval(t); }, []);

  const { data, isLoading, isError } = useQuery({ queryKey: ["wallet"], queryFn: walletApi.wallet, refetchOnWindowFocus: true });
  const { data: packs } = useQuery({ queryKey: ["packs"], queryFn: walletApi.packs });
  const { data: costs } = useQuery({ queryKey: ["costs"], queryFn: walletApi.costs });
  const tx = useQuery({ queryKey: ["wallet-tx", filter, page], queryFn: () => walletApi.transactions({ credit_type: filter, page, per_page: 10 }), placeholderData: (p) => p });

  const refresh = () => { qc.invalidateQueries({ queryKey: ["wallet"] }); qc.invalidateQueries({ queryKey: ["wallet-tx"] }); };

  async function buy(pack) {
    setMsg(null);
    try { setBuying({ pack, payment: (await walletApi.buyPack(pack.id)).payment }); } catch (e) { setMsg({ ok: false, text: e.message }); }
  }

  async function cancelSub() {
    if (!window.confirm("Cancel your subscription? You keep access until the end of the paid period. Payments are not refunded.")) return;
    try { await walletApi.cancelSubscription(); refresh(); setMsg({ ok: true, text: "Subscription will end at the close of the current period." }); }
    catch (e) { setMsg({ ok: false, text: e.message }); }
  }

  if (isLoading) return <p className="p-10 text-center" role="status">Loading…</p>;
  if (isError) return <p className="p-10 text-center" role="alert">Could not load your wallet. <button className="underline" onClick={refresh}>Retry</button></p>;
  const { wallet: w, subscription: sub } = data;
  const pages = tx.data ? Math.max(1, Math.ceil(tx.data.total / tx.data.per_page)) : 1;

  return (
    <div className="mx-auto max-w-5xl space-y-10 px-4 py-10">
      <h1 className="font-serif text-3xl">Wallet</h1>

      <div className="grid gap-4 md:grid-cols-2">
        <CreditCard kind="daily" title="Daily Credits" balance={w.daily.balance}>
          <p>Free allowance: {w.daily.daily_allowance} per day.</p>
          <p><strong>Unused Daily Credits expire</strong> at the daily reset:</p>
          <p>{fmt(w.daily.next_reset_at)} ({w.daily.timezone}) · in {untilText(w.daily.next_reset_at, now)}</p>
        </CreditCard>
        <CreditCard kind="super" title="Super Credits" balance={w.super.balance}>
          <p>Bought or earned through a subscription.</p>
          <p><strong>They never expire</strong> and add up from day to day.</p>
        </CreditCard>
      </div>

      {msg && <p role={msg.ok ? "status" : "alert"} className={`text-sm ${msg.ok ? "text-green-800" : "text-red-700"}`}>{msg.text}</p>}

      <section aria-labelledby="sub-h" className="rounded-2xl border border-black/10 p-6">
        <h2 id="sub-h" className="font-serif text-xl">Subscription</h2>
        {sub ? (
          <div className="mt-2 text-sm">
            <p><strong>{sub.plan.name}</strong> · {sub.status}{sub.cancel_at && " (ending)"}</p>
            <p className="text-black/70">{sub.cancel_at ? "Access ends" : "Paid until"} {fmt(sub.current_period_end)}. {sub.plan.grant_frequency === "daily" ? `${sub.plan.super_credit_amount} Super Credits every day.` : `${sub.plan.super_credit_amount} Super Credits per ${sub.plan.billing_interval}.`}</p>
            <div className="mt-3 flex gap-4">
              <Link to="/subscriptions" className="underline">Renew or change</Link>
              {!sub.cancel_at && <button onClick={cancelSub} className="underline">Cancel</button>}
            </div>
          </div>
        ) : (
          <p className="mt-2 text-sm text-black/70">No active subscription. <Link to="/subscriptions" className="underline">See plans</Link></p>
        )}
      </section>

      <section aria-labelledby="buy-h">
        <h2 id="buy-h" className="mb-3 font-serif text-xl">Buy Super Credits</h2>
        {buying ? (
          <PaymentSimulator title="Pay" amountMinor={buying.pack.price_minor} providerOrderId={buying.payment.provider_order_id}
            description={`${buying.pack.name}: ${buying.pack.credits} Super Credits`} onCancel={() => setBuying(null)}
            onDone={(r, outcome) => {
              setBuying(null); refresh();
              setMsg(outcome === "success" ? { ok: true, text: `${buying.pack.credits} Super Credits added.` } : { ok: false, text: "Payment failed. No credits were added." });
            }} />
        ) : (
          <div className="grid gap-3 sm:grid-cols-3">
            {packs?.packs.map((p) => (
              <div key={p.id} className="rounded-2xl border border-black/10 p-4">
                <p className="font-medium">{p.name}</p>
                <p className="text-2xl font-serif">{p.credits} <span className="text-sm font-sans text-black/60">Super Credits</span></p>
                <p className="text-sm text-black/70">{money(p.price_minor)}</p>
                <button onClick={() => buy(p)} className="mt-3 w-full rounded-full bg-ink py-2 text-sm text-white hover:bg-accent">Buy</button>
              </div>
            ))}
            {packs?.packs.length === 0 && <p className="text-sm text-black/60">No credit packs are available right now.</p>}
          </div>
        )}
      </section>

      <section aria-labelledby="costs-h">
        <h2 id="costs-h" className="mb-2 font-serif text-xl">What credits are used for</h2>
        <ul className="text-sm text-black/80">
          {costs?.services.map((s) => (
            <li key={s.service}>{s.label}: <strong>{s.cost === 0 ? "free right now" : `${s.cost} credit${s.cost === 1 ? "" : "s"}`}</strong>
              {s.cost > 0 && <> ({s.credit_types.length === 2 ? `uses ${costs.spend_priority === "daily_first" ? "Daily Credits first, then Super" : "Super Credits first, then Daily"}` : `${s.credit_types[0]} credits only`})</>}</li>
          ))}
        </ul>
        <p className="mt-1 text-xs text-black/60">The exact split is shown before anything is spent.</p>
      </section>

      <section aria-labelledby="hist-h">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 id="hist-h" className="font-serif text-xl">Transaction history</h2>
          <label className="text-sm">Show{" "}
            <select value={filter} onChange={(e) => { setFilter(e.target.value); setPage(1); }} className="rounded-lg border border-black/20 px-2 py-1">
              <option value="">All credits</option><option value="daily">Daily only</option><option value="super">Super only</option>
            </select>
          </label>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <caption className="sr-only">Credit transactions, newest first</caption>
            <thead><tr className="border-b border-black/20"><th className="py-2 pr-3">Date</th><th className="pr-3">Credits</th><th className="pr-3">Type</th><th className="pr-3">Details</th><th className="pr-3 text-right">Change</th><th className="text-right">Balance</th></tr></thead>
            <tbody>
              {tx.data?.transactions.map((t) => (
                <tr key={t.id} className="border-b border-black/10">
                  <td className="py-2 pr-2 whitespace-nowrap">{fmt(t.created_at)}</td>
                  <td className="pr-3">{t.credit_type === "daily" ? "Daily" : "Super"}</td>
                  <td className="pr-3">{TYPE_LABEL[t.transaction_type] || t.transaction_type}</td>
                  <td className="pr-3 text-black/70">{t.description}</td>
                  <td className="pr-3 text-right font-medium">{t.amount > 0 ? `+${t.amount}` : t.amount}</td>
                  <td className="text-right text-black/60">{t.balance_after}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {tx.data?.transactions.length === 0 && <p className="mt-3 text-sm text-black/60">No transactions yet.</p>}
        </div>
        {pages > 1 && (
          <nav aria-label="Pagination" className="mt-4 flex items-center justify-center gap-4 text-sm">
            <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="underline disabled:opacity-40">Previous</button>
            <span>Page {page} of {pages}</span>
            <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="underline disabled:opacity-40">Next</button>
          </nav>
        )}
      </section>
    </div>
  );
}
