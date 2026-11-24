import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import Field from "../../components/layout/Field.jsx";
import PaymentSimulator from "../../components/payments/PaymentSimulator.jsx";
import { useCart } from "../../hooks/useShop.js";
import { shopApi } from "../../services/api.js";
import { money } from "../../utils/money.js";
import { Totals } from "./Cart.jsx";

const EMPTY = { recipient_name: "", phone: "", address_line_1: "", address_line_2: "", city: "", state: "", postal_code: "", country: "India" };

function AddressForm({ onSaved }) {
  const [f, setF] = useState(EMPTY);
  const [errs, setErrs] = useState({});
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  async function submit(e) {
    e.preventDefault();
    setErrs({});
    try {
      const r = await shopApi.addressCreate({ ...f, address_line_2: f.address_line_2 || null });
      onSaved(r.address);
    } catch (x) { setErrs(Object.fromEntries(Object.entries(x.details || {}).map(([k, v]) => [k, [].concat(v).join(" ")]))); }
  }
  const F = (k, label, extra = {}) => <Field label={label} id={`a-${k}`} value={f[k] || ""} onChange={set(k)} error={errs[k]} {...extra} />;
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2" noValidate>
      {F("recipient_name", "Full name", { required: true, autoComplete: "name" })}
      {F("phone", "Phone", { required: true, autoComplete: "tel" })}
      <div className="sm:col-span-2">{F("address_line_1", "Address line 1", { required: true, autoComplete: "address-line1" })}</div>
      <div className="sm:col-span-2">{F("address_line_2", "Address line 2 (optional)", { autoComplete: "address-line2" })}</div>
      {F("city", "City", { required: true })}
      {F("state", "State", { required: true })}
      {F("postal_code", "PIN code", { required: true, autoComplete: "postal-code" })}
      <div className="flex items-end"><button className="rounded-full bg-ink px-6 py-2 text-white hover:bg-accent">Save address</button></div>
    </form>
  );
}

export function PaymentPanel({ order, onDone }) {
  return (
    <PaymentSimulator title="Pay" amountMinor={order.total_minor} orderId={order.id}
      description={`Order ${order.order_number}.`} onDone={(r, outcome) => onDone(r.order, outcome)} />
  );
}

export default function Checkout() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data: cart, isLoading } = useCart();
  const { data: addrs } = useQuery({ queryKey: ["addresses"], queryFn: shopApi.addresses });
  const [picked, setPicked] = useState(null);
  const [adding, setAdding] = useState(false);
  const [order, setOrder] = useState(null);
  const [payMsg, setPayMsg] = useState("");

  const addresses = addrs?.addresses || [];
  const selected = picked ?? addresses.find((a) => a.is_default)?.id ?? addresses[0]?.id;

  const place = useMutation({
    mutationFn: () => shopApi.checkout(selected),
    onSuccess: (r) => setOrder(r.order),
    onSettled: () => { qc.invalidateQueries({ queryKey: ["cart"] }); qc.invalidateQueries({ queryKey: ["products"] }); },
  });

  if (order) {
    return (
      <div className="mx-auto max-w-xl px-4 py-12">
        <PaymentPanel order={order} onDone={(o, outcome) => {
          qc.invalidateQueries({ queryKey: ["cart"] });
          if (outcome === "success") navigate(`/orders/${o.id}`, { replace: true });
          else setPayMsg("Payment failed. Your order is on hold — you can retry now or from My orders.");
        }} />
        {payMsg && <p role="alert" className="mt-4 text-sm text-red-700">{payMsg} <Link className="underline" to={`/orders/${order.id}`}>View order</Link></p>}
      </div>
    );
  }

  if (isLoading) return <p className="p-10 text-center" role="status">Loading…</p>;
  if (!cart || cart.items.length === 0) return <p className="p-16 text-center">Your cart is empty. <Link className="underline" to="/shop">Shop</Link></p>;

  return (
    <div className="mx-auto grid max-w-6xl gap-10 px-4 py-10 md:grid-cols-[1fr_320px]">
      <section>
        <h1 className="font-serif text-3xl">Checkout</h1>
        <h2 className="mb-3 mt-8 font-serif text-xl">Delivery address</h2>
        <div role="radiogroup" aria-label="Delivery address" className="space-y-2">
          {addresses.map((a) => (
            <label key={a.id} className={`flex cursor-pointer gap-3 rounded-xl border p-4 text-sm ${selected === a.id ? "border-ink" : "border-black/15"}`}>
              <input type="radio" name="addr" checked={selected === a.id} onChange={() => setPicked(a.id)} />
              <span><strong>{a.recipient_name}</strong> · {a.phone}<br />{a.address_line_1}{a.address_line_2 && `, ${a.address_line_2}`}, {a.city}, {a.state} {a.postal_code}</span>
            </label>
          ))}
        </div>
        {adding || addresses.length === 0 ? (
          <div className="mt-4"><AddressForm onSaved={(a) => { qc.invalidateQueries({ queryKey: ["addresses"] }); setPicked(a.id); setAdding(false); }} /></div>
        ) : <button onClick={() => setAdding(true)} className="mt-3 text-sm underline">+ Add a new address</button>}
      </section>
      <aside className="h-fit rounded-2xl bg-sand p-6">
        <h2 className="mb-4 font-serif text-xl">Summary</h2>
        <ul className="mb-4 space-y-1 text-sm">{cart.items.map((i) => <li key={i.id} className="flex justify-between gap-2"><span>{i.name} × {i.quantity}</span><span>{money(i.line_total_minor)}</span></li>)}</ul>
        <Totals t={cart.totals} />
        {place.error && (
          <div role="alert" className="mt-3 text-sm text-red-700">
            {place.error.message}{place.error.status === 409 && <> <Link className="underline" to="/cart">Review cart</Link></>}
          </div>
        )}
        <button disabled={!selected || place.isPending || cart.has_issues} onClick={() => place.mutate()}
          className="mt-5 w-full rounded-full bg-ink py-3 text-white hover:bg-accent disabled:opacity-50">
          {place.isPending ? "Placing order…" : "Place order & pay"}
        </button>
      </aside>
    </div>
  );
}
