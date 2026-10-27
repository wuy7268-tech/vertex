import Link from "next/link";

import { ApiDown, PageTitle, Pill } from "@/components/ui";
import { api } from "@/lib/api";
import type { SearchHit } from "@/lib/types";

export default async function SearchPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q = "" } = await searchParams;
  if (q.trim().length < 2) {
    return (
      <div>
        <PageTitle title="Search" />
        <p className="text-sm text-muted">Try a name, a meeting, or a phrase from a document.</p>
      </div>
    );
  }
  let results: SearchHit[];
  try {
    results = (await api<{ results: SearchHit[] }>(`/api/search?q=${encodeURIComponent(q)}`)).results;
  } catch {
    return <ApiDown />;
  }
  return (
    <div>
      <PageTitle kicker="Semantic search" title={q} />
      <ul className="space-y-3">
        {results.map((hit) => (
          <li key={`${hit.href}-${hit.title}`} className="card p-5">
            <div className="mb-2 flex items-center gap-2">
              <Pill value={hit.origin} />
              <span className="text-xs text-faint">{hit.score.toFixed(2)}</span>
            </div>
            {hit.href.startsWith("/") ? (
              <Link href={hit.href} className="font-serif text-2xl">
                {hit.title}
              </Link>
            ) : (
              <div className="font-serif text-2xl">{hit.title}</div>
            )}
            <p className="mt-2 text-sm text-muted">{hit.snippet}</p>
          </li>
        ))}
        {!results.length ? <li className="text-sm text-muted">No close matches.</li> : null}
      </ul>
    </div>
  );
}
