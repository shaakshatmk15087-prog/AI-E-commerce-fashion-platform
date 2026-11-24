import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { shopApi } from "../../services/api.js";
import { money, statusLabel } from "../../utils/money.js";

export function StatusBadge({ s }) {
  const cls = { confirmed: "bg-green-100 text-green-900", delivered: "bg-green-100 text-green-900", cancelled: "bg-red-100 text-red-900", pending_payment: "bg-amber-100 text-amber-900" }[s] || "bg-black/10";
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>{statusLabel(s)}</span>;
}

export default function Orders() {
  const { data, isLoading } = useQuery({ queryKey: ["orders"], queryFn: shopApi.orders });
  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <h1 className="font-serif text-3xl">My orders</h1>
      {isLoading && <p role="status" className="mt-6">Loading…</p>}
      {data?.orders.length === 0 && <p className="mt-6">No orders yet. <Link className="underline" to="/shop">Start shopping</Link></p>}
      <ul className="mt-6 divide-y divide-black/10">
        {data?.orders.map((o) => (
          <li key={o.id} className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div>
              <Link to={`/orders/${o.id}`} className="font-medium underline">{o.order_number}</Link>
              <p className="text-sm text-black/60">{new Date(o.created_at).toLocaleDateString()} · {o.item_count} item{o.item_count === 1 ? "" : "s"}</p>
            </div>
            <StatusBadge s={o.order_status} />
            <span className="font-medium">{money(o.total_minor)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
