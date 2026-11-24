import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import ConsultStatus from "../../components/stylists/ConsultStatus.jsx";
import { stylistApi } from "../../services/api.js";
import { fmtDateTime } from "../../utils/money.js";

/** Shared by customers and stylists; the server decides which actions each side may take. */
export default function ConsultationDetail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const { data, isError } = useQuery({ queryKey: ["consultation", id], queryFn: () => stylistApi.consultation(id), retry: false });
  const status = data?.consultation.status;
  const chatOpen = status === "accepted";
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const last = useRef(0);
  const endRef = useRef(null);
  const loaded = !!data;

  // Poll for new messages while the chat is open; one final fetch after it closes so history is complete.
  useEffect(() => {
    if (!loaded) return undefined;
    let stop = false;
    async function pull() {
      try {
        const r = await stylistApi.messages(id, last.current);
        if (stop || r.messages.length === 0) return;
        last.current = r.messages[r.messages.length - 1].id;
        setMsgs((m) => [...m, ...r.messages.filter((x) => !m.some((y) => y.id === x.id))]);
      } catch { /* transient; the next poll retries */ }
    }
    pull();
    if (!chatOpen) return () => { stop = true; };
    const t = setInterval(pull, 4000);
    return () => { stop = true; clearInterval(t); };
  }, [id, chatOpen, loaded]);
  useEffect(() => { endRef.current?.scrollIntoView?.({ block: "end" }); }, [msgs]);

  if (isError) return <p className="p-10 text-center">Consultation not found. <Link className="underline" to="/consultations">My consultations</Link></p>;
  if (!data) return <p className="p-10 text-center" role="status">Loading…</p>;
  const c = data.consultation;
  const isStylist = data.role === "stylist";
  const other = isStylist ? c.customer.name : c.stylist.name;

  async function act(action, confirmText) {
    if (confirmText && !window.confirm(confirmText)) return;
    setErr(""); setBusy(true);
    try {
      await stylistApi.act(id, action);
      ["consultation", "consultations", "wallet", "wallet-tx", "stylist-earnings"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  async function send(e) {
    e.preventDefault();
    if (!text.trim()) return;
    setErr("");
    try {
      const r = await stylistApi.send(id, text.trim());
      last.current = Math.max(last.current, r.message.id);
      setMsgs((m) => (m.some((x) => x.id === r.message.id) ? m : [...m, r.message]));
      setText("");
    } catch (x) { setErr(x.message); }
  }

  const mineType = isStylist ? "stylist" : "customer";
  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <Link to={isStylist ? "/stylist" : "/consultations"} className="text-sm underline">← Back</Link>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <h1 className="font-serif text-3xl">Session with {other}</h1><ConsultStatus status={c.status} />
      </div>
      <p className="mt-1 text-sm text-black/60">{fmtDateTime(c.scheduled_start)} – {new Date(c.scheduled_end).toLocaleTimeString([], { timeStyle: "short" })} · {c.credit_cost} Super Credits{c.refunded_credits > 0 && ` · ${c.refunded_credits} refunded`}</p>
      {c.customer_notes && <p className="mt-3 rounded-xl bg-sand p-3 text-sm"><strong>Request:</strong> {c.customer_notes}</p>}

      <div className="mt-4 flex flex-wrap gap-3">
        {isStylist && c.status === "requested" && (
          <>
            <button disabled={busy} onClick={() => act("accept")} className="rounded-full bg-ink px-5 py-2 text-sm text-white hover:bg-accent">Accept</button>
            <button disabled={busy} onClick={() => act("decline", "Decline this request? The customer's credits are returned in full.")} className="rounded-full border border-ink px-5 py-2 text-sm">Decline</button>
          </>
        )}
        {isStylist && c.status === "accepted" && <button disabled={busy} onClick={() => act("complete")} className="rounded-full bg-ink px-5 py-2 text-sm text-white hover:bg-accent">Mark completed</button>}
        {["requested", "accepted"].includes(c.status) && (
          <button disabled={busy} onClick={() => act("cancel", isStylist ? "Cancel this session? The customer is refunded in full." : "Cancel this consultation? Late cancellations are only partly refunded.")} className="px-3 py-2 text-sm underline">Cancel session</button>
        )}
      </div>
      {err && <p role="alert" className="mt-3 text-sm text-red-700">{err}</p>}

      <section aria-label="Chat" className="mt-8">
        <h2 className="font-serif text-xl">Chat</h2>
        <div role="log" aria-live="polite" className="mt-3 min-h-[200px] space-y-3 rounded-2xl border border-black/10 p-4">
          {msgs.length === 0 && <p className="text-sm text-black/60">{c.status === "requested" ? "The chat opens once the stylist accepts." : chatOpen ? "No messages yet - say hello!" : "No messages."}</p>}
          {msgs.map((m) => (
            <div key={m.id} className={`flex ${m.sender_type === mineType ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${m.sender_type === mineType ? "bg-ink text-white" : "bg-sand"}`}>
                <p className="whitespace-pre-wrap break-words">{m.text}</p>
                <p className="mt-1 text-[10px] opacity-60">{m.sender_type === mineType ? "You" : other} · {new Date(m.created_at).toLocaleTimeString([], { timeStyle: "short" })}</p>
              </div>
            </div>
          ))}
          <div ref={endRef} />
        </div>
        {chatOpen ? (
          <form onSubmit={send} className="mt-3 flex gap-2">
            <label htmlFor="msg" className="sr-only">Message</label>
            <input id="msg" value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} placeholder="Type a message…" className="flex-1 rounded-full border border-black/20 px-4 py-2 text-sm" />
            <button disabled={!text.trim()} className="rounded-full bg-ink px-5 py-2 text-sm text-white hover:bg-accent disabled:opacity-50">Send</button>
          </form>
        ) : <p className="mt-2 text-xs text-black/60">The chat is read-only when a consultation is not confirmed.</p>}
      </section>
    </div>
  );
}
