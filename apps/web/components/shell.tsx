"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useRef, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import type { Summary } from "@/lib/types";

const links = [
  { href: "/", label: "Today" },
  { href: "/tasks", label: "Tasks" },
  { href: "/calendar", label: "Calendar" },
  { href: "/inbox", label: "Inbox" },
  { href: "/docs", label: "Documents" },
  { href: "/github", label: "GitHub" },
  { href: "/goals", label: "Goals" },
  { href: "/integrations", label: "Integrations" },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [offline, setOffline] = useState(false);
  const previous = useRef<boolean | null>(null);

  useEffect(() => {
    let stop = false;
    async function tick() {
      try {
        const next = await api<Summary>("/api/summary");
        if (stop) return;
        setOffline(false);
        setSummary(next);
        if (previous.current === true && !next.running) router.refresh();
        previous.current = next.running;
      } catch {
        if (!stop) setOffline(true);
      }
    }
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [router]);

  function badge(href: string) {
    if (!summary) return null;
    if (href === "/inbox" && summary.unread) return summary.unread;
    if (href === "/tasks" && summary.open_tasks) return summary.open_tasks;
    if (href === "/github" && summary.open_prs) return summary.open_prs;
    return null;
  }

  return (
    <div className="min-h-screen md:grid md:grid-cols-[232px_1fr]">
      <aside className="flex flex-col bg-sidebar text-stone-200 md:min-h-screen">
        <div className="flex items-center gap-3 px-5 pb-4 pt-6">
          <Mark />
          <div>
            <div className="font-serif text-[28px] leading-none text-white">Vertex</div>
            <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-stone-400">Workspace</div>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:overflow-visible">
          {links.map((link) => {
            const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            const count = badge(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`flex items-center justify-between rounded-lg px-3 py-2 text-sm whitespace-nowrap ${
                  active ? "bg-white/10 text-white" : "text-stone-300 hover:bg-white/5 hover:text-white"
                }`}
              >
                {link.label}
                {count ? <span className="ml-3 rounded-full bg-[#d6f25c] px-1.5 text-[11px] font-medium text-sidebar">{count}</span> : null}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto hidden px-5 py-5 md:block">
          <div className="flex items-center gap-2 text-sm">
            <span className={`h-2 w-2 rounded-full ${summary?.running ? "bg-[#d6f25c] animate-pulse" : "bg-stone-500"}`} />
            <span className="text-stone-300">
              {offline ? "API unreachable" : summary?.running ? `Running ${summary.running_goals[0]?.title || "a goal"}` : "Agent idle"}
            </span>
          </div>
        </div>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-10 border-b border-line bg-canvas/90 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center px-5 py-3 md:px-10">
            <SearchBox />
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-5 py-8 md:px-10 md:py-10">{children}</main>
      </div>
    </div>
  );
}

function SearchBox() {
  const params = useSearchParams();
  const [value, setValue] = useState(params.get("q") || "");

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const query = value.trim();
    if (query) window.location.href = `/search?q=${encodeURIComponent(query)}`;
  }

  return (
    <form onSubmit={onSubmit} className="w-full">
      <input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Search mail, docs, calendar, GitHub…"
        className="w-full rounded-full border border-line bg-paper px-4 py-2 text-sm outline-none ring-forest/30 placeholder:text-faint focus:ring-2"
        aria-label="Search the workspace"
      />
    </form>
  );
}

function Mark() {
  return (
    <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
      <path d="M16 4.5 26.5 11.2 16 17.9 5.5 11.2 16 4.5Z" fill="#d6f25c" />
      <path d="M16 19.2 26.5 12.5V21.4L16 28.1 5.5 21.4V12.5L16 19.2Z" fill="#f4efe6" />
    </svg>
  );
}
