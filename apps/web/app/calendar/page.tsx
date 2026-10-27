import { ApiDown, PageTitle } from "@/components/ui";
import { api } from "@/lib/api";
import { dayKey, formatDay, formatTime } from "@/lib/format";
import type { CalendarEvent } from "@/lib/types";

export default async function CalendarPage() {
  let events: CalendarEvent[];
  try {
    events = (await api<{ events: CalendarEvent[] }>("/api/calendar")).events;
  } catch {
    return <ApiDown />;
  }
  const groups = new Map<string, CalendarEvent[]>();
  for (const event of events) {
    const key = dayKey(event.start_at);
    groups.set(key, [...(groups.get(key) || []), event]);
  }
  return (
    <div>
      <PageTitle kicker="Next 7 days · Eastern time" title="Calendar" />
      <div className="space-y-4">
        {[...groups.entries()].map(([key, rows]) => (
          <section key={key} className="card p-5">
            <h2 className="mb-3 font-serif text-2xl">{formatDay(rows[0].start_at)}</h2>
            <ul className="space-y-3">
              {rows.map((event) => (
                <li key={event.id} className="grid grid-cols-[88px_1fr] gap-3 text-sm">
                  <div className="text-muted">
                    {formatTime(event.start_at)}–{formatTime(event.end_at)}
                  </div>
                  <div>
                    <div className="font-medium">{event.title}</div>
                    <p className="text-muted">
                      {event.location}
                      {event.attendees.length ? ` · ${event.attendees.map((person) => person.name).join(", ")}` : ""}
                    </p>
                    {event.description ? <p className="mt-1 text-muted">{event.description}</p> : null}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
        {!events.length ? <p className="text-sm text-muted">No events this week.</p> : null}
      </div>
    </div>
  );
}
