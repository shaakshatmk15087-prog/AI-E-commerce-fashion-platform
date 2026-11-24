import { useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";

function Field({ label, id, error, ...props }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">{label}</label>
      <input id={id} aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined}
        className="w-full rounded-lg border border-black/20 px-3 py-2 focus:border-accent" {...props} />
      {error && <p id={`${id}-err`} className="mt-1 text-sm text-red-700">{error}</p>}
    </div>
  );
}

export default function AuthForm({ mode }) {
  const isRegister = mode === "register";
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const referral = params.get("ref") || "";
  const location = useLocation();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function onSubmit(e) {
    e.preventDefault();
    setErrors({}); setFormError(""); setBusy(true);
    try {
      await (isRegister ? register(referral ? { ...form, referral_code: referral } : form) : login({ email: form.email, password: form.password }));
      const from = location.state?.from;
      navigate(from ? from.pathname + (from.search || "") : "/dashboard", { replace: true, state: from?.state });
    } catch (err) {
      const d = err.details || {};
      setErrors(Object.fromEntries(Object.entries(d).map(([k, v]) => [k, [].concat(v).join(" ")])));
      setFormError(err.message);
    } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto max-w-md px-4 py-16">
      <h1 className="font-serif text-3xl">{isRegister ? "Create your account" : "Welcome back"}</h1>
      {isRegister && referral && <p className="mt-2 text-sm text-green-800">Referral code {referral.toUpperCase()} applied.</p>}
      <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
        {isRegister && <Field label="Name" id="name" value={form.name} onChange={set("name")} error={errors.name} required autoComplete="name" />}
        <Field label="Email" id="email" type="email" value={form.email} onChange={set("email")} error={errors.email} required autoComplete="email" />
        <Field label="Password" id="password" type="password" value={form.password} onChange={set("password")} error={errors.password} required
          autoComplete={isRegister ? "new-password" : "current-password"} />
        {isRegister && <p className="text-xs text-black/60">At least 8 characters, with an uppercase letter and a digit.</p>}
        {formError && <p role="alert" className="text-sm text-red-700">{formError}</p>}
        <button disabled={busy} className="w-full rounded-full bg-ink py-2.5 text-white hover:bg-accent disabled:opacity-60">
          {busy ? "Please wait…" : isRegister ? "Sign up" : "Log in"}
        </button>
      </form>
      {!isRegister && <p className="mt-4 text-sm"><Link className="underline" to="/forgot-password">Forgot password?</Link></p>}
      <p className="mt-4 text-sm">
        {isRegister ? <>Already registered? <Link className="underline" to="/login" state={location.state}>Log in</Link></> : <>New here? <Link className="underline" to="/register" state={location.state}>Create an account</Link></>}
      </p>
    </div>
  );
}
