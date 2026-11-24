import { NavLink, Outlet } from "react-router-dom";

const LINKS = [
  ["/admin", "Dashboard", true], ["/admin/orders", "Orders"], ["/admin/products", "Products"], ["/admin/catalogue", "Catalogue & stock"],
  ["/admin/users", "Users"], ["/admin/credits", "Credits & plans"], ["/admin/stylists", "Stylists & rewards"], ["/admin/reports", "Reports & audit"],
];

/** Shared frame for every admin page: one consistent, keyboard-friendly navigation. */
export default function AdminShell() {
  return (
    <div>
      <nav aria-label="Admin" className="border-b border-black/10 bg-sand">
        <ul className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-4 py-2 text-sm">
          {LINKS.map(([to, label, end]) => (
            <li key={to} className="shrink-0">
              <NavLink to={to} end={end} className={({ isActive }) => `block rounded-full px-3 py-1.5 ${isActive ? "bg-ink text-white" : "hover:bg-white"}`}>{label}</NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <Outlet />
    </div>
  );
}
