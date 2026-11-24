import { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";
import { useCart } from "../../hooks/useShop.js";
import NotificationBell from "./NotificationBell.jsx";

const links = [
  ["/shop", "Shop"],
  ["/ai-stylist", "AI Stylist"],
  ["/stylists", "Consult a Stylist"],
  ["/rewards", "Rewards"],
];

const linkCls = ({ isActive }) =>
  `px-2 py-1 text-sm transition-colors hover:text-accent ${isActive ? "text-accent font-medium" : ""}`;

function CartLink({ count, className }) {
  return (
    <Link to="/cart" className={className}>
      Cart{count > 0 && <span className="ml-1 rounded-full bg-accent px-1.5 text-xs text-white" aria-label={`${count} items`}>{count}</span>}
    </Link>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const { data: cart } = useCart();
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const count = cart?.items.reduce((n, i) => n + i.quantity, 0) || 0;
  const close = () => setOpen(false);

  const onLogout = async () => { await logout(); close(); navigate("/"); };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 border-b border-black/10 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4">
          <Link to="/" className="font-serif text-xl tracking-wide">AI Fashion</Link>
          <nav aria-label="Main" className="hidden items-center gap-4 md:flex">
            {links.map(([to, label]) => <NavLink key={to} to={to} className={linkCls}>{label}</NavLink>)}
          </nav>
          <div className="hidden items-center gap-3 md:flex">
            {user ? (
              <>
                {user.role === "admin" && <Link to="/admin" className="text-sm hover:text-accent">Admin</Link>}
                {user.role === "stylist" && <Link to="/stylist" className="text-sm hover:text-accent">Stylist console</Link>}
                {user.role === "customer" && <Link to="/consultations" className="text-sm hover:text-accent">Consultations</Link>}
                {user.role !== "stylist" && (
                  <>
                    <Link to="/orders" className="text-sm hover:text-accent">Orders</Link>
                    <Link to="/wishlist" className="text-sm hover:text-accent">Wishlist</Link>
                    <Link to="/wallet" className="text-sm hover:text-accent">Wallet</Link>
                    <CartLink count={count} className="text-sm hover:text-accent" />
                  </>
                )}
                <NotificationBell />
                <Link to="/account" className="text-sm hover:text-accent">{user.name}</Link>
                <button onClick={onLogout} className="rounded-full border border-ink px-4 py-1.5 text-sm hover:bg-ink hover:text-white">Log out</button>
              </>
            ) : (
              <>
                <Link to="/login" className="text-sm hover:text-accent">Log in</Link>
                <Link to="/register" className="rounded-full bg-ink px-4 py-1.5 text-sm text-white hover:bg-accent">Sign up</Link>
              </>
            )}
          </div>
          <div className="flex items-center gap-1 md:hidden">
            {user && <NotificationBell />}
            {user && user.role !== "stylist" && <CartLink count={count} className="px-2 py-1 text-sm" />}
            <button className="rounded p-2" aria-label="Toggle menu" aria-expanded={open} onClick={() => setOpen(!open)}>
              <span aria-hidden="true" className="text-2xl leading-none">{open ? "✕" : "☰"}</span>
            </button>
          </div>
        </div>
        {open && (
          <nav aria-label="Mobile" className="flex flex-col gap-1 border-t border-black/10 px-4 py-3 md:hidden">
            {links.map(([to, label]) => (
              <NavLink key={to} to={to} className={linkCls} onClick={close}>{label}</NavLink>
            ))}
            {user ? (
              <>
                {user.role === "stylist" && <Link to="/stylist" className="px-2 py-1 text-sm" onClick={close}>Stylist console</Link>}
                {user.role === "customer" && <Link to="/consultations" className="px-2 py-1 text-sm" onClick={close}>Consultations</Link>}
                {user.role !== "stylist" && (
                  <>
                    <Link to="/orders" className="px-2 py-1 text-sm" onClick={close}>Orders</Link>
                    <Link to="/wishlist" className="px-2 py-1 text-sm" onClick={close}>Wishlist</Link>
                    <Link to="/wallet" className="px-2 py-1 text-sm" onClick={close}>Wallet</Link>
                  </>
                )}
                {user.role === "admin" && <Link to="/admin" className="px-2 py-1 text-sm" onClick={close}>Admin</Link>}
                <Link to="/dashboard" className="px-2 py-1 text-sm" onClick={close}>Dashboard</Link>
                <Link to="/account" className="px-2 py-1 text-sm" onClick={close}>Account</Link>
                <button onClick={onLogout} className="px-2 py-1 text-left text-sm">Log out</button>
              </>
            ) : (
              <>
                <Link to="/login" className="px-2 py-1 text-sm" onClick={close}>Log in</Link>
                <Link to="/register" className="px-2 py-1 text-sm" onClick={close}>Sign up</Link>
              </>
            )}
          </nav>
        )}
      </header>
      <main className="flex-1"><Outlet /></main>
      <footer className="bg-sand">
        <div className="mx-auto flex max-w-7xl flex-wrap justify-between gap-4 px-4 py-8 text-sm text-black/70">
          <p>© AI Fashion Platform</p>
          <ul className="flex flex-wrap gap-4">
            <li><Link to="/about">About</Link></li>
            <li><Link to="/help">Help</Link></li>
            <li><Link to="/contact">Contact</Link></li>
            <li><Link to="/privacy">Privacy</Link></li>
            <li><Link to="/terms">Terms</Link></li>
            <li><Link to="/returns">Returns &amp; Refunds</Link></li>
          </ul>
        </div>
      </footer>
    </div>
  );
}
