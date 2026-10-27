import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["REDIS_URL"] = ""
os.environ["VERTEX_SCHEDULER"] = "0"
os.environ["VERTEX_AUTO_SEED"] = "0"
os.environ["VERTEX_LLM_API_KEY"] = ""

import pytest

from app.cache import MemoryCache
from app.db import make_engine, make_session_factory
from app.loop import AgentLoop
from app.models import Base
from app.timeutil import SystemClock
from app.tools import WorkspaceTools


@pytest.fixture
def sessions():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture
def make_loop(sessions):
    def _make(tools=None, compact_after=8):
        cache = MemoryCache()
        workspace = tools or WorkspaceTools()
        loop = AgentLoop(
            sessions,
            cache,
            workspace,
            SystemClock(),
            compact_after=compact_after,
            retry_backoff=0,
        )
        return loop, cache, workspace

    return _make
