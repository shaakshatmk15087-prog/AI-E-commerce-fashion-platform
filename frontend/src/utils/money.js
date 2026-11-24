const fmt = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
export const money = (minor) => fmt.format(minor / 100);
export const fmtDateTime = (iso) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
export const statusLabel = (s) => s.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
