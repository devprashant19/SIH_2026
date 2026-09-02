import { useLocation } from "react-router-dom";

/** Stand-in for screens not yet built; keeps every route navigable. */
export function PlaceholderPage({ title }: { title: string }) {
  const { pathname } = useLocation();
  return (
    <section aria-labelledby="page-title" className="card p-6">
      <h1 id="page-title" className="text-xl font-semibold">
        {title}
      </h1>
      <p className="mt-2 text-sm text-muted">
        This screen is under construction. Route: <code className="font-mono">{pathname}</code>
      </p>
    </section>
  );
}
