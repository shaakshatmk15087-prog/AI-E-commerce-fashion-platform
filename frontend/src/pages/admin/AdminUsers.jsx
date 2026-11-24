import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "../../services/api.js";
import { fmtDateTime } from "../../utils/money.js";

export default function AdminUsers() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [active, setActive] = useState("");
  const [page, setPage] = useState(1);
  const params = { q, role, active, page, per_page: 15 };
  const { data, isLoading } = useQuery({ queryKey: ["admin-users-list", params], queryFn: () => adminApi.users(params), placeholderData: (p) => p });
  const toggle = useMutation({
    mutationFn: ({ id, on }) => adminApi.setUserActive(id, on),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-users-list"] }); qc.invalidateQueries({ queryKey: ["admin-audit"] }); },
  });
  const pages = data ? Math.max(1, Math.ceil(data.total / data.per_page)) : 1;
  const reset = (fn) => (e) => { fn(e.target.value); setPage(1); };

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="font-serif text-3xl">Users</h1>
      <form role="search" onSubmit={(e) => e.preventDefault()} className="mt-4 flex flex-wrap items-end gap-3">
        <div><label htmlFor="uq" className="mb-1 block text-sm font-medium">Search name or email</label>
          <input id="uq" value={q} onChange={reset(setQ)} className="rounded-lg border border-black/20 px-3 py-2" /></div>
        <div><label htmlFor="ur" className="mb-1 block text-sm font-medium">Role</label>
          <select id="ur" value={role} onChange={reset(setRole)} className="rounded-lg border border-black/20 px-3 py-2"><option value="">All</option><option>customer</option><option>stylist</option><option>admin</option></select></div>
        <div><label htmlFor="ua" className="mb-1 block text-sm font-medium">Status</label>
          <select id="ua" value={active} onChange={reset(setActive)} className="rounded-lg border border-black/20 px-3 py-2"><option value="">All</option><option value="true">Active</option><option value="false">Deactivated</option></select></div>
      </form>
      {toggle.error && <p role="alert" className="mt-3 text-sm text-red-700">{toggle.error.message}</p>}
      {isLoading && <p role="status" className="mt-4">Loading…</p>}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <caption className="sr-only">Users</caption>
          <thead><tr className="border-b border-black/20"><th className="py-2 pr-3">User</th><th className="pr-3">Role</th><th className="pr-3">Joined</th><th className="pr-3">Verified</th><th className="pr-3">Status</th><th><span className="sr-only">Action</span></th></tr></thead>
          <tbody>
            {data?.users.map((u) => (
              <tr key={u.id} className="border-b border-black/10">
                <td className="py-2 pr-3">{u.name}<span className="block text-xs text-black/60">{u.email}</span></td>
                <td className="pr-3">{u.role}</td><td className="pr-3">{fmtDateTime(u.created_at)}</td><td className="pr-3">{u.is_verified ? "Yes" : "No"}</td>
                <td className="pr-3"><span className={`rounded-full px-2 py-0.5 text-xs ${u.is_active ? "bg-green-100 text-green-900" : "bg-red-100 text-red-900"}`}>{u.is_active ? "Active" : "Deactivated"}</span></td>
                <td className="text-right">
                  <button disabled={toggle.isPending} className="underline" aria-label={`${u.is_active ? "Deactivate" : "Reactivate"} ${u.email}`}
                    onClick={() => (!u.is_active || window.confirm(`Deactivate ${u.email}? They are signed out immediately and can't log in.`)) && toggle.mutate({ id: u.id, on: !u.is_active })}>
                    {u.is_active ? "Deactivate" : "Reactivate"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data?.users.length === 0 && <p className="mt-3 text-sm text-black/60">No users match.</p>}
      </div>
      {pages > 1 && (
        <nav aria-label="Pagination" className="mt-4 flex items-center justify-center gap-4 text-sm">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="underline disabled:opacity-40">Previous</button>
          <span>Page {page} of {pages} ({data.total} users)</span>
          <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="underline disabled:opacity-40">Next</button>
        </nav>
      )}
    </div>
  );
}
