import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { shopApi } from "../../services/api.js";
import { money } from "../../utils/money.js";
import { Totals } from "./Cart.jsx";
import { PaymentPanel } from "./Checkout.jsx";
import { StatusBadge } from "./Orders.jsx";

const STEPS = ["confirmed", "processing", "shipped", "out_for_delivery", "delivered"];

export default function OrderDetail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery({ queryKey: ["order", id], queryFn: () => shopApi.order(id), retry: false });
  const [paying, setPaying] = useState(false);
  const [err, setErr] = useState("");

  if (isLoading) return <p className="p-10 text-center" role="status">Loading…</p>;
  if (isError) return <p className="p-10 text-center">Order not found. <Link className="underline" to="/orders">My orders</Link></p>;
  const o = data.order;
  const refresh = () => {
    for (const key of ["order", "orders", "cart", "products"]) qc.invalidateQueries({ queryKey: [key] });
  };
  const stepIdx = STEPS.indexOf(o.order_status);

  async function cancel() {
    if (!window.confirm("Cancel this order?")) return;
    try { await shopApi.cancelOrder(o.id); refresh(); } catch (x) { setErr(x.message); }
  }
  async function retry() {
    try { await shopApi.payRetry(o.id); setPaying(true); } catch (x) { setErr(x.message); }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <Link to="/orders" className="text-sm underline">← My orders</Link>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <h1 className="font-serif text-3xl">{o.order_number}</h1><StatusBadge s={o.order_status} />
      </div>
      <p className="text-sm text-black/60">Placed {new Date(o.created_at).toLocaleString()} · Payment: {o.payment_status}</p>

      {stepIdx >= 0 && (
        <ol aria-label="Delivery progress" className="my-6 grid grid-cols-5 gap-1 text-center text-xs">
          {STEPS.map((s, i) => (
            <li key={s} className={i <= stepIdx ? "font-semibold text-accent" : "text-black/60"}>
              <div className={`mb-1 h-1.5 rounded ${i <= stepIdx ? "bg-accent" : "bg-black/10"}`} />
              {s.replace(/_/g, " ")}{i === stepIdx && <span className="sr-only"> (current)</span>}
            </li>
          ))}
        </ol>
      )}

      {o.order_status === "pending_payment" && (
        <div className="my-6">
          {paying ? <PaymentPanel order={o} onDone={() => { setPaying(false); refresh(); }} /> : (
            <div className="flex flex-wrap items-center gap-3 rounded-xl bg-amber-50 p-4 text-sm">
              <span>Payment is pending. Stock is held for a limited time.</span>
              <button onClick={retry} className="rounded-full bg-ink px-4 py-1.5 text-white">Pay now</button>
              <button onClick={cancel} className="underline">Cancel order</button>
            </div>
          )}
        </div>
      )}
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}

      <ul className="mt-4 divide-y divide-black/10">
        {o.items.map((i) => (
          <li key={i.id} className="flex gap-4 py-3">
            {i.image && <img src={i.image} alt={i.name} className="h-20 w-16 rounded object-cover" />}
            <div className="flex-1">
              <Link className="font-medium underline" to={`/products/${i.product_id}`}>{i.name}</Link>
              <p className="text-sm text-black/60">{[i.color, i.size].filter(Boolean).join(" · ")} · Qty {i.quantity}</p>
            </div>
            <span>{money(i.line_total_minor)}</span>
          </li>
        ))}
      </ul>
      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <div className="text-sm"><h2 className="mb-1 font-semibold">Delivery address</h2>
          {o.address.recipient_name}<br />{o.address.address_line_1}{o.address.address_line_2 && `, ${o.address.address_line_2}`}<br />{o.address.city}, {o.address.state} {o.address.postal_code}</div>
        <Totals t={o} />
      </div>
    </div>
  );
}
