import type { ReactNode } from "react";

const tones: Record<string, string> = {
  succeeded: "bg-forest-soft text-forest",
  completed: "bg-forest-soft text-forest",
  connected: "bg-forest-soft text-forest",
  running: "bg-gold-soft text-gold",
  in_progress: "bg-gold-soft text-gold",
  paused: "bg-gold-soft text-gold",
  pending: "bg-stone-100 text-stone-600",
  idle: "bg-stone-100 text-stone-600",
  todo: "bg-stone-100 text-stone-700",
  skipped: "bg-stone-100 text-stone-500",
  failed: "bg-clay-soft text-clay",
  open: "bg-gold-soft text-gold",
  closed: "bg-stone-100 text-stone-500",
  high: "bg-clay-soft text-clay",
  medium: "bg-gold-soft text-gold",
  low: "bg-stone-100 text-stone-600",
  agent: "bg-forest-soft text-forest",
  drive: "bg-stone-100 text-stone-700",
  notion: "bg-stone-100 text-stone-700",
  gmail: "bg-clay-soft text-clay",
  pr: "bg-forest-soft text-forest",
  issue: "bg-gold-soft text-gold",
};

export function Pill({ value }: { value: string }) {
  const label = value.replaceAll("_", " ");
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ${tones[value] || "bg-stone-100 text-stone-600"}`}>
      {label}
    </span>
  );
}

export function PageTitle({ kicker, title, children }: { kicker?: string; title: string; children?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        {kicker ? <p className="text-sm text-muted">{kicker}</p> : null}
        <h1 className="font-serif text-4xl tracking-tight text-ink md:text-5xl">{title}</h1>
      </div>
      {children}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted">{children}</p>;
}

export function ApiDown() {
  return (
    <div className="card p-6">
      <h1 className="font-serif text-3xl">The workspace API is not running</h1>
      <p className="mt-2 max-w-xl text-sm text-muted">
        Start Postgres, Redis, and the FastAPI service, then refresh. The web app reads everything from that API.
      </p>
    </div>
  );
}

export function Prose({ text }: { text: string }) {
  return (
    <div className="space-y-2 text-[15px] leading-7">
      {text.split("\n").map((line, index) => {
        if (!line.trim()) return <div key={index} className="h-2" />;
        if (line.startsWith("# ")) return <h2 key={index} className="font-serif text-3xl leading-tight">{line.slice(2)}</h2>;
        if (line.startsWith("## "))
          return (
            <h3 key={index} className="pt-4 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">
              {line.slice(3)}
            </h3>
          );
        if (line.startsWith("- "))
          return (
            <p key={index} className="border-l border-line pl-3 text-ink">
              {line.slice(2)}
            </p>
          );
        return <p key={index}>{line}</p>;
      })}
    </div>
  );
}
