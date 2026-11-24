import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";
import { authApi, walletApi } from "../../services/api.js";

export default function Dashboard() {
  const { user } = useAuth();
  const [sent, setSent] = useState("");
  const { data: w } = useQuery({ queryKey: ["wallet"], queryFn: walletApi.wallet });
  return (
    <div className="mx-auto max-w-7xl px-4 py-12">
      <h1 className="font-serif text-3xl">Hello, {user.name}</h1>
      <p className="mt-2 text-black/70">Signed in as {user.email} ({user.role}).</p>
      {!user.is_verified && (
        <div role="status" className="mt-6 flex flex-wrap items-center gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm">
          <span>Your email is not verified yet.</span>
          <button className="underline" onClick={async () => setSent((await authApi.resendVerification()).message)}>Resend verification email</button>
          {sent && <span>{sent}</span>}
        </div>
      )}
      {w && (
        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          <Link to="/wallet" className="rounded-xl border border-sky-200 bg-sky-50 p-4"><p className="text-xs font-semibold uppercase tracking-widest text-black/60">Daily Credits</p><p className="font-serif text-3xl">{w.wallet.daily.balance}</p></Link>
          <Link to="/wallet" className="rounded-xl border border-amber-200 bg-amber-50 p-4"><p className="text-xs font-semibold uppercase tracking-widest text-black/60">Super Credits</p><p className="font-serif text-3xl">{w.wallet.super.balance}</p></Link>
        </div>
      )}
      <p className="mt-6 rounded-xl bg-sand p-4 text-sm">
        Orders and more will appear here in later phases. <Link className="underline" to="/account">Edit your fashion profile</Link>.
      </p>
    </div>
  );
}
