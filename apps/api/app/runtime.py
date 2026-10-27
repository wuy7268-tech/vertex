from app.cache import make_cache
from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.llm import LLMClient
from app.loop import AgentLoop
from app.scheduler import Scheduler
from app.timeutil import SystemClock
from app.tools import ToolRouter, WorkspaceTools

settings = get_settings()
engine = make_engine(settings.database_url)
SessionLocal = make_session_factory(engine)
cache = make_cache(settings.redis_url)
clock = SystemClock()
llm = LLMClient(settings, cache)
tools = ToolRouter(WorkspaceTools(llm))
agent = AgentLoop(SessionLocal, cache, tools, clock, llm)
scheduler = Scheduler(SessionLocal, agent, clock)
