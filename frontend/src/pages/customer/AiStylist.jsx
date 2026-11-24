import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router-dom";
import ProductCard from "../../components/products/ProductCard.jsx";
import { aiApi } from "../../services/api.js";

const PROMPTS = [
  "Suggest an outfit for a college cultural event",
  "I need a formal outfit under ₹2,000",
  "Suggest a casual outfit for a weekend trip",
  "Find shoes for a formal interview",
];
const MAX = 500;

function ModeBadge({ m }) {
  return m.ai_generated ? (
    <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[11px] font-medium text-accent">✦ AI-generated</span>
  ) : (
    <span className="rounded-full bg-black/10 px-2 py-0.5 text-[11px] font-medium" title="The AI service was unavailable, so these suggestions come from our rule-based matcher.">
      Rule-based suggestions
    </span>
  );
}

function Bubble({ m }) {
  const mine = m.sender_type === "user";
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[92%] rounded-2xl px-4 py-3 text-sm sm:max-w-[85%] ${mine ? "bg-ink text-white" : "bg-sand"}`}>
        {!mine && <div className="mb-1"><ModeBadge m={m} /></div>}
        {/* Rendered as plain text (React escapes it): never as HTML. */}
        <p className="whitespace-pre-wrap break-words">{m.text}</p>
        {m.products?.length > 0 && (
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {m.products.map((p) => <ProductCard key={p.id} p={p} reason={p.reason} />)}
          </div>
        )}
      </div>
    </div>
  );
}

export default function AiStylist() {
  const qc = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const [remaining, setRemaining] = useState(null);
  const [credits, setCredits] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  const endRef = useRef(null);
  const startedWith = useRef(null);

  const { data: sessions } = useQuery({ queryKey: ["ai-sessions"], queryFn: aiApi.sessions });

  useEffect(() => { endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" }); }, [messages, pending]);

  async function send(text, { retry = false } = {}) {
    const msg = text.trim();
    if (!msg || pending) return;
    setError(null);
    if (!retry) {
      setMessages((ms) => [...ms, { id: `tmp-${Date.now()}`, sender_type: "user", text: msg }]);
      setInput("");
    }
    setPending(true);
    try {
      const r = await aiApi.chat(msg, sessionId);
      setSessionId(r.session_id);
      setRemaining(r.remaining_today);
      setCredits(r.credits);
      qc.invalidateQueries({ queryKey: ["wallet"] });
      setMessages((ms) => [...ms, r.message]);
      qc.invalidateQueries({ queryKey: ["ai-sessions"] });
    } catch (e) {
      const detail = e.details?.message?.[0];
      setError({ text: detail || e.message || "Something went wrong.", retry: ![400, 402, 429].includes(e.status) ? msg : null, wallet: e.status === 402 });
    } finally { setPending(false); }
  }

  // Prompt handed over from the home page (runs once even under StrictMode).
  useEffect(() => {
    const p = location.state?.prompt;
    if (p && startedWith.current !== p) {
      startedWith.current = p;
      navigate(location.pathname, { replace: true, state: null }); // consume it so a reload doesn't re-send
      send(p);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function open(id) {
    setError(null); setShowHistory(false);
    try {
      const r = await aiApi.session(id);
      setSessionId(id); setMessages(r.messages);
    } catch (e) { setError({ text: e.message, retry: null }); }
  }

  function newChat() { setSessionId(null); setMessages([]); setError(null); setShowHistory(false); }

  async function remove(id) {
    if (!window.confirm("Delete this conversation?")) return;
    await aiApi.remove(id);
    if (id === sessionId) newChat();
    qc.invalidateQueries({ queryKey: ["ai-sessions"] });
  }

  const empty = messages.length === 0;

  return (
    <div className="mx-auto grid max-w-7xl gap-6 px-4 py-8 md:grid-cols-[240px_1fr]">
      <aside aria-label="Conversations" className={`${showHistory ? "block" : "hidden"} md:block`}>
        <button onClick={newChat} className="mb-3 w-full rounded-full bg-ink py-2 text-sm text-white hover:bg-accent">+ New chat</button>
        <ul className="space-y-1 text-sm">
          {sessions?.sessions.map((s) => (
            <li key={s.id} className={`flex items-center justify-between gap-1 rounded-lg px-2 py-1.5 ${s.id === sessionId ? "bg-sand font-medium" : "hover:bg-sand/60"}`}>
              <button className="min-w-0 flex-1 truncate text-left" onClick={() => open(s.id)}>{s.title || "Chat"}</button>
              <button aria-label={`Delete conversation ${s.title || ""}`} className="px-1 text-black/60 hover:text-red-700" onClick={() => remove(s.id)}>✕</button>
            </li>
          ))}
          {sessions?.sessions.length === 0 && <li className="px-2 text-black/60">No conversations yet.</li>}
        </ul>
      </aside>

      <section className="flex min-h-[70vh] flex-col">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h1 className="font-serif text-3xl">AI Stylist</h1>
            <p className="text-sm text-black/60">Suggestions are matched to products that are in stock right now. Prices and sizes always come from the shop.</p>
          </div>
          <button className="rounded-full border border-ink px-3 py-1.5 text-sm md:hidden" aria-expanded={showHistory} onClick={() => setShowHistory(!showHistory)}>History</button>
        </div>

        <div role="log" aria-live="polite" aria-label="Conversation" className="flex-1 space-y-4">
          {empty && !pending && (
            <div className="rounded-2xl border border-black/10 p-6">
              <p className="font-medium">What are you shopping for?</p>
              <p className="mt-1 text-sm text-black/60">Describe an occasion, a budget or a colour - or try one of these:</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {PROMPTS.map((p) => (
                  <button key={p} onClick={() => send(p)} className="rounded-full border border-black/20 px-3 py-1.5 text-left text-sm hover:border-ink">{p}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m) => <Bubble key={m.id} m={m} />)}
          {pending && <div className="flex"><div role="status" className="rounded-2xl bg-sand px-4 py-3 text-sm text-black/60">Your stylist is thinking…</div></div>}
          {error && (
            <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {error.text}{" "}
              {error.retry && <button className="underline" onClick={() => send(error.retry, { retry: true })}>Retry</button>}
              {error.wallet && <Link to="/wallet" className="underline">Top up in your wallet</Link>}
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="sticky bottom-0 mt-4 bg-white pt-2">
          <label htmlFor="chat-input" className="sr-only">Message your stylist</label>
          <div className="flex items-end gap-2">
            <textarea id="chat-input" rows={2} maxLength={MAX} value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
              placeholder="e.g. A formal outfit for an interview under ₹2,500"
              className="flex-1 resize-none rounded-xl border border-black/20 px-3 py-2 text-sm focus:border-accent" />
            <button disabled={pending || !input.trim()} className="rounded-full bg-ink px-5 py-2.5 text-sm text-white hover:bg-accent disabled:opacity-50">Send</button>
          </div>
          <p className="mt-1 flex justify-between text-xs text-black/60">
            <span>Enter to send · Shift+Enter for a new line</span>
            <span>{input.length}/{MAX}{remaining != null && ` · ${remaining} messages left today`}{credits && Object.keys(credits.charged).length > 0 && ` · used ${Object.entries(credits.charged).map(([k, v]) => `${v} ${k}`).join(" + ")} credits`}</span>
          </p>
        </form>
      </section>
    </div>
  );
}
