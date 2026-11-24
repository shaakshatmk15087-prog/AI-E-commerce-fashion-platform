import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import ProductCard from "../../components/products/ProductCard.jsx";
import { shopApi } from "../../services/api.js";

const SORTS = [["newest", "Newest"], ["price_asc", "Price: low to high"], ["price_desc", "Price: high to low"]];

function Check({ name, values, params, setParam }) {
  const sel = params.getAll(name);
  return (
    <fieldset className="mb-5">
      <legend className="mb-2 text-sm font-medium capitalize">{name}</legend>
      <div className="flex flex-wrap gap-2">
        {values.map((v) => {
          const on = sel.includes(v);
          return (
            <label key={v} className={`cursor-pointer rounded-full border px-3 py-1 text-sm ${on ? "border-ink bg-ink text-white" : "border-black/20 hover:border-ink"}`}>
              <input type="checkbox" className="sr-only" checked={on}
                onChange={() => setParam(name, on ? sel.filter((x) => x !== v) : [...sel, v])} />
              {v}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

export default function Shop() {
  const [params, setParams] = useSearchParams();
  const [showFilters, setShowFilters] = useState(false);
  const page = Number(params.get("page") || 1);

  const setParam = (k, v) => {
    const next = new URLSearchParams(params);
    next.delete(k);
    [].concat(v).forEach((x) => x !== "" && x != null && next.append(k, x));
    next.delete("page");
    setParams(next);
  };

  const { data: cats } = useQuery({ queryKey: ["categories"], queryFn: shopApi.categories });
  const { data: facets } = useQuery({ queryKey: ["filters"], queryFn: shopApi.filters });

  const apiParams = {
    q: params.get("q"), category_id: params.get("category_id"), sort: params.get("sort"), page,
    size: params.getAll("size"), color: params.getAll("color"), brand: params.getAll("brand"),
    min_price: params.get("min") ? Math.round(Number(params.get("min")) * 100) : "",
    max_price: params.get("max") ? Math.round(Number(params.get("max")) * 100) : "",
  };
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["products", apiParams], queryFn: () => shopApi.products(apiParams), placeholderData: (prev) => prev,
  });
  const pages = data ? Math.max(1, Math.ceil(data.total / data.per_page)) : 1;

  return (
    <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 md:grid-cols-[240px_1fr]">
      <button type="button" aria-expanded={showFilters} aria-controls="filters" onClick={() => setShowFilters(!showFilters)}
        className="rounded-full border border-ink px-4 py-2 text-sm md:hidden">
        {showFilters ? "Hide filters" : "Filters"}
      </button>
      <aside id="filters" aria-label="Filters" className={`${showFilters ? "block" : "hidden"} md:block md:row-span-2`}>
        <form role="search" onSubmit={(e) => { e.preventDefault(); setParam("q", new FormData(e.currentTarget).get("q")); }} className="mb-5">
          <label htmlFor="q" className="mb-1 block text-sm font-medium">Search</label>
          <input id="q" name="q" key={params.get("q") || ""} defaultValue={params.get("q") || ""} placeholder="Shirt, dress, sneakers…"
            className="w-full rounded-lg border border-black/20 px-3 py-2" />
        </form>
        <div className="mb-5">
          <label htmlFor="cat" className="mb-1 block text-sm font-medium">Category</label>
          <select id="cat" value={params.get("category_id") || ""} onChange={(e) => setParam("category_id", e.target.value)}
            className="w-full rounded-lg border border-black/20 px-3 py-2">
            <option value="">All</option>
            {cats?.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <fieldset className="mb-5">
          <legend className="mb-1 text-sm font-medium">Price (₹)</legend>
          <div className="flex gap-2">
            {["min", "max"].map((k) => (
              <input key={k + (params.get(k) || "")} aria-label={`${k} price`} type="number" min="0" placeholder={k}
                defaultValue={params.get(k) || ""} onBlur={(e) => e.target.value !== (params.get(k) || "") && setParam(k, e.target.value)}
                className="w-full rounded-lg border border-black/20 px-2 py-1.5 text-sm" />
            ))}
          </div>
        </fieldset>
        {facets && <>
          <Check name="size" values={facets.sizes} params={params} setParam={setParam} />
          <Check name="color" values={facets.colors} params={params} setParam={setParam} />
          <Check name="brand" values={facets.brands} params={params} setParam={setParam} />
        </>}
        <button onClick={() => setParams({})} className="text-sm underline">Clear filters</button>
      </aside>

      <section aria-live="polite">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <h1 className="font-serif text-3xl">Shop</h1>
          <div className="flex items-center gap-2 text-sm">
            <span>{data ? `${data.total} item${data.total === 1 ? "" : "s"}` : ""}</span>
            <label htmlFor="sort" className="sr-only">Sort by</label>
            <select id="sort" value={params.get("sort") || "newest"} onChange={(e) => setParam("sort", e.target.value)}
              className="rounded-lg border border-black/20 px-2 py-1.5">
              {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
        </div>
        {isLoading && <p role="status">Loading…</p>}
        {isError && <p role="alert">Could not load products. <button className="underline" onClick={() => refetch()}>Retry</button></p>}
        {data && data.products.length === 0 && <p>No products match your filters.</p>}
        <div className="grid grid-cols-2 gap-x-4 gap-y-8 lg:grid-cols-3">
          {data?.products.map((p) => <ProductCard key={p.id} p={p} />)}
        </div>
        {pages > 1 && (
          <nav aria-label="Pagination" className="mt-10 flex items-center justify-center gap-4 text-sm">
            <button disabled={page <= 1} onClick={() => setParams({ ...Object.fromEntries(params), page: page - 1 })} className="underline disabled:opacity-40">Previous</button>
            <span>Page {page} of {pages}</span>
            <button disabled={page >= pages} onClick={() => setParams({ ...Object.fromEntries(params), page: page + 1 })} className="underline disabled:opacity-40">Next</button>
          </nav>
        )}
      </section>
    </div>
  );
}
