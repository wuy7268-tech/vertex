import Link from "next/link";

import { ApiDown, PageTitle, Pill } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDay } from "@/lib/format";
import type { Document } from "@/lib/types";

const filters = [
  ["", "All"],
  ["drive", "Drive"],
  ["notion", "Notion"],
  ["agent", "Briefings"],
];

export default async function DocsPage({ searchParams }: { searchParams: Promise<{ source?: string }> }) {
  const { source = "" } = await searchParams;
  let documents: Document[];
  try {
    const query = source ? `?source=${source}` : "";
    documents = (await api<{ documents: Document[] }>(`/api/documents${query}`)).documents;
  } catch {
    return <ApiDown />;
  }
  return (
    <div>
      <PageTitle title="Documents" />
      <div className="mb-4 flex gap-3 text-sm">
        {filters.map(([value, label]) => (
          <Link key={label} href={value ? `/docs?source=${value}` : "/docs"} className={source === value ? "text-ink" : "text-muted"}>
            {label}
          </Link>
        ))}
      </div>
      <ul className="grid gap-3">
        {documents.map((doc) => (
          <li key={doc.id} className="card p-5">
            <div className="mb-2 flex items-center gap-2">
              <Pill value={doc.source} />
              <span className="text-xs text-faint">{formatDay(doc.updated_at)}</span>
            </div>
            <Link href={`/docs/${doc.id}`} className="font-serif text-2xl">
              {doc.title}
            </Link>
            <p className="mt-2 line-clamp-2 text-sm text-muted">{doc.excerpt}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
