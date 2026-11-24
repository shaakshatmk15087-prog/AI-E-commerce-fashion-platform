import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { authApi } from "../../services/api.js";
import { useAuth } from "../../context/AuthContext.jsx";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const { user, setUser } = useAuth();
  const [state, setState] = useState({ status: "loading", message: "" });

  useEffect(() => {
    const token = params.get("token");
    if (!token) { setState({ status: "error", message: "Missing verification token." }); return; }
    let cancelled = false;
    authApi.verify(token)
      .then((r) => { if (!cancelled) { setState({ status: "ok", message: r.message }); if (user) setUser({ ...user, is_verified: true }); } })
      .catch((e) => !cancelled && setState({ status: "error", message: e.message }));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  return (
    <div className="mx-auto max-w-md px-4 py-24 text-center">
      <h1 className="font-serif text-3xl">Email verification</h1>
      <p role="status" className={`mt-4 ${state.status === "error" ? "text-red-700" : ""}`}>
        {state.status === "loading" ? "Verifying…" : state.message}
      </p>
      <Link to="/dashboard" className="mt-6 inline-block underline">Continue</Link>
    </div>
  );
}
