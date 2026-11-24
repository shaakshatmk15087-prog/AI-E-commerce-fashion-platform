import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "../../services/api.js";
import { money, statusLabel } from "../../utils/money.js";
import { StatusBadge } from "../customer/Orders.jsx";

const NEXT = { confirmed: "processing", processing: "shipped", shipped: "out_for_delivery", out_for_delivery: "delivered" };
const REFUNDABLE = ["confirmed", "processing", "shipped", "out_for_delivery", "delivered", "cancelled"];

function RefundForm({ order, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [restock, setRestock] = useState("default");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      await adminApi.refund(order.id, { reason, restock: restock === "default" ? null : restock === "yes" });
      onDone();
    } catch (x) { setErr(x.details ? Object.values(x.details).flat().join(" ") : x.message); } finally { setBusy(false); }
  }

  return (
    <form onSubmit={submit} aria-label={`Refund order ${order.order_number}`} className="mt-2 w-full space-y-2 rounded-xl border border-red-200 bg-red-50 p-3 text-left text-sm">
      <p><strong>Refund {money(order.total_minor)}</strong> to the customer for order {order.order_number}. This can't be undone.</p>
      <div><label htmlFor={`r-${order.id}`} className="mb-1 block font-medium">Reason (required)</label>
        <input id={`r-${order.id}`} required minLength={3} maxLength={255} value={reason} onChange={(e) => setReason(e.target.value)} className="w-full rounded-lg border border-black/20 px-3 py-1.5" /></div>
      <div><label htmlFor={`s-${order.id}`} className="mb-1 block font-medium">Return items to stock?</label>
        <select id={`s-${order.id}`} value={restock} onChange={(e) => setRestock(e.target.value)} className="rounded-lg border border-black/20 px-2 py-1.5">
          <option value="default">Automatic (yes if not yet shipped)</option><option value="yes">Yes</option><option value="no">No</option></select></div>
      {err && <p role="alert" className="text-red-700">{err}</p>}
      <div className="flex gap-3">
        <button disabled={busy} className="rounded-full bg-red-700 px-4 py-1.5 text-white disabled:opacity-60">{busy ? "Refunding…" : "Confirm refund"}</button>
        <button type="button" onClick={onClose} className="underline">Cancel</button>
      </div>
    </form>
  );
}

export default function AdminOrders() {
  const qc = useQueryClient();
  const [refunding, setRefunding] = useState(null);
  const { data } = useQuery({ queryKey: ["admin-orders"], queryFn: adminApi.orders });
  const advance = useMutation({
    mutationFn: ({ id, to }) => adminApi.setStatus(id, to),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-orders"] }),
  });
  const done = () => { setRefunding(null); ["admin-orders", "admin-refunds", "admin-dashboard", "admin-audit"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); };

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="font-serif text-3xl">Orders</h1>
      {advance.error && <p role="alert" className="mt-3 text-sm text-red-700">{advance.error.message}</p>}
      <div className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <caption className="sr-only">Orders, newest first</caption>
          <thead><tr className="border-b border-black/20"><th className="py-2">Order</th><th>Date</th><th>Items</th><th>Total</th><th>Payment</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>
            {data?.orders.map((o) => (
              <tr key={o.id} className="border-b border-black/10 align-top">
                <td className="py-2">{o.order_number}</td><td>{new Date(o.created_at).toLocaleDateString()}</td><td>{o.item_count}</td>
                <td>{money(o.total_minor)}</td><td>{statusLabel(o.payment_status)}</td><td><StatusBadge s={o.order_status} /></td>
                <td className="text-right">
                  <div className="flex flex-col items-end gap-1">
                    {NEXT[o.order_status] && o.payment_status === "paid" && (
                      <button className="underline" disabled={advance.isPending} onClick={() => advance.mutate({ id: o.id, to: NEXT[o.order_status] })}>Mark {statusLabel(NEXT[o.order_status]).toLowerCase()}</button>)}
                    {o.payment_status === "paid" && REFUNDABLE.includes(o.order_status) && <button className="text-red-700 underline" onClick={() => setRefunding(refunding === o.id ? null : o.id)}>Refund</button>}
                  </div>
                  {refunding === o.id && <RefundForm order={o} onClose={() => setRefunding(null)} onDone={done} />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data?.orders.length === 0 && <p className="mt-4">No orders yet.</p>}
      </div>
    </div>
  );
}
