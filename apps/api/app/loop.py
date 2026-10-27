import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import PermanentToolError, TransientToolError
from app.models import Goal, Plan, PlanStep, StepResult, WorkflowEvent, WorkflowRun
from app.planner import Planner
from app.timeutil import utcnow
from app.tools import SPEC_BY_NAME, summarize_result

log = logging.getLogger("vertex.agent")

BROADENABLE = {
    "gmail.list_messages",
    "drive.list_files",
    "github.list_items",
    "notion.search",
    "calendar.list_events",
}


@dataclass
class Outcome:
    key: str
    tool_name: str
    status: str
    empty: bool = False
    error: str | None = None
    tool_args: dict | None = None


class AgentLoop:
    """Plan, act, reflect, and replan without repeating finished work.

    Every successful step is stored under an idempotency key. A resume loads
    that checkpoint and does not call the tool again. Read results are also
    cached so a later goal can skip a live lookup. When the event log grows,
    older results are folded into a short memory the next plan can see.
    """

    def __init__(self, sessions, cache, tools, clock, llm=None, *, compact_after: int = 8, max_attempts: int = 3, retry_backoff: float = 0.15):
        self.sessions = sessions
        self.cache = cache
        self.tools = tools
        self.clock = clock
        self.compact_after = compact_after
        self.max_attempts = max_attempts
        self.retry_backoff = retry_backoff
        self.planner = Planner(clock, llm, tools.names() if hasattr(tools, "names") else [])

    def execute(self, goal_id: int, *, resume: bool = False, idempotency_key: str | None = None, stop_after: str | None = None) -> WorkflowRun:
        db = self.sessions()
        token = uuid.uuid4().hex
        lock = f"lock:goal:{goal_id}"
        acquired = self.cache.set_nx(lock, token, 180)
        run_id = None
        try:
            if not acquired:
                existing = self._latest_open(db, goal_id) or self._latest(db, goal_id)
                if existing is None:
                    raise RuntimeError("This goal is already running")
                return _snapshot(existing)
            goal = db.get(Goal, goal_id)
            if goal is None:
                raise KeyError(goal_id)
            run = self._claim(db, goal, resume=resume, idempotency_key=idempotency_key)
            run_id = run.id
            if run.status == "completed":
                return _snapshot(run)
            run.status = "running"
            run.error = None
            goal.status = "running"
            goal.updated_at = self.clock.now()
            db.commit()
            if run.plan_id is None:
                self._create_plan(db, run, goal)
            self._advance(db, run.id, goal.id, stop_after)
            return _snapshot(db.get(WorkflowRun, run.id))
        except Exception as exc:
            if not isinstance(exc, (KeyError, RuntimeError)):
                self._fail_unexpected(db, run_id, goal_id, exc)
            raise
        finally:
            if acquired and self.cache.get_str(lock) == token:
                self.cache.delete(lock)
            db.close()

    def _advance(self, db: Session, run_id: int, goal_id: int, stop_after: str | None) -> None:
        for _ in range(30):
            run = db.get(WorkflowRun, run_id)
            goal = db.get(Goal, goal_id)
            self._maybe_compact(db, run)
            steps = self._steps(db, run)
            step = _next_ready(steps)
            if step is None:
                if any(item.status in ("pending", "running") for item in steps):
                    self._finish(db, run, goal, "failed", "Plan has pending steps with unmet dependencies")
                else:
                    self._finish(db, run, goal, "completed", None)
                return
            outcome = self._execute_step(db, run_id, step.id, goal_id)
            run = db.get(WorkflowRun, run_id)
            goal = db.get(Goal, goal_id)
            steps = self._steps(db, run)
            if stop_after and outcome.status == "succeeded" and outcome.key == stop_after:
                self._finish(db, run, goal, "paused", None)
                return
            decision, hint, message = _reflect(outcome, steps)
            self._log(db, run, outcome.key, "reflection", message, {"action": decision, **hint})
            db.commit()
            if decision == "continue":
                continue
            if decision == "replan":
                if run.replan_count >= 8:
                    self._finish(db, run, goal, "failed", "Stopped after too many replans")
                    return
                self._replan(db, run, goal, hint, message)
                continue
            self._finish(db, run, goal, "failed", message)
            return
        run = db.get(WorkflowRun, run_id)
        goal = db.get(Goal, goal_id)
        self._finish(db, run, goal, "failed", "Exceeded planning cycles")

    def _execute_step(self, db: Session, run_id: int, step_id: int, goal_id: int) -> Outcome:
        step = db.get(PlanStep, step_id)
        idem = _idempotency_key(run_id, step.key, step.tool_args)
        existing = db.scalar(select(StepResult).where(StepResult.idempotency_key == idem, StepResult.status == "succeeded"))
        if existing or step.status == "succeeded":
            if step.status != "succeeded":
                step.status = "succeeded"
            self._log(
                db,
                db.get(WorkflowRun, run_id),
                step.key,
                "checkpoint",
                "Reused the durable result for this step; the tool was not called again.",
                {"idempotency_key": idem},
            )
            db.commit()
            result = existing.result if existing else {}
            return Outcome(step.key, step.tool_name, "succeeded", _is_empty(result), tool_args=dict(step.tool_args or {}))

        spec = SPEC_BY_NAME.get(step.tool_name)
        cacheable = bool(step.cacheable and spec and spec.cacheable and spec.ttl > 0)
        cache_key = None
        if cacheable:
            generation = self.cache.get_int(f"gen:{spec.namespace}")
            cache_key = f"tool:{spec.namespace}:{generation}:{step.tool_name}:{_args_hash(step.tool_args)}"
            cached = self.cache.get(cache_key)
            if isinstance(cached, dict) and "value" in cached:
                self._store_success(db, run_id, step, idem, cached["value"], attempts=step.attempts or 1, cache_hit=True)
                self._log(db, db.get(WorkflowRun, run_id), step.key, "cache_hit", f"Cache hit for {step.tool_name}; skipped a live lookup.", {})
                db.commit()
                return Outcome(step.key, step.tool_name, "succeeded", _is_empty(cached["value"]), tool_args=dict(step.tool_args or {}))

        step.status = "running"
        db.commit()
        attempts = step.attempts or 0
        while True:
            attempts += 1
            step = db.get(PlanStep, step_id)
            step.attempts = attempts
            run = db.get(WorkflowRun, run_id)
            self._log(db, run, step.key, "tool_call", f"Calling {step.tool_name}.", {"args": step.tool_args, "attempt": attempts})
            db.commit()
            try:
                result = self.tools.call(
                    step.tool_name,
                    dict(step.tool_args or {}),
                    db=db,
                    context=self._context(db, run_id, goal_id),
                )
            except (PermanentToolError, TransientToolError, Exception) as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                db.rollback()
                step = db.get(PlanStep, step_id)
                run = db.get(WorkflowRun, run_id)
                retryable = not isinstance(exc, PermanentToolError)
                if retryable and attempts < self.max_attempts:
                    self._log(db, run, step.key, "retry", f"{step.tool_name} failed ({exc}). Retrying the same step.", {"attempt": attempts})
                    step.attempts = attempts
                    step.status = "running"
                    db.commit()
                    if self.retry_backoff:
                        time.sleep(self.retry_backoff * attempts)
                    continue
                step.status = "failed"
                step.attempts = attempts
                self._log(db, run, step.key, "error", f"{step.tool_name} failed: {exc}", {"attempt": attempts})
                db.commit()
                return Outcome(step.key, step.tool_name, "failed", error=str(exc), tool_args=dict(step.tool_args or {}))

            summary = result.get("summary") or summarize_result(step.tool_name, result)
            invalidate = list(result.get("invalidate") or [])
            llm_cache_hit = bool(result.get("llm_cache_hit"))
            stored = {key: value for key, value in result.items() if key not in {"invalidate", "llm_cache_hit"}}
            self._store_success(db, run_id, step, idem, stored, attempts=attempts, cache_hit=False, summary=summary)
            self._log(db, db.get(WorkflowRun, run_id), step.key, "tool_result", summary, {})
            self._log(
                db,
                db.get(WorkflowRun, run_id),
                step.key,
                "checkpoint",
                "Checkpoint saved. This step can be skipped if the run resumes.",
                {"idempotency_key": idem},
            )
            if llm_cache_hit:
                self._log(db, db.get(WorkflowRun, run_id), step.key, "cache_hit", "Reused a cached model response instead of calling the LLM.", {})
            db.commit()
            if cacheable and cache_key:
                self.cache.set(cache_key, {"value": stored}, spec.ttl)
            for namespace in invalidate or ([spec.namespace] if spec and not spec.cacheable else []):
                self.cache.incr(f"gen:{namespace}")
            return Outcome(step.key, step.tool_name, "succeeded", _is_empty(stored), tool_args=dict(step.tool_args or {}))

    def _store_success(self, db, run_id, step, idem, result, *, attempts, cache_hit, summary=None):
        step.status = "succeeded"
        summary = summary or result.get("summary") or summarize_result(step.tool_name, result)
        db.add(
            StepResult(
                run_id=run_id,
                step_key=step.key,
                idempotency_key=idem,
                status="succeeded",
                result=result,
                summary=summary,
                attempts=attempts,
                cache_hit=cache_hit,
            )
        )

    def _context(self, db, run_id: int, goal_id: int) -> dict:
        run = db.get(WorkflowRun, run_id)
        rows = db.scalars(select(StepResult).where(StepResult.run_id == run_id, StepResult.status == "succeeded")).all()
        return {
            "run_id": run_id,
            "goal_id": goal_id,
            "now": self.clock.now(),
            "compacted": run.compacted_context if run else "",
            "steps": {row.step_key: row.result for row in rows},
        }

    def _create_plan(self, db, run: WorkflowRun, goal: Goal) -> None:
        text = _goal_text(goal)
        drafts = self.planner.plan(text, self.clock.now())
        plan = Plan(goal_id=goal.id, run_id=run.id, version=1, summary="Initial plan")
        db.add(plan)
        db.flush()
        _persist_steps(db, plan, drafts)
        run.plan_id = plan.id
        source = "model" if self.planner.last_source == "llm" else "heuristic planner"
        deps = ", ".join(f"{step.key}→{','.join(step.depends_on) or 'start'}" for step in drafts)
        self._log(db, run, None, "plan", f"Planned {len(drafts)} steps with the {source}.", {"steps": deps, "source": self.planner.last_source})
        db.commit()

    def _replan(self, db, run: WorkflowRun, goal: Goal, hint: dict, message: str) -> None:
        current = db.get(Plan, run.plan_id)
        drafts = self.planner.revise(self._steps(db, run), hint, self.clock.now())
        plan = Plan(
            goal_id=goal.id,
            run_id=run.id,
            version=(current.version if current else 0) + 1,
            summary=message,
        )
        db.add(plan)
        db.flush()
        _persist_steps(db, plan, drafts)
        run.plan_id = plan.id
        run.replan_count += 1
        self._log(db, run, hint.get("broaden") or hint.get("skip"), "replan", message, {"version": plan.version, **hint})
        db.commit()

    def _maybe_compact(self, db, run: WorkflowRun) -> None:
        events = db.scalars(select(WorkflowEvent).where(WorkflowEvent.run_id == run.id).order_by(WorkflowEvent.id)).all()
        if len(events) < self.compact_after or (events and events[-1].kind == "compact"):
            return
        results = db.scalars(select(StepResult).where(StepResult.run_id == run.id, StepResult.status == "succeeded").order_by(StepResult.id)).all()
        if not results:
            return
        lines = [f"- {row.step_key}: {row.summary}" for row in results]
        run.compacted_context = "Memory of completed steps:\n" + "\n".join(lines)
        self._log(
            db,
            run,
            None,
            "compact",
            "Folded earlier tool results into a short memory so later steps do not carry every payload.",
            {"steps": len(results)},
        )
        db.commit()

    def _finish(self, db, run: WorkflowRun, goal: Goal, status: str, error: str | None) -> None:
        run.status = status
        run.error = error
        if status in ("completed", "failed"):
            run.finished_at = self.clock.now()
        goal.last_run_at = self.clock.now()
        goal.updated_at = self.clock.now()
        if status == "completed":
            goal.status = "idle" if goal.schedule else "completed"
        elif status == "paused":
            goal.status = "paused"
        else:
            goal.status = "failed"
        if error:
            self._log(db, run, None, "error", error, {})
        db.commit()
        log.info("run %s goal %s -> %s", run.id, goal.id, status)

    def _claim(self, db, goal: Goal, *, resume: bool, idempotency_key: str | None) -> WorkflowRun:
        if resume:
            run = self._latest_open(db, goal.id)
            if run is None:
                raise RuntimeError("No paused or failed run to resume")
            return run
        key = idempotency_key or f"goal:{goal.id}:manual:{uuid.uuid4()}"
        existing = db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == key))
        if existing:
            return existing
        run = WorkflowRun(goal_id=goal.id, status="running", idempotency_key=key, started_at=self.clock.now())
        db.add(run)
        db.commit()
        return run

    def _latest_open(self, db, goal_id: int) -> WorkflowRun | None:
        return db.scalar(
            select(WorkflowRun)
            .where(WorkflowRun.goal_id == goal_id, WorkflowRun.status.in_(("paused", "failed", "running")))
            .order_by(WorkflowRun.id.desc())
        )

    def _latest(self, db, goal_id: int) -> WorkflowRun | None:
        return db.scalar(select(WorkflowRun).where(WorkflowRun.goal_id == goal_id).order_by(WorkflowRun.id.desc()))

    def _steps(self, db, run: WorkflowRun) -> list[PlanStep]:
        if run.plan_id is None:
            return []
        return list(
            db.scalars(select(PlanStep).where(PlanStep.plan_id == run.plan_id).order_by(PlanStep.order_index)).all()
        )

    def _log(self, db, run: WorkflowRun, step_key: str | None, kind: str, message: str, payload: dict) -> None:
        db.add(WorkflowEvent(run_id=run.id, step_key=step_key, kind=kind, message=message, payload=payload or {}))

    def _fail_unexpected(self, db, run_id: int | None, goal_id: int, exc: Exception) -> None:
        try:
            db.rollback()
            if run_id:
                run = db.get(WorkflowRun, run_id)
                if run and run.status == "running":
                    run.status = "failed"
                    run.error = str(exc)
                    run.finished_at = utcnow()
                    self._log(db, run, None, "error", str(exc), {})
            goal = db.get(Goal, goal_id)
            if goal and goal.status == "running":
                goal.status = "failed"
            db.commit()
        except Exception:
            log.exception("could not record agent failure")


