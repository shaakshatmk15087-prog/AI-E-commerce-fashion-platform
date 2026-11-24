import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";
import { useCartActions, useToggleWishlist, useWishlistIds } from "../../hooks/useShop.js";
import { shopApi } from "../../services/api.js";
import { money } from "../../utils/money.js";

export default function ProductDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { add } = useCartActions();
  const { ids } = useWishlistIds();
  const toggle = useToggleWishlist();
  const { data, isLoading, isError } = useQuery({ queryKey: ["product", id], queryFn: () => shopApi.product(id), retry: false });
  const [color, setColor] = useState(null);
  const [size, setSize] = useState(null);
  const [imgIdx, setImgIdx] = useState(0);
  const [msg, setMsg] = useState(null);

  if (isLoading) return <p className="p-10 text-center" role="status">Loading…</p>;
  if (isError) return <p className="p-10 text-center">Product not found. <Link className="underline" to="/shop">Back to shop</Link></p>;

  const p = data.product;
  const colors = [...new Set(p.variants.map((v) => v.color).filter(Boolean))];
  const sizes = [...new Set(p.variants.map((v) => v.size).filter(Boolean))];
  const find = (c, s) => p.variants.find((v) => (v.color || null) === (c || null) && (v.size || null) === (s || null));
  const chosenColor = color ?? (colors.length === 1 ? colors[0] : null);
  const chosenSize = size ?? (sizes.length === 1 ? sizes[0] : null);
  const variant = find(chosenColor, chosenSize);
  const onSale = p.effective_price_minor < p.price_minor;
  const saved = ids.has(p.id);
  const sizeAvailable = (s) => p.variants.some((v) => v.size === s && v.stock_quantity > 0 && (!chosenColor || v.color === chosenColor));
  const colorAvailable = (c) => p.variants.some((v) => v.color === c && v.stock_quantity > 0 && (!chosenSize || v.size === chosenSize));

  function onAdd() {
    if (!user) return navigate("/login", { state: { from: location } });
    if (!variant) return setMsg({ ok: false, text: "Please select " + [!chosenColor && colors.length && "a colour", !chosenSize && sizes.length && "a size"].filter(Boolean).join(" and ") + "." });
    add.mutate({ variantId: variant.id, qty: 1 }, {
      onSuccess: () => setMsg({ ok: true, text: "Added to your cart." }),
      onError: (e) => setMsg({ ok: false, text: e.message }),
    });
  }

  const pill = (on, disabled) =>
    `rounded-full border px-4 py-1.5 text-sm ${on ? "border-ink bg-ink text-white" : "border-black/20 hover:border-ink"} ${disabled ? "opacity-40 line-through" : ""}`;

  return (
    <div className="mx-auto grid max-w-6xl gap-10 px-4 py-10 md:grid-cols-2">
      <div>
        <div className="overflow-hidden rounded-2xl bg-sand">
          {p.images[imgIdx] && <img src={p.images[imgIdx].image_url} alt={p.images[imgIdx].alt_text || p.name} className="aspect-[3/4] w-full object-cover" />}
        </div>
        {p.images.length > 1 && (
          <div className="mt-3 flex gap-2">
            {p.images.map((im, i) => (
              <button key={im.id} onClick={() => setImgIdx(i)} aria-label={`Show image ${i + 1}`} className={`h-16 w-14 overflow-hidden rounded ${i === imgIdx ? "ring-2 ring-accent" : ""}`}>
                <img src={im.image_url} alt="" className="h-full w-full object-cover" />
              </button>
            ))}
          </div>
        )}
      </div>

      <div>
        <p className="text-xs uppercase tracking-widest text-black/60">{p.brand} · {p.category}</p>
        <h1 className="mt-1 font-serif text-3xl">{p.name}</h1>
        <p className="mt-3 text-xl">
          <span className={onSale ? "font-semibold text-accent" : ""}>{money(p.effective_price_minor)}</span>
          {onSale && <span className="ml-3 text-base text-black/60 line-through">{money(p.price_minor)}</span>}
        </p>
        <p className="mt-4 text-black/70">{p.description}</p>

        {colors.length > 0 && (
          <fieldset className="mt-6">
            <legend className="mb-2 text-sm font-medium">Colour{chosenColor && `: ${chosenColor}`}</legend>
            <div className="flex flex-wrap gap-2">
              {colors.map((c) => (
                <button key={c} type="button" aria-pressed={chosenColor === c} onClick={() => setColor(c)} className={pill(chosenColor === c, !colorAvailable(c))}>
                  {c}{!colorAvailable(c) && <span className="sr-only"> (unavailable)</span>}
                </button>
              ))}
            </div>
          </fieldset>
        )}
        {sizes.length > 0 && (
          <fieldset className="mt-5">
            <legend className="mb-2 text-sm font-medium">Size{chosenSize && `: ${chosenSize}`}</legend>
            <div className="flex flex-wrap gap-2">
              {sizes.map((s) => (
                <button key={s} type="button" aria-pressed={chosenSize === s} onClick={() => setSize(s)} className={pill(chosenSize === s, !sizeAvailable(s))}>
                  {s}{!sizeAvailable(s) && <span className="sr-only"> (unavailable)</span>}
                </button>
              ))}
            </div>
          </fieldset>
        )}

        <p className="mt-4 text-sm" role="status">
          {!p.in_stock ? "Out of stock" : variant ? (variant.stock_quantity > 0 ? (variant.stock_quantity <= 3 ? `Only ${variant.stock_quantity} left` : "In stock") : "This combination is out of stock") : ""}
        </p>

        <div className="mt-6 flex gap-3">
          <button onClick={onAdd} disabled={!p.in_stock || (variant && variant.stock_quantity === 0) || add.isPending}
            className="flex-1 rounded-full bg-ink py-3 text-white hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50">
            {add.isPending ? "Adding…" : "Add to cart"}
          </button>
          <button aria-pressed={saved} onClick={() => (user ? toggle.mutate({ id: p.id, on: saved }) : navigate("/login", { state: { from: location } }))}
            className="rounded-full border border-ink px-5 py-3 hover:bg-ink hover:text-white">{saved ? "♥ Saved" : "♡ Save"}</button>
        </div>
        {msg && <p role={msg.ok ? "status" : "alert"} className={`mt-3 text-sm ${msg.ok ? "text-green-800" : "text-red-700"}`}>{msg.text} {msg.ok && <Link to="/cart" className="underline">View cart</Link>}</p>}

        <dl className="mt-8 space-y-2 border-t border-black/10 pt-6 text-sm">
          {p.material && <div className="flex gap-2"><dt className="w-24 font-medium">Material</dt><dd>{p.material}</dd></div>}
          {p.care && <div className="flex gap-2"><dt className="w-24 font-medium">Care</dt><dd>{p.care}</dd></div>}
          <div className="flex gap-2"><dt className="w-24 font-medium">Returns</dt><dd>{p.return_eligible ? "Eligible for return" : "Not eligible for return"}</dd></div>
        </dl>
      </div>
    </div>
  );
}
