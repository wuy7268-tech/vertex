import Link from "next/link";

import { RunButton } from "@/components/actions";
import { ApiDown, PageTitle, Pill, Prose } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDay, formatTime, relative } from "@/lib/format";
import type { Today } from "@/lib/types";

export default async function TodayPage() {
  let data: Today;
  try {
    data = await api<Today>("/api/today");
  } catch {
    return <ApiDown />;
  }

  return (
    <div>
      <PageTitle kicker={formatDay(data.now)} title="Today" />
      {data.briefing ? (
        <section className="card mb-6 p-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted">Latest briefing</p>
            <Link href={`/docs/${data.briefing.id}`} className="text-sm text-forest">
              Open
            </Link>
          </div>
          <div className="max-h-80 overflow-hidden">
            <Prose text={data.briefing.content || data.briefing.excerpt || data.briefing.title} />
          </div>
        </section>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-3">
          <section className="card p-5">
            <h2 className="mb-3 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">Next two days</h2>
            {data.events.length ? (
              <ul className="space-y-4">
                {data.events.map((event) => (
                  <li key={event.id} className="flex gap-4">
                    <div className="w-16 shrink-0 text-sm text-muted">{formatTime(event.start_at)}</div>
                    <div>
                      <div className="text-sm font-medium">{event.title}</div>
                      <p className="text-sm text-muted">
                        {event.location}
                        {event.attendees.length ? ` · ${event.attendees.map((person) => person.name).join(", ")}` : ""}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">Nothing scheduled for the next two days.</p>
            )}
          </section>
          <section className="card p-5">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted">Open tasks</h2>
              <Link href="/tasks" className="text-sm text-forest">
                All tasks
              </Link>
            </div>
            <ul className="divide-y divide-line">
              {data.tasks.map((task) => (
                <li key={task.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                  <span>{task.title}</span>
                  <Pill value={task.priority} />
                </li>
              ))}
            </ul>
          </section>
        </div>
        <div className="space-y-6 lg:col-span-2">
          <section className="card p-5">
            <h2 className="mb-3 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">Unread</h2>
            <ul className="space-y-3">
              {data.unread.map((message) => (
                <li key={message.id}>
                  <Link href={`/inbox/${message.id}`} className="block">
                    <div className="text-sm font-medium">{message.sender_name}</div>
                    <div className="text-sm text-ink">{message.subject}</div>
                    <div className="text-xs text-faint">{relative(message.received_at)}</div>
                  </Link>
                </li>
              ))}
              {!data.unread.length ? <p className="text-sm text-muted">Inbox is clear.</p> : null}
            </ul>
          </section>
          <section className="card p-5">
            <h2 className="mb-3 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">Review requested</h2>
            <ul className="space-y-3">
              {data.pulls.map((item) => (
                <li key={item.id} className="text-sm">
                  <a href={item.url} className="font-medium hover:underline">
                    {item.repo}#{item.number}
                  </a>
                  <div className="text-muted">{item.title}</div>
                </li>
              ))}
            </ul>
          </section>
          <section className="card p-5">
            <h2 className="mb-3 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">Goals</h2>
            <ul className="space-y-4">
              {data.goals.map((goal) => (
                <li key={goal.id} className="flex items-start justify-between gap-3">
                  <div>
                    <Link href={`/goals/${goal.id}`} className="text-sm font-medium">
                      {goal.title}
                    </Link>
                    <div className="text-xs text-faint">{goal.schedule_label}</div>
                  </div>
                  {goal.latest_run?.status === "paused" || goal.latest_run?.status === "failed" ? (
                    <RunButton id={goal.id} resume label="Resume" />
                  ) : (
                    <RunButton id={goal.id} label="Run" />
                  )}
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