def _reflect(outcome: Outcome, steps) -> tuple[str, dict, str]:
    if outcome.status == "succeeded":
        if outcome.empty and _can_broaden(outcome, steps):
            hint = {"broaden": outcome.key}
            return "replan", hint, f"No records from {outcome.tool_name}. Replanning with a broader lookup and keeping finished steps."
        return "continue", {}, f"{outcome.key} completed."
    hint = {"skip": outcome.key}
    return "replan", hint, f"{outcome.tool_name} failed ({outcome.error}). Skipping that step and continuing with the rest of the plan."


def _can_broaden(outcome: Outcome, steps) -> bool:
    if outcome.tool_name not in BROADENABLE or outcome.key.endswith("_broad"):
        return False
    if any(step.key == f"{outcome.key}_broad" for step in steps):
        return False
    args = outcome.tool_args or {}
    if outcome.tool_name == "gmail.list_messages" and args.get("query", "recent") == "recent":
        return False
    if outcome.tool_name == "github.list_items" and args.get("state") == "all":
        return False
    if outcome.tool_name == "drive.list_files" and not args.get("query"):
        return False
    if outcome.tool_name == "notion.search" and not args.get("query"):
        return False
    return True


def _next_ready(steps: list[PlanStep]) -> PlanStep | None:
    done = {step.key for step in steps if step.status in ("succeeded", "skipped")}
    pending = [step for step in steps if step.status in ("pending", "running")]
    ready = [step for step in pending if all(dep in done for dep in (step.depends_on or []))]
    ready.sort(key=lambda step: step.order_index)
    return ready[0] if ready else None


