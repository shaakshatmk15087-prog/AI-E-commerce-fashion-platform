const STYLES = {
  requested: ["Awaiting stylist", "bg-amber-100 text-amber-900"],
  accepted: ["Confirmed", "bg-green-100 text-green-900"],
  completed: ["Completed", "bg-black/10 text-black"],
  declined: ["Declined", "bg-red-100 text-red-900"],
  cancelled: ["Cancelled", "bg-red-100 text-red-900"],
  expired: ["Expired", "bg-black/10 text-black"],
};

/** Status is always spelled out in text, never colour alone. */
export default function ConsultStatus({ status }) {
  const [label, cls] = STYLES[status] || [status, "bg-black/10"];
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>{label}</span>;
}
