"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { api } from "@/lib/api";
import type { Task } from "@/lib/types";

export function RunButton({ id, resume = false, label }: { id: number; resume?: boolean; label: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function go() {
    setBusy(true);
    setError(null);
    try {
      await api(`/api/goals/${id}/run?resume=${resume ? "true" : "false"}`, { method: "POST" });
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button
        type="button"
        onClick={go}
        disabled={busy}
        className="rounded-full bg-forest px-4 py-2 text-sm text-white disabled:opacity-60"
      >
        {busy ? "Running the plan…" : label}
      </button>
      {error ? <p className="mt-2 text-sm text-clay">{error}</p> : null}
    </div>
  );
}

export function TaskList({ tasks }: { tasks: Task[] }) {
  const router = useRouter();

  async function setStatus(task: Task, done: boolean) {
    await api(`/api/tasks/${task.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: done ? "done" : "todo" }),
    });
    router.refresh();
  }

  if (!tasks.length) return <p className="text-sm text-muted">Nothing on this list.</p>;

  return (
    <ul className="divide-y divide-line">
      {tasks.map((task) => (
        <li key={task.id} className="flex items-start gap-3 py-3">
          <input
            type="checkbox"
            checked={task.status === "done"}
            onChange={(event) => setStatus(task, event.target.checked)}
            aria-label={`Mark ${task.title} ${task.status === "done" ? "open" : "done"}`}
            className="mt-1"
          />
          <div className="min-w-0">
            <div className={`text-sm ${task.status === "done" ? "text-muted line-through" : "text-ink"}`}>{task.title}</div>
            {task.description ? <p className="mt-1 text-sm text-muted">{task.description}</p> : null}
            <p className="mt-1 text-xs uppercase tracking-wide text-faint">
              {task.priority}
              {task.source === "agent" ? " · from the agent" : ""}
              {task.status === "in_progress" ? " · in progress" : ""}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function NewTaskForm() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState("medium");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    await api("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, priority }),
    });
    setTitle("");
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="mb-6 flex flex-col gap-2 sm:flex-row">
      <input
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        placeholder="Add a task"
        className="flex-1 rounded-xl border border-line bg-paper px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-forest/30"
      />
      <select
        value={priority}
        onChange={(event) => setPriority(event.target.value)}
        className="rounded-xl border border-line bg-paper px-3 py-2 text-sm"
      >
        <option value="high">High</option>
        <option value="medium">Medium</option>
        <option value="low">Low</option>
      </select>
      <button type="submit" className="rounded-xl bg-ink px-4 py-2 text-sm text-paper">
        Add
      </button>
    </form>
  );
}

export function NewGoalForm() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [schedule, setSchedule] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const goal = await api<{ id: number }>("/api/goals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, description, schedule: schedule || null }),
      });
      setTitle("");
      setDescription("");
      router.push(`/goals/${goal.id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the goal");
    }
  }

  return (
    <form onSubmit={onSubmit} className="card mb-8 space-y-3 p-4">
      <input
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        placeholder="Goal"
        required
        className="w-full rounded-xl border border-line bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-forest/30"
      />
      <textarea
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        placeholder="What should the agent look at, and should it draft follow-up tasks?"
        rows={3}
        className="w-full rounded-xl border border-line bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-forest/30"
      />
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <select
          value={schedule}
          onChange={(event) => setSchedule(event.target.value)}
          className="rounded-xl border border-line bg-white px-3 py-2 text-sm"
        >
          <option value="">Manual</option>
          <option value="daily@08:00">Daily · 8:00 AM ET</option>
          <option value="weekly@mon@09:00">Weekly · Monday 9:00 AM ET</option>
        </select>
        <button type="submit" className="rounded-full bg-forest px-4 py-2 text-sm text-white">
          Create goal
        </button>
      </div>
      {error ? <p className="text-sm text-clay">{error}</p> : null}
    </form>
  );
}

export function IntegrationForm({ provider, mode, mcpUrl }: { provider: string; mode: string; mcpUrl: string | null }) {
  const router = useRouter();
  const [nextMode, setNextMode] = useState(mode);
  const [url, setUrl] = useState(mcpUrl || "");
  const [message, setMessage] = useState<string | null>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    try {
      await api(`/api/integrations/${provider}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: nextMode, mcp_url: url || null }),
      });
      setMessage("Saved");
      router.refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Save failed");
    }
  }

  async function sync() {
    setMessage(null);
    try {
      await api(`/api/integrations/${provider}/sync`, { method: "POST" });
      setMessage(nextMode === "mcp" ? "Remote MCP responded" : "Search index refreshed");
      router.refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Sync failed");
    }
  }

  return (
    <form onSubmit={save} className="mt-4 space-y-2">
      <div className="flex flex-col gap-2 sm:flex-row">
        <select
          value={nextMode}
          onChange={(event) => setNextMode(event.target.value)}
          className="rounded-xl border border-line bg-white px-3 py-2 text-sm"
        >
          <option value="builtin">Built-in workspace MCP</option>
          <option value="mcp">Remote MCP URL</option>
        </select>
        <input
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="http://localhost:7000/mcp"
          className="flex-1 rounded-xl border border-line bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-forest/30"
        />
      </div>
      <div className="flex gap-2">
        <button type="submit" className="rounded-full bg-ink px-3 py-1.5 text-sm text-paper">
          Save
        </button>
        <button type="button" onClick={sync} className="rounded-full border border-line px-3 py-1.5 text-sm">
          {nextMode === "mcp" ? "Check MCP" : "Reindex"}
        </button>
      </div>
      {message ? <p className="text-sm text-muted">{message}</p> : null}
    </form>
  );
}
