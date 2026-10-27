from datetime import datetime, timezone

from app.retrieval import embed, search
from app.seed import seed_workspace


def test_embed_is_normalized_and_stable():
    first = embed("navigation proposal for the design review")
    second = embed("navigation proposal for the design review")
    assert first == second
    assert abs(sum(value * value for value in first) - 1) < 1e-6


def test_search_finds_the_navigation_proposal(sessions):
    db = sessions()
    seed_workspace(db, now=datetime(2026, 10, 27, 15, tzinfo=timezone.utc))
    hits = search(db, "navigation proposal for the design review", limit=5)
    titles = [hit["title"] for hit in hits]
    assert "Navigation proposal" in titles
    assert any(hit["title"] == "Navigation proposal" and hit["href"].startswith("/docs/") for hit in hits)
    db.close()
