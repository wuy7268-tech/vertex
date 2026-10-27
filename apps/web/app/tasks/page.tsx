import Link from "next/link";

import { NewTaskForm, TaskList } from "@/components/actions";
import { ApiDown, PageTitle } from "@/components/ui";
import { api } from "@/lib/api";
import type { Task } from "@/lib/types";

export default async function TasksPage({ searchParams }: { searchParams: Promise<{ status?: string }> }) {
  const { status = "open" } = await searchParams;
  let tasks: Task[];
  try {
    tasks = (await api<{ tasks: Task[] }>(`/api/tasks?status=${encodeURIComponent(status)}`)).tasks;
  } catch {
    return <ApiDown />;
  }
  const filters = [
    ["open", "Open"],
    ["done", "Done"],
    ["all", "All"],
  ];
  return (
    <div>
      <PageTitle title="Tasks" />
      <div className="mb-4 flex gap-3 text-sm">
        {filters.map(([value, label]) => (
          <Link key={value} href={value === "open" ? "/tasks" : `/tasks?status=${value}`} className={status === value ? "text-ink" : "text-muted"}>
            {label}
          </Link>
        ))}
      </div>
      <NewTaskForm />
      <div className="card px-5">
        <TaskList tasks={tasks} />
      </div>
    </div>
  );
}
