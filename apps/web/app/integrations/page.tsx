import { IntegrationForm } from "@/components/actions";
import { ApiDown, PageTitle, Pill } from "@/components/ui";
import { api } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import type { Integration } from "@/lib/types";

export default async function IntegrationsPage() {
  let integrations: Integration[];
  try {
    integrations = (await api<{ integrations: Integration[] }>("/api/integrations")).integrations;
  } catch {
    return <ApiDown />;
  }
  return (
    <div>
      <PageTitle title="Integrations" />
      <p className="mb-6 max-w-2xl text-sm leading-6 text-muted">
        Calendar, Gmail, Drive, GitHub, and Notion are reached through MCP. The built-in servers read this workspace.
        A remote MCP URL replaces that provider for the agent.
      </p>
      <div className="grid gap-4">
        {integrations.map((item) => (
          <section key={item.provider} className="card p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-serif text-2xl">{item.label}</h2>
                <p className="mt-1 max-w-xl text-sm text-muted">{item.blurb}</p>
              </div>
              <Pill value={item.status} />
            </div>
            <ul className="mt-3 space-y-1 text-sm text-muted">
              {item.tools.map((tool) => (
                <li key={tool.name}>
                  <span className="font-mono text-xs text-ink">{tool.name}</span> — {tool.description}
                </li>
              ))}
            </ul>
            {item.last_synced_at ? <p className="mt-3 text-xs text-faint">Synced {formatWhen(item.last_synced_at)}</p> : null}
            <IntegrationForm provider={item.provider} mode={item.mode} mcpUrl={item.mcp_url} />
          </section>
        ))}
      </div>
    </div>
  );
}
