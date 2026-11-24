import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { adminApi, downloadCsv } from "../../services/api.js";
import { fmtDateTime, money, statusLabel } from "../../utils/money.js";

const TABS = [["audit", "Audit log"], ["refunds", "Refunds"], ["subscriptions", "Subscriptions"], ["consultations", "Consultations"], ["downloads", "CSV downloads"]];
const REPORTS = [["orders", "Orders"], ["payments", "Payments"], ["credits", "Credit ledger"], ["audit", "Audit log"]];

function Audit() {
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);
  const { data } = useQuery({ queryKey: ["admin-audit", action, page], queryFn: () => adminApi.audit({ action, page, per_page: 20 }), placeholderData: (p) => p });
  const pages = data ? Math.max(1, Math.ceil(data.total / data.per_page)) : 1;
  return (
    <div>
      <label className="text-sm">Action{" "}
        <select value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} className="rounded-lg border border-black/20 px-2 py-1">
          <option value="">All</option>{data?.actions.map((a) => <option key={a}>{a}</option>)}
        </select>
      </label>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-xs">
          <caption className="sr-only">Audit log, newest first</caption>
          <thead><tr className="border-b border-black/20"><th className="py-1 pr-2">When</th><th className="pr-2">Actor</th><th className="pr-2">Action</th><th className="pr-2">Target</th><th>Details</th></tr></thead>
          <tbody>{data?.logs.map((l) => (
            <tr key={l.id} className="border-b border-black/10 align-top"><td className="py-1 pr-2 whitespace-nowrap">{fmtDateTime(l.created_at)}</td><td className="pr-2">{l.actor_id ?? "system"}</td>
              <td className="pr-2">{l.action}</td><td className="pr-2">{l.target_type} {l.target_id}</td><td className="break-all text-black/60">{JSON.stringify(l.details)}</td></tr>))}</tbody>
        </table>
        {data?.logs.length === 0 && <p className="mt-2 text-sm text-black/60">Nothing logged.</p>}
      </div>
      {pages > 1 && (
        <nav aria-label="Pagination" className="mt-3 flex items-center justify-center gap-4 text-sm">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="underline disabled:opacity-40">Previous</button>
          <span>Page {page} of {pages}</span>
          <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="underline disabled:opacity-40">Next</button>
        </nav>
      )}
    </div>
  );
}

function SimpleTable({ queryKey, fetcher, pick, columns, empty }) {
  const { data } = useQuery({ queryKey: [queryKey], queryFn: fetcher });
  const rows = data ? pick(data) : [];
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-left text-sm">
        <thead><tr className="border-b border-black/20">{columns.map((c) => <th key={c.h} className="py-2 pr-3">{c.h}</th>)}</tr></thead>
        <tbody>{rows.map((r) => <tr key={r.id} className="border-b border-black/10">{columns.map((c) => <td key={c.h} className="py-1.5 pr-3">{c.v(r)}</td>)}</tr>)}</tbody>
      </table>
      {data && rows.length === 0 && <p className="mt-2 text-sm text-black/60">{empty}</p>}
    </div>
  );
}

function Downloads() {
  const [days, setDays] = useState(30);
  const [err, setErr] = useState("");
  return (
    <div>
      <label className="text-sm">Period{" "}
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-lg border border-black/20 px-2 py-1">{[7, 30, 90, 365].map((n) => <option key={n} value={n}>Last {n} days</option>)}</select>
      </label>
      <ul className="mt-4 grid gap-3 sm:grid-cols-2">
        {REPORTS.map(([k, label]) => (
          <li key={k} className="flex items-center justify-between rounded-xl border border-black/10 p-4">
            <span>{label}</span>
            <button className="rounded-full border border-ink px-4 py-1.5 text-sm hover:bg-ink hover:text-white" onClick={() => downloadCsv(k, days).catch((e) => setErr(e.message))}>Download CSV</button>
          </li>
        ))}
      </ul>
      {err && <p role="alert" className="mt-3 text-sm text-red-700">{err}</p>}
      <p className="mt-3 text-xs text-black/60">Exports contain personal data. Handle them under your data-protection policy. Spreadsheet formulas in values are neutralised.</p>
    </div>
  );
}

export default function AdminReports() {
  const [tab, setTab] = useState("audit");
  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="font-serif text-3xl">Reports &amp; audit</h1>
      <div role="tablist" aria-label="Reports" className="mt-4 flex flex-wrap gap-2 border-b border-black/10">
        {TABS.map(([k, label]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`-mb-px border-b-2 px-4 py-2 text-sm ${tab === k ? "border-ink font-medium" : "border-transparent text-black/60"}`}>{label}</button>)}
      </div>
      <div role="tabpanel" className="mt-5">
        {tab === "audit" && <Audit />}
        {tab === "refunds" && <SimpleTable queryKey="admin-refunds" fetcher={adminApi.refunds} pick={(d) => d.refunds} empty="No refunds yet."
          columns={[{ h: "Date", v: (r) => fmtDateTime(r.created_at) }, { h: "Order", v: (r) => `#${r.order_id}` }, { h: "Amount", v: (r) => money(r.amount_minor) }, { h: "Reason", v: (r) => r.reason }, { h: "Restocked", v: (r) => (r.restocked ? "Yes" : "No") }]} />}
        {tab === "subscriptions" && <SimpleTable queryKey="admin-subscriptions" fetcher={adminApi.subscriptions} pick={(d) => d.subscriptions} empty="No subscriptions yet."
          columns={[{ h: "Customer", v: (r) => r.user.email }, { h: "Plan", v: (r) => r.plan.name }, { h: "Status", v: (r) => statusLabel(r.status) }, { h: "Period ends", v: (r) => (r.current_period_end ? fmtDateTime(r.current_period_end) : "—") }]} />}
        {tab === "consultations" && <SimpleTable queryKey="admin-consultations" fetcher={() => adminApi.consultationsAll()} pick={(d) => d.consultations} empty="No consultations yet."
          columns={[{ h: "When", v: (r) => fmtDateTime(r.scheduled_start) }, { h: "Customer", v: (r) => r.customer.name }, { h: "Stylist", v: (r) => r.stylist.name }, { h: "Status", v: (r) => statusLabel(r.status) }, { h: "Credits", v: (r) => `${r.credit_cost}${r.refunded_credits ? ` (−${r.refunded_credits})` : ""}` }]} />}
        {tab === "downloads" && <Downloads />}
      </div>
    </div>
  );
}
