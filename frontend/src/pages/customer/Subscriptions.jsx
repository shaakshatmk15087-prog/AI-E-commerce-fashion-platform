import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import PaymentSimulator from "../../components/payments/PaymentSimulator.jsx";
import { walletApi } from "../../services/api.js";
import { money } from "../../utils/money.js";

export default function Subscriptions() {
  const qc = useQueryClient();
  const { data: plans, isLoading } = useQuery({ queryKey: ["plans"], queryFn: walletApi.plans });
  const { data: mine } = useQuery({ queryKey: ["subscription"], queryFn: walletApi.mySubscription });
  const [paying, setPaying] = useState(null);
  const [msg, setMsg] = useState(null);
  const current = mine?.subscription;

  async function choose(plan) {
    setMsg(null);
    try { setPaying({ plan, payment: (await walletApi.subscribe(plan.id)).payment }); }
    catch (e) { setMsg({ ok: false, text: e.message }); }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <h1 className="font-serif text-3xl">Subscription plans</h1>
      <p className="mt-2 text-sm text-black/70">Plans add <strong>Super Credits</strong>, which never expire. They are separate from your free Daily Credits. See <Link className="underline" to="/wallet">your wallet</Link>.</p>
      {current && <p role="status" className="mt-4 rounded-xl bg-sand p-3 text-sm">You are on <strong>{current.plan.name}</strong> until {new Date(current.current_period_end).toLocaleDateString()}. Renewing adds another period.</p>}
      {msg && <p role={msg.ok ? "status" : "alert"} className={`mt-4 text-sm ${msg.ok ? "text-green-800" : "text-red-700"}`}>{msg.text}</p>}

      {paying ? (
        <div className="mt-8 max-w-xl">
          <PaymentSimulator title="Pay" amountMinor={paying.plan.price_minor} providerOrderId={paying.payment.provider_order_id}
            description={`${paying.plan.name} · one ${paying.plan.billing_interval}`} onCancel={() => setPaying(null)}
            onDone={(r, outcome) => {
              setPaying(null);
              ["subscription", "wallet", "wallet-tx"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
              setMsg(outcome === "success" ? { ok: true, text: `${paying.plan.name} is active.` } : { ok: false, text: "Payment failed. Your plan was not activated." });
            }} />
        </div>
      ) : (
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          {isLoading && <p role="status">Loading…</p>}
          {plans?.plans.map((p) => {
            const mineNow = current?.plan.id === p.id;
            const blocked = current && !mineNow;
            return (
              <article key={p.id} className={`rounded-2xl border p-6 ${mineNow ? "border-ink" : "border-black/10"}`}>
                <h2 className="font-serif text-2xl">{p.name} {mineNow && <span className="ml-2 rounded-full bg-ink px-2 py-0.5 align-middle text-xs text-white">Your plan</span>}</h2>
                <p className="mt-1 text-xl">{money(p.price_minor)} <span className="text-sm text-black/60">/ {p.billing_interval}</span></p>
                {p.description && <p className="mt-2 text-sm text-black/70">{p.description}</p>}
                <ul className="mt-3 list-disc pl-5 text-sm">
                  {p.benefits.map((b) => <li key={b}>{b}</li>)}
                  <li>{p.grant_frequency === "daily" ? `${p.super_credit_amount} Super Credits every day` : `${p.super_credit_amount} Super Credits with each ${p.billing_interval}`}</li>
                </ul>
                <button disabled={blocked} onClick={() => choose(p)} className="mt-4 w-full rounded-full bg-ink py-2.5 text-white hover:bg-accent disabled:opacity-50">
                  {mineNow ? "Renew" : blocked ? "Finish your current plan first" : "Subscribe"}
                </button>
              </article>
            );
          })}
          {plans?.plans.length === 0 && <p>No plans are available right now.</p>}
        </div>
      )}
      <p className="mt-6 text-xs text-black/60">Renewals are manual for now. Cancelling keeps access until the paid period ends; paid periods are not refunded.</p>
    </div>
  );
}
