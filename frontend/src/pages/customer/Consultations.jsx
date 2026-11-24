import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import ConsultStatus from "../../components/stylists/ConsultStatus.jsx";
import { stylistApi } from "../../services/api.js";
import { fmtDateTime } from "../../utils/money.js";

export default function Consultations() {
  const { data, isLoading } = useQuery({ queryKey: ["consultations", "customer"], queryFn: () => stylistApi.consultations() });
  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <h1 className="font-serif text-3xl">My consultations</h1>
      {isLoading && <p role="status" className="mt-6">Loading…</p>}
      {data?.consultations.length === 0 && <p className="mt-6">No consultations yet. <Link className="underline" to="/stylists">Find a stylist</Link></p>}
      <ul className="mt-6 divide-y divide-black/10">
        {data?.consultations.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div>
              <Link to={`/consultations/${c.id}`} className="font-medium underline">{c.stylist.name}</Link>
              <p className="text-sm text-black/60">{fmtDateTime(c.scheduled_start)} · {c.credit_cost} credits</p>
            </div>
            <ConsultStatus status={c.status} />
          </li>
        ))}
      </ul>
    </div>
  );
}
