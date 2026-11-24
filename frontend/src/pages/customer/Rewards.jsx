import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { rewardsApi } from "../../services/api.js";
import { fmtDateTime } from "../../utils/money.js";

export default function Rewards() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["rewards"], queryFn: rewardsApi.balance });
  const { data: offers } = useQuery({ queryKey: ["reward-offers"], queryFn: rewardsApi.offers });
  const [page, setPage] = useState(1);
  const { data: tx } = useQuery({ queryKey: ["reward-tx", page], queryFn: () => rewardsApi.transactions({ page, per_page: 10 }), placeholderData: (p) => p });
  const [msg, setMsg] = useState(null);
  const [copied, setCopied] = useState(false);

  if (isLoading) return <p className="p-10 text-center" role="status">Loading…</p>;
  const r = data.rewards;
  const link = `${window.location.origin}/register?ref=${r.referral_code}`;
  const pages = tx ? Math.max(1, Math.ceil(tx.total / tx.per_page)) : 1;

  async function redeem(o) {
    setMsg(null);
    try {
      const res = await rewardsApi.redeem(o.id);
      ["rewards", "reward-tx", "wallet", "wallet-tx"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      setMsg({ ok: true, text: `Redeemed ${res.redeemed.points_spent} points for ${res.redeemed.super_credits} Super Credits.` });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
  }

  async function copy() {
    try { await navigator.clipboard.writeText(link); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* clipboard blocked */ }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-10 px-4 py-10">
      <h1 className="font-serif text-3xl">Rewards</h1>
      <div className="grid gap-4 md:grid-cols-2">
        <section aria-labelledby="pts-h" className="rounded-2xl border border-violet-200 bg-violet-50 p-6">
          <h2 id="pts-h" className="text-sm font-semibold uppercase tracking-widest text-black/60">Reward points</h2>
          <p className="mt-2 font-serif text-5xl">{r.balance}</p>
          <p className="mt-3 text-sm text-black/70">Earn {r.rules.points_per_100_inr} point per ₹100 on orders once they are <strong>delivered</strong>. Points are separate from Daily and Super Credits and have no cash value.</p>
        </section>
        <section aria-labelledby="ref-h" className="rounded-2xl border border-black/10 p-6">
          <h2 id="ref-h" className="font-serif text-xl">Refer a friend</h2>
          <p className="mt-2 text-sm text-black/70">When a friend you refer gets their first order delivered, you earn <strong>{r.rules.referrer_points}</strong> points and they get <strong>{r.rules.referred_points}</strong>.</p>
          <p className="mt-3 text-sm">Your code: <strong className="font-mono tracking-widest">{r.referral_code}</strong></p>
          <div className="mt-2 flex gap-2">
            <input readOnly aria-label="Referral link" value={link} onFocus={(e) => e.target.select()} className="min-w-0 flex-1 rounded-lg border border-black/20 px-3 py-1.5 text-xs" />
            <button onClick={copy} className="rounded-full border border-ink px-4 py-1.5 text-sm hover:bg-ink hover:text-white">{copied ? "Copied" : "Copy"}</button>
          </div>
          <p className="mt-2 text-xs text-black/60">{r.referrals.total} referred · {r.referrals.rewarded} rewarded</p>
        </section>
      </div>

      {msg && <p role={msg.ok ? "status" : "alert"} className={`text-sm ${msg.ok ? "text-green-800" : "text-red-700"}`}>{msg.text} {msg.ok && <Link to="/wallet" className="underline">See wallet</Link>}</p>}

      <section aria-labelledby="off-h">
        <h2 id="off-h" className="mb-3 font-serif text-xl">Redeem your points</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {offers?.offers.map((o) => (
            <div key={o.id} className="rounded-2xl border border-black/10 p-4">
              <p className="font-medium">{o.name}</p>
              <p className="text-sm text-black/70">{o.points_cost} points → {o.super_credits} Super Credits</p>
              <button disabled={r.balance < o.points_cost} onClick={() => redeem(o)} className="mt-3 w-full rounded-full bg-ink py-2 text-sm text-white hover:bg-accent disabled:opacity-50">
                {r.balance < o.points_cost ? `Need ${o.points_cost - r.balance} more` : "Redeem"}
              </button>
            </div>
          ))}
          {offers?.offers.length === 0 && <p className="text-sm text-black/60">No offers are available right now.</p>}
        </div>
      </section>

      <section aria-labelledby="hist-h">
        <h2 id="hist-h" className="mb-3 font-serif text-xl">Points history</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-left text-sm">
            <caption className="sr-only">Reward point transactions, newest first</caption>
            <thead><tr className="border-b border-black/20"><th className="py-2 pr-3">Date</th><th className="pr-3">Type</th><th className="pr-3">Details</th><th className="pr-3 text-right">Points</th><th className="text-right">Balance</th></tr></thead>
            <tbody>
              {tx?.transactions.map((t) => (
                <tr key={t.id} className="border-b border-black/10">
                  <td className="py-2 pr-3 whitespace-nowrap">{fmtDateTime(t.created_at)}</td>
                  <td className="pr-3">{t.transaction_type === "earn" ? "Earned" : t.transaction_type === "redeem" ? "Redeemed" : t.transaction_type}</td>
                  <td className="pr-3 text-black/70">{t.description}</td>
                  <td className="pr-3 text-right font-medium">{t.points > 0 ? `+${t.points}` : t.points}</td>
                  <td className="text-right text-black/60">{t.balance_after}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {tx?.transactions.length === 0 && <p className="mt-3 text-sm text-black/60">No points yet. Place an order to start earning.</p>}
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
