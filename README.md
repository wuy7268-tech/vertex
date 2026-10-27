# Vertex

Agentic workspace for tasks, calendar, email, documents, and GitHub. A goal is planned into dependent steps, run through MCP tools, and checkpointed so a failure can resume without repeating finished work.

## Run

```bash
docker compose up -d postgres redis
cd apps/api && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --port 8000
```

In another shell:

```bash
cd apps/web && npm install && npm run dev
```

Open http://localhost:3000. The API is http://localhost:8000.

On startup the scheduler runs the morning briefing if it is due. Design review prep is a manual goal.

## Layout

- `apps/web` — Next.js workspace
- `apps/api` — FastAPI agent, Postgres models, Redis cache
- Connectors for Google Calendar, Gmail, Drive, GitHub, and Notion speak MCP `tools/list` and `tools/call`. Built-in servers read the local workspace. Set a remote MCP URL on Integrations to replace one.

Optional model calls use an OpenAI-compatible API (`VERTEX_LLM_API_KEY`). Without a key, planning and briefings stay on the built-in planner. Identical prompts are cached either way.

```bash
cd apps/api && .venv/bin/pytest -q
```
