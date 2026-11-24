import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { authApi } from "../../services/api.js";
import Field from "../../components/layout/Field.jsx";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [fieldErr, setFieldErr] = useState("");

  async function onSubmit(e) {
    e.preventDefault();
    setErr(""); setFieldErr("");
    try { setMsg((await authApi.reset(token, password)).message); }
    catch (x) { setFieldErr([].concat(x.details?.password || []).join(" ")); setErr(x.message); }
  }

  return (
    <div className="mx-auto max-w-md px-4 py-16">
      <h1 className="font-serif text-3xl">Choose a new password</h1>
      {msg ? (
        <p role="status" className="mt-6">{msg} <Link className="underline" to="/login">Log in</Link></p>
      ) : (
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <Field label="New password" id="password" type="password" required autoComplete="new-password"
            value={password} onChange={(e) => setPassword(e.target.value)} error={fieldErr}
            hint="At least 8 characters, with an uppercase letter and a digit." />
          {err && !fieldErr && <p role="alert" className="text-sm text-red-700">{err}</p>}
          <button disabled={!token} className="w-full rounded-full bg-ink py-2.5 text-white hover:bg-accent disabled:opacity-60">Update password</button>
        </form>
      )}
    </div>
  );
}
