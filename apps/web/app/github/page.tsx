import { ApiDown, PageTitle, Pill } from "@/components/ui";
import { api } from "@/lib/api";
import type { GitHubItem } from "@/lib/types";

export default async function GitHubPage() {
  let items: GitHubItem[];
  try {
    items = (await api<{ items: GitHubItem[] }>("/api/github")).items;
  } catch {
    return <ApiDown />;
  }
  const open = items.filter((item) => item.state === "open");
  const closed = items.filter((item) => item.state !== "open");
  return (
    <div>
      <PageTitle title="GitHub" />
      <Section title="Open" items={open} />
      <Section title="Closed" items={closed} />
    </div>
  );
}

function Section({ title, items }: { title: string; items: GitHubItem[] }) {
  if (!items.length) return null;
  return (
    <section className="mb-8">
      <h2 className="mb-3 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">{title}</h2>
      <ul className="card divide-y divide-line">
        {items.map((item) => (
          <li key={item.id} className="px-5 py-4">
            <div className="mb-1 flex items-center gap-2">
              <Pill value={item.kind} />
              <span className="text-xs text-faint">
                {item.repo}#{item.number} · {item.author}
              </span>
            </div>
            <a href={item.url} className="text-sm font-medium hover:underline">
              {item.title}
            </a>
            {item.body ? <p className="mt-1 text-sm text-muted">{item.body}</p> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
