import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { notifyApi } from "../../services/api.js";

export default function NotificationBell() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  const { data } = useQuery({ queryKey: ["notifications"], queryFn: notifyApi.list, refetchInterval: 30000 });

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);

  const unread = data?.unread || 0;
  const refresh = () => qc.invalidateQueries({ queryKey: ["notifications"] });

  async function go(n) {
    setOpen(false);
    if (!n.is_read) { await notifyApi.markRead([n.id]).catch(() => {}); refresh(); }
    if (n.link) navigate(n.link);
  }

  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="true" className="relative px-2 py-1 text-sm hover:text-accent">
        <span aria-hidden="true">🔔</span><span className="sr-only">Notifications{unread ? `, ${unread} unread` : ""}</span>
        {unread > 0 && <span aria-hidden="true" className="absolute -right-1 -top-1 rounded-full bg-accent px-1.5 text-[10px] text-white">{unread}</span>}
      </button>
      {open && (
        <div role="region" aria-label="Notifications" className="absolute right-0 z-30 mt-2 w-80 max-w-[90vw] rounded-xl border border-black/10 bg-white p-2 shadow-lg">
          <div className="flex items-center justify-between px-2 py-1">
            <p className="text-sm font-medium">Notifications</p>
            {unread > 0 && <button className="text-xs underline" onClick={async () => { await notifyApi.markRead(); refresh(); }}>Mark all read</button>}
          </div>
          <ul className="max-h-80 overflow-auto">
            {data?.notifications.length === 0 && <li className="px-2 py-3 text-sm text-black/60">You're all caught up.</li>}
            {data?.notifications.map((n) => (
              <li key={n.id}>
                <button onClick={() => go(n)} className={`block w-full rounded-lg px-2 py-2 text-left text-sm hover:bg-sand ${n.is_read ? "text-black/60" : "font-medium"}`}>
                  {!n.is_read && <span className="mr-1 text-accent" aria-label="Unread">●</span>}{n.title}
                  {n.body && <span className="block text-xs font-normal text-black/60">{n.body}</span>}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
