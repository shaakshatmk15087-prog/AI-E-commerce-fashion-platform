import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";
import { useToggleWishlist, useWishlistIds } from "../../hooks/useShop.js";
import { money } from "../../utils/money.js";

export default function ProductCard({ p, reason }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { ids } = useWishlistIds();
  const toggle = useToggleWishlist();
  const saved = ids.has(p.id);
  const onSale = p.effective_price_minor < p.price_minor;

  return (
    <article className="group relative">
      <Link to={`/products/${p.id}`} className="block overflow-hidden rounded-xl bg-sand">
        {p.image ? (
          <img src={p.image} alt={p.name} loading="lazy" className="aspect-[3/4] w-full object-cover transition-transform duration-300 group-hover:scale-105" />
        ) : <div className="aspect-[3/4]" />}
      </Link>
      <button
        aria-label={saved ? `Remove ${p.name} from wishlist` : `Save ${p.name} to wishlist`} aria-pressed={saved}
        onClick={() => (user ? toggle.mutate({ id: p.id, on: saved }) : navigate("/login"))}
        className="absolute right-2 top-2 rounded-full bg-white/90 px-2.5 py-1 text-lg leading-none shadow hover:bg-white">
        <span aria-hidden="true">{saved ? "♥" : "♡"}</span>
      </button>
      {!p.in_stock && <span className="absolute left-2 top-2 rounded bg-ink px-2 py-0.5 text-xs text-white">Out of stock</span>}
      <div className="mt-3">
        <p className="text-xs uppercase tracking-wide text-black/60">{p.brand}</p>
        <h3 className="text-sm font-medium"><Link to={`/products/${p.id}`}>{p.name}</Link></h3>
        <p className="mt-1 text-sm">
          <span className={onSale ? "font-semibold text-accent" : ""}>{money(p.effective_price_minor)}</span>
          {onSale && <span className="ml-2 text-black/60 line-through"><span className="sr-only">Was </span>{money(p.price_minor)}</span>}
        </p>
        {reason && <p className="mt-1 text-xs italic text-black/60">{reason}</p>}
      </div>
    </article>
  );
}
