import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { stylistApi } from "../../services/api.js";

export default function Stylists() {
  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ["stylists"], queryFn: stylistApi.list });
  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <h1 className="font-serif text-3xl">Consult a stylist</h1>
      <p className="mt-2 max-w-2xl text-black/70">Book a text consultation with a professional stylist. The exact cost in <strong>Super Credits</strong> is shown before you confirm.</p>
      {isLoading && <p role="status" className="mt-8">Loading…</p>}
      {isError && <p role="alert" className="mt-8">Could not load stylists. <button className="underline" onClick={() => refetch()}>Retry</button></p>}
      {data?.stylists.length === 0 && <p className="mt-8">No stylists are available right now. Please check back soon.</p>}
      <div className="mt-8 grid gap-5 md:grid-cols-2">
        {data?.stylists.map((s) => (
          <article key={s.id} className="rounded-2xl border border-black/10 p-6">
            <div className="flex items-start justify-between gap-3">
              <h2 className="font-serif text-2xl">{s.name}</h2>
              <p className="whitespace-nowrap rounded-full bg-amber-50 px-3 py-1 text-sm">{s.price_credits} Super Credits</p>
            </div>
            <p className="mt-2 text-sm text-black/70">{s.bio}</p>
            <ul className="mt-3 flex flex-wrap gap-2 text-xs" aria-label="Expertise">
              {s.expertise.map((e) => <li key={e} className="rounded-full bg-sand px-2.5 py-1">{e}</li>)}
            </ul>
            <p className="mt-3 text-sm text-black/60">Speaks {s.languages.join(", ") || "—"} · {s.next_slots} open slot{s.next_slots === 1 ? "" : "s"}</p>
            <Link to={`/stylists/${s.id}`} className="mt-4 inline-block rounded-full bg-ink px-5 py-2 text-sm text-white hover:bg-accent">View &amp; book</Link>
          </article>
        ))}
      </div>
    </div>
  );
}
