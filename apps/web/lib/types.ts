export type Task = {
  id: number;
  title: string;
  description: string;
  status: string;
  priority: string;
  due_at: string | null;
  source: string;
  source_ref: string | null;
  goal_id: number | null;
};

export type Attendee = { name: string; email: string };

export type CalendarEvent = {
  id: number;
  title: string;
  description: string;
  start_at: string;
  end_at: string;
  location: string;
  attendees: Attendee[];
  source: string;
};

export type Message = {
  id: number;
  sender_name: string;
  sender_email: string;
  subject: string;
  snippet: string;
  body?: string;
  received_at: string;
  unread: boolean;
  labels: string[];
};

export type Document = {
  id: number;
  title: string;
  source: string;
  url: string;
  updated_at: string;
  excerpt?: string;
  content?: string;
};

export type GitHubItem = {
  id: number;
  kind: string;
  repo: string;
  number: number;
  title: string;
  state: string;
  author: string;
  url: string;
  updated_at: string;
  body?: string;
};

export type Goal = {
  id: number;
  title: string;
  description: string;
  status: string;
  schedule: string | null;
  schedule_label: string;
  next_run_at: string | null;
  last_run_at: string | null;
  latest_run: RunSummary | null;
};

export type RunSummary = {
  id: number;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  replan_count: number;
  error: string | null;
};

export type Step = {
  id: number;
  key: string;
  title: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  depends_on: string[];
  status: string;
  attempts: number;
  cache_hit: boolean;
  summary: string;
  wave: number;
};

export type Plan = {
  id: number;
  version: number;
  summary: string;
  steps: Step[];
};

export type AgentEvent = {
  id: number;
  step_key: string | null;
  kind: string;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type RunDetail = {
  id: number;
  status: string;
  idempotency_key: string;
  compacted_context: string;
  replan_count: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  plans: Plan[];
  events: AgentEvent[];
  artifacts: { documents: Document[]; tasks: Task[] };
};

export type GoalDetail = {
  goal: Goal;
  runs: RunSummary[];
  run: RunDetail | null;
};

export type Today = {
  now: string;
  events: CalendarEvent[];
  tasks: Task[];
  unread: Message[];
  pulls: GitHubItem[];
  goals: Goal[];
  briefing: Document | null;
};

export type Summary = {
  unread: number;
  open_tasks: number;
  open_prs: number;
  running: boolean;
  running_goals: { id: number; title: string }[];
};

export type SearchHit = {
  title: string;
  snippet: string;
  score: number;
  origin: string;
  href: string;
};

export type Integration = {
  provider: string;
  label: string;
  blurb: string;
  status: string;
  mode: string;
  mcp_url: string | null;
  last_synced_at: string | null;
  tools: { name: string; description: string }[];
};
