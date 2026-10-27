import Link from "next/link";

import { NewGoalForm, RunButton } from "@/components/actions";
import { ApiDown, PageTitle, Pill } from "@/components/ui";
import { api } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import type { Goal } from "@/lib/types";

export default async function GoalsPage() {
  let goals: Goal[];
  try {
    goals = (await api<{ goals: Goal[] }>("/api/goals")).goals;
  } catch {
    return <ApiDown />;
  }
  return (
    <div>
      <PageTitle title="Goals" />
      <p className="mb-6 max-w-2xl text-sm leading-6 text-muted">
        A goal becomes a plan. Each step waits on its dependencies, and a checkpoint is written after every tool call.
        Failed steps retry on the same idempotency key. Empty or broken tools trigger a replan that keeps finished work.
        Long logs are compacted into a short memory so later steps do not reread every payload.
      </p>
      <NewGoalForm />
      <ul className="space-y-3">
        {goals.map((goal) => (
          <li key={goal.id} className="card flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="mb-2 flex items-center gap-2">
                <Pill value={goal.status} />
                <span className="text-xs text-faint">{goal.schedule_label}</span>
              </div>
              <Link href={`/goals/${goal.id}`} className="font-serif text-2xl">
                {goal.title}
              </Link>
              <p className="mt-1 max-w-xl text-sm text-muted">{goal.description}</p>
              {goal.next_run_at ? <p className="mt-2 text-xs text-faint">Next run {formatWhen(goal.next_run_at)}</p> : null}
            </div>
            <RunButton
              id={goal.id}
              resume={goal.latest_run?.status === "paused" || goal.latest_run?.status === "failed"}
              label={goal.latest_run?.status === "paused" || goal.latest_run?.status === "failed" ? "Resume" : "Run"}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}
