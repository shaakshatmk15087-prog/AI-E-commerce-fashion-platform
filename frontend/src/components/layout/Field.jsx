export default function Field({ label, id, error, hint, ...props }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">{label}</label>
      <input id={id} aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined}
        className="w-full rounded-lg border border-black/20 px-3 py-2 focus:border-accent" {...props} />
      {hint && !error && <p className="mt-1 text-xs text-black/60">{hint}</p>}
      {error && <p id={`${id}-err`} className="mt-1 text-sm text-red-700">{error}</p>}
    </div>
  );
}
