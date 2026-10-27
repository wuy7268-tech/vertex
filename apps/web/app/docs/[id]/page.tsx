import Link from "next/link";

import { ApiDown, PageTitle, Pill, Prose } from "@/components/ui";
import { api } from "@/lib/api";
import type { Document } from "@/lib/types";

export default async function DocPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let doc: Document;
  try {
    doc = await api<Document>(`/api/documents/${id}`);
  } catch {
    return <ApiDown />;
  }
  return (
    <div>
      <Link href="/docs" className="text-sm text-muted">
        Documents
      </Link>
      <div className="mt-3">
        <Pill value={doc.source} />
      </div>
      <PageTitle title={doc.title} />
      <article className="card p-6">
        <Prose text={doc.content || ""} />
      </article>
      {doc.url?.startsWith("http") ? (
        <p className="mt-4 text-sm">
          <a href={doc.url} className="text-forest">
            Open source
          </a>
        </p>
      ) : null}
    </div>
  );
}
