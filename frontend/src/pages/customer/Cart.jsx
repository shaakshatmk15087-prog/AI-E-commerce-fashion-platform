import { Link } from "react-router-dom";
import { useCart, useCartActions } from "../../hooks/useShop.js";
import { money } from "../../utils/money.js";

export function Totals({ t }) {
  return (
    <dl className="space-y-1 text-sm">
      <div className="flex justify-between"><dt>Subtotal</dt><dd>{money(t.subtotal_minor)}</dd></div>
      {t.discount_minor > 0 && <div className="flex justify-between"><dt>Discount</dt><dd>-{money(t.discount_minor)}</dd></div>}
      <div className="flex justify-between"><dt>Shipping</dt><dd>{t.shipping_minor ? money(t.shipping_minor) : "Free"}</dd></div>
      {t.tax_minor > 0 && <div className="flex justify-between"><dt>Tax</dt><dd>{money(t.tax_minor)}</dd></div>}
      <div className="flex justify-between border-t border-black/10 pt-2 text-base font-semibold"><dt>Total</dt><dd>{money(t.total_minor)}</dd></div>
    </dl>
  );
}

export default function Cart() {
  const { data: cart, isLoading } = useCart();
  const { set, remove } = useCartActions();
  const err = set.error || remove.error;

  if (isLoading) return <p className="p-10 text-center" role="status">Loading…</p>;
  if (!cart || cart.items.length === 0)
    return <div className="p-16 text-center"><h1 className="font-serif text-3xl">Your cart is empty</h1><Link to="/shop" className="mt-4 inline-block underline">Continue shopping</Link></div>;

  return (
    <div className="mx-auto grid max-w-6xl gap-10 px-4 py-10 md:grid-cols-[1fr_320px]">
      <section>
        <h1 className="font-serif text-3xl">Your cart</h1>
        {err && <p role="alert" className="mt-3 text-sm text-red-700">{err.message}</p>}
        <ul className="mt-6 divide-y divide-black/10">
          {cart.items.map((it) => (
            <li key={it.id} className="flex gap-4 py-4">
              <Link to={`/products/${it.product_id}`} className="h-28 w-22 shrink-0 overflow-hidden rounded-lg bg-sand">
                {it.image && <img src={it.image} alt={it.name} className="h-28 w-[84px] object-cover" />}
              </Link>
              <div className="flex-1">
                <h2 className="font-medium">{it.name}</h2>
                <p className="text-sm text-black/60">{[it.color, it.size].filter(Boolean).join(" · ")}</p>
                {!it.available && <p role="alert" className="text-sm text-red-700">{it.stock_quantity === 0 ? "Out of stock" : `Only ${it.stock_quantity} left`} — update or remove to check out.</p>}
                {it.price_changed && it.available && <p className="text-sm text-amber-700">Price has changed since you added this.</p>}
                <div className="mt-2 flex items-center gap-3 text-sm">
                  <label htmlFor={`q${it.id}`} className="sr-only">Quantity for {it.name}</label>
                  <select id={`q${it.id}`} value={it.quantity} onChange={(e) => set.mutate({ id: it.id, qty: Number(e.target.value) })}
                    className="rounded border border-black/20 px-2 py-1">
                    {Array.from({ length: Math.max(it.quantity, Math.min(10, it.stock_quantity)) }, (_, i) => i + 1).map((n) => <option key={n}>{n}</option>)}
                  </select>
                  <button onClick={() => remove.mutate(it.id)} className="underline">Remove</button>
                </div>
              </div>
              <p className="font-medium">{money(it.line_total_minor)}</p>
            </li>
          ))}
        </ul>
      </section>
      <aside className="h-fit rounded-2xl bg-sand p-6">
        <h2 className="mb-4 font-serif text-xl">Order summary</h2>
        <Totals t={cart.totals} />
        {cart.has_issues ? (
          <p className="mt-4 text-sm text-red-700">Resolve the unavailable items above to continue.</p>
        ) : (
          <Link to="/checkout" className="mt-5 block rounded-full bg-ink py-3 text-center text-white hover:bg-accent">Checkout</Link>
        )}
      </aside>
    </div>
  );
}
