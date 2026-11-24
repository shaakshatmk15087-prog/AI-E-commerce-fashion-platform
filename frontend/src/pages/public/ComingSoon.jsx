import { Link } from "react-router-dom";

export default function ComingSoon({ title = "Coming soon" }) {
  return (
    <div className="mx-auto max-w-2xl px-4 py-24 text-center">
      <h1 className="font-serif text-3xl">{title}</h1>
      <p className="mt-3 text-black/70">This page is planned for a later phase.</p>
      <Link to="/" className="mt-6 inline-block underline">Back home</Link>
    </div>
  );
}
