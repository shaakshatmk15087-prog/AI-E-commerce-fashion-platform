import { useState } from "react";
import { shopApi, walletApi } from "../../services/api.js";
import { money } from "../../utils/money.js";

/** Test-mode stand-in for the payment gateway page. Whatever the outcome, the server decides what it means. */
export default function PaymentSimulator({ title, amountMinor, description, orderId, providerOrderId, onDone, onCancel }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function pay(outcome) {
    setBusy(true); setErr("");
    try {
      const r = orderId ? await shopApi.mockPay(orderId, outcome) : await walletApi.mockPay(providerOrderId, outcome);
      onDone(r, outcome);
    } catch (x) { setErr(x.message); } finally { setBusy(false); }
  }

  return (
    <div className="rounded-2xl border border-dashed border-amber-500 bg-amber-50 p-6">
      <p className="text-xs font-semibold uppercase tracking-widest text-amber-800">Test mode · no real payment</p>
      <h2 className="mt-1 font-serif text-2xl">{title ?? "Pay"} {money(amountMinor)}</h2>
      {description && <p className="mt-1 text-sm text-black/70">{description}</p>}
      <p className="mt-1 text-xs text-black/60">This simulates the gateway. Nothing is applied until the server verifies the signed payment event.</p>
      <div className="mt-4 flex flex-wrap gap-3">
        <button disabled={busy} onClick={() => pay("success")} className="rounded-full bg-ink px-6 py-2.5 text-white hover:bg-accent disabled:opacity-60">Simulate successful payment</button>
        <button disabled={busy} onClick={() => pay("failure")} className="rounded-full border border-ink px-6 py-2.5 hover:bg-ink hover:text-white disabled:opacity-60">Simulate failed payment</button>
        {onCancel && <button disabled={busy} onClick={onCancel} className="px-3 py-2.5 text-sm underline">Cancel</button>}
      </div>
      {err && <p role="alert" className="mt-3 text-sm text-red-700">{err}</p>}
    </div>
  );
}
