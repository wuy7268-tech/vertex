import Link from "next/link";

import { RunButton } from "@/components/actions";
import { ApiDown, PageTitle, Pill } from "@/components/ui";
import { api } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import type { GoalDetail, Plan, Step } from "@/lib/types";

export default async function GoalPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ run?: string }>;
}) {
  const { id } = await params;
  const { run: runId } = await searchParams;
  let detail: GoalDetail;
  try {
    detail = await api<GoalDetail>(`/api/goals/${id}${runId ? `?run=${runId}` : ""}`);
  } catch {
    return <ApiDown />;
  }
  const { goal, run, runs } = detail;
  const plan = run?.plans.at(-1);
  const resume = run?.status === "paused" || run?.status === "failed";
  return (
    <div>
      <Link href="/goals" className="text-sm text-muted">
        Goals
      </Link>
      <PageTitle kicker={goal.schedule_label} title={goal.title}>
        <RunButton id={goal.id} resume={resume} label={resume ? "Resume" : run ? "Run again" : "Run"} />
      </PageTitle>
      <p className="mb-8 max-w-2xl text-sm leading-6 text-muted">{goal.description}</p>
      {!run || !plan ? (
        <p className="text-sm text-muted">This goal has not run yet.</p>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-6">
            <section className="card p-5">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted">Plan v{plan.version}</h2>
                <Pill value={run.status} />
              </div>
              {plan.version > 1 ? <p className="mb-4 text-sm text-muted">{plan.summary}</p> : null}
              <StepList plan={plan} />
            </section>
            {run.compacted_context ? (
              <section className="card p-5">
                <h2 className="mb-3 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">Compacted memory</h2>
                <pre className="whitespace-pre-wrap font-sans text-sm leading-6 text-ink">{run.compacted_context}</pre>
              </section>
            ) : null}
            <section className="card p-5">
              <h2 className="mb-3 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">Trace</h2>
              <ol className="space-y-3 border-l border-line pl-4">
                {run.events.map((event) => (
                  <li key={event.id}>
                    <div className="text-[11px] uppercase tracking-[0.14em] text-faint">
                      {event.kind.replaceAll("_", " ")}
                      {event.step_key ? ` · ${event.step_key}` : ""}
                    </div>
                    <p className="text-sm">{event.message}</p>
                  </li>
                ))}
              </ol>
            </section>
          </div>
          <aside className="space-y-6">
            <section className="card p-5">
              <h2 className="mb-3 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">Artifacts</h2>
              <ul className="space-y-2 text-sm">
                {run.artifacts.documents.map((doc) => (
                  <li key={doc.id}>
                    <Link href={`/docs/${doc.id}`} className="text-forest">
                      {doc.title}
                    </Link>
                  </li>
                ))}
                {run.artifacts.tasks.map((task) => (
                  <li key={task.id}>{task.title}</li>
                ))}
                {!run.artifacts.documents.length && !run.artifacts.tasks.length ? <li className="text-muted">None yet.</li> : null}
              </ul>
            </section>
            <section className="card p-5">
              <h2 className="mb-3 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">Runs</h2>
              <ul className="space-y-2 text-sm">
                {runs.map((item) => (
                  <li key={item.id}>
                    <Link href={`/goals/${goal.id}?run=${item.id}`} className={item.id === run.id ? "font-medium" : "text-muted"}>
                      {item.started_at ? formatWhen(item.started_at) : "Run"} · {item.status}
                    </Link>
                  </li>
                ))}
              </ul>
              {run.error ? <p className="mt-3 text-sm text-clay">{run.error}</p> : null}
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}

function StepList({ plan }: { plan: Plan }) {
  const waves = [...new Set(plan.steps.map((step) => step.wave))].sort((a, b) => a - b);
  return (
    <div className="space-y-5">
      {waves.map((wave) => (
        <div key={wave}>
          <p className="mb-2 text-xs text-faint">Wave {wave + 1}{wave > 0 ? " · after the previous wave" : ""}</p>
          <ul className="space-y-2">
            {plan.steps.filter((step) => step.wave === wave).map((step) => (
              <StepRow key={step.id} step={step} />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function StepRow({ step }: { step: Step }) {
  return (
    <li className="rounded-xl border border-line bg-white px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium">{step.title}</div>
          <div className="mt-1 font-mono text-xs text-faint">{step.tool_name}</div>
        </div>
        <div className="flex items-center gap-2">
          {step.cache_hit ? <span className="text-[11px] text-forest">cache</span> : null}
          {step.attempts > 1 ? <span className="text-[11px] text-gold">{step.attempts} tries</span> : null}
          <Pill value={step.status} />
        </div>
      </div>
      {step.depends_on.length ? <p className="mt-2 text-xs text-muted">Depends on {step.depends_on.join(", ")}</p> : null}
      {step.summary ? <p className="mt-1 text-sm text-muted">{step.summary}</p> : null}
    </li>
  );
}
