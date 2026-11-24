import { useState } from "react";
import { Link } from "react-router-dom";
import { authApi } from "../../services/api.js";
import Field from "../../components/layout/Field.jsx";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  async function onSubmit(e) {
    e.preventDefault();
    setErr(""); setMsg("");
    try { setMsg((await authApi.forgot(email)).message); } catch (x) { setErr(x.message); }
  }

  return (
    <div className="mx-auto max-w-md px-4 py-16">
      <h1 className="font-serif text-3xl">Reset your password</h1>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        <Field label="Email" id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        {msg && <p role="status" className="text-sm text-green-800">{msg}</p>}
        {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
        <button className="w-full rounded-full bg-ink py-2.5 text-white hover:bg-accent">Send reset link</button>
      </form>
      <p className="mt-4 text-sm"><Link className="underline" to="/login">Back to log in</Link></p>
    </div>
  );
}