def _persist_steps(db, plan: Plan, drafts) -> None:
    for step in drafts:
        db.add(
            PlanStep(
                plan_id=plan.id,
                key=step.key,
                title=step.title,
                tool_name=step.tool_name,
                tool_args=dict(step.tool_args or {}),
                depends_on=list(step.depends_on or []),
                status=step.preset or "pending",
                cacheable=bool(step.cacheable),
                order_index=step.order_index,
            )
        )


def _goal_text(goal: Goal) -> str:
    return "\n".join(part.strip() for part in (goal.title, goal.description or "") if part and part.strip())


def _args_hash(args: dict) -> str:
    raw = json.dumps(args or {}, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _idempotency_key(run_id: int, step_key: str, args: dict) -> str:
    return f"{run_id}:{step_key}:{_args_hash(args)}"


def _is_empty(result: dict) -> bool:
    items = result.get("items") if isinstance(result, dict) else None
    return isinstance(items, list) and len(items) == 0


def _snapshot(run: WorkflowRun):
    return SimpleNamespace(
        id=run.id,
        goal_id=run.goal_id,
        status=run.status,
        error=run.error,
        compacted_context=run.compacted_context,
        replan_count=run.replan_count,
        plan_id=run.plan_id,
        idempotency_key=run.idempotency_key,
    )
