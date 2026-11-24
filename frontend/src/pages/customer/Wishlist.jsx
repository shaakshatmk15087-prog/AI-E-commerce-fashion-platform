import { Link } from "react-router-dom";
import ProductCard from "../../components/products/ProductCard.jsx";
import { useWishlistIds } from "../../hooks/useShop.js";

export default function Wishlist() {
  const { products, isLoading } = useWishlistIds();
  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <h1 className="font-serif text-3xl">Wishlist</h1>
      {isLoading && <p role="status" className="mt-6">Loading…</p>}
      {products?.length === 0 && <p className="mt-6">Nothing saved yet. <Link className="underline" to="/shop">Browse the shop</Link></p>}
      <div className="mt-8 grid grid-cols-2 gap-x-4 gap-y-8 md:grid-cols-4">
        {products?.map((p) => <ProductCard key={p.id} p={p} />)}
      </div>
    </div>
  );
}
