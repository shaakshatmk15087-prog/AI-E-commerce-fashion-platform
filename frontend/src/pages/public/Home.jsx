import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import ProductCard from "../../components/products/ProductCard.jsx";
import { useAuth } from "../../context/AuthContext.jsx";
import { aiApi } from "../../services/api.js";

export default function Home() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [prompt, setPrompt] = useState("");
  const { data: recs } = useQuery({ queryKey: ["recs", user?.id ?? null], queryFn: aiApi.recommendations });
  const ask = (e) => { e.preventDefault(); navigate("/ai-stylist", { state: prompt.trim() ? { prompt: prompt.trim() } : undefined }); };
  return (
    <>
      <section className="bg-sand">
        <div className="mx-auto max-w-7xl px-4 py-20 sm:py-28">
          <p className="mb-3 text-sm uppercase tracking-widest text-accent">Your personal AI fashion companion</p>
          <h1 className="max-w-3xl font-serif text-4xl leading-tight sm:text-6xl">Discover your style. Find the right outfit. Shop with confidence.</h1>
          <p className="mt-6 max-w-xl text-lg text-black/70">Tell our AI stylist what you need — a college event, an interview, a weekend trip — and get real, in-stock suggestions.</p>
          <form onSubmit={ask} className="mt-8 flex max-w-xl gap-2">
            <label htmlFor="home-ask" className="sr-only">Ask the AI stylist</label>
            <input id="home-ask" value={prompt} maxLength={500} onChange={(e) => setPrompt(e.target.value)}
              placeholder="Try: an outfit for a college event under ₹3,000"
              className="flex-1 rounded-full border border-black/20 bg-white px-5 py-3" />
            <button className="rounded-full bg-ink px-6 py-3 text-white hover:bg-accent">Ask</button>
          </form>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link to="/ai-stylist" className="rounded-full bg-ink px-6 py-3 text-white hover:bg-accent">Talk to the AI Stylist</Link>
            <Link to="/shop" className="rounded-full border border-ink px-6 py-3 hover:bg-ink hover:text-white">Browse the shop</Link>
          </div>
        </div>
      </section>
      <section className="mx-auto grid max-w-7xl gap-6 px-4 py-16 md:grid-cols-3">
        {[
          ["Conversational discovery", "Describe the occasion and budget in your own words."],
          ["Human stylists", "Book a text consultation with a professional using credits."],
          ["Transparent credits", "Daily and Super Credits are always shown separately, with clear costs."],
        ].map(([t, d]) => (
          <div key={t} className="rounded-2xl border border-black/10 p-6">
            <h2 className="font-serif text-xl">{t}</h2>
            <p className="mt-2 text-black/70">{d}</p>
          </div>
        ))}
      </section>
      {recs?.products.length > 0 && (
        <section className="mx-auto max-w-7xl px-4 pb-20">
          <h2 className="mb-6 font-serif text-2xl">{recs.personalized ? "Picked for you" : "Trending now"}</h2>
          <div className="grid grid-cols-2 gap-x-4 gap-y-8 md:grid-cols-4">
            {recs.products.slice(0, 4).map((p) => <ProductCard key={p.id} p={p} reason={recs.personalized ? p.reason : null} />)}
          </div>
        </section>
      )}
    </>
  );
}
