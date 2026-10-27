import hashlib
import math
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CalendarEvent, Chunk, Document, GitHubItem, Message, Task

DIM = 256
_TOKEN = re.compile(r"[a-z0-9]+")
_SYNONYMS = {
    "mail": ("email", "inbox"),
    "email": ("mail", "inbox"),
    "inbox": ("email", "mail"),
    "meeting": ("calendar", "agenda"),
    "calendar": ("meeting", "agenda"),
    "agenda": ("calendar", "meeting"),
    "doc": ("document",),
    "docs": ("document",),
    "document": ("docs",),
    "documents": ("docs",),
    "pr": ("pull", "request"),
    "issue": ("github",),
    "github": ("issue", "pr"),
}


def _tokens(text: str) -> list[str]:
    tokens = _TOKEN.findall(text.lower())
    expanded = list(tokens)
    for token in tokens:
        expanded.extend(_SYNONYMS.get(token, ()))
    return expanded


def embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    tokens = _tokens(text)
    if not tokens:
        return vec
    for token in tokens:
        digest = hashlib.sha256(token.encode()).digest()
        idx = int.from_bytes(digest[:4], "little") % DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    for left, right in zip(tokens, tokens[1:]):
        digest = hashlib.sha256(f"{left}_{right}".encode()).digest()
        idx = int.from_bytes(digest[:4], "little") % DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign * 0.5
    norm = math.sqrt(sum(value * value for value in vec)) or 1.0
    return [value / norm for value in vec]


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def split_chunks(text: str, size: int = 700) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    if len(cleaned) <= size:
        return [cleaned]
    parts: list[str] = []
    start = 0
    while start < len(cleaned):
        parts.append(cleaned[start : start + size])
        if start + size >= len(cleaned):
            break
        start += size - 80
    return parts


def index_record(
    db: Session,
    *,
    origin: str,
    source_type: str,
    source_id: int,
    title: str,
    text: str,
) -> None:
    db.query(Chunk).filter(Chunk.source_type == source_type, Chunk.source_id == source_id).delete()
    for part in split_chunks(text):
        db.add(
            Chunk(
                origin=origin,
                source_type=source_type,
                source_id=source_id,
                title=title,
                text=part,
                embedding=embed(f"{title}. {part}"),
            )
        )


def reindex(db: Session) -> int:
    db.query(Chunk).delete()
    count = 0
    for doc in db.scalars(select(Document)).all():
        index_record(
            db,
            origin=doc.source,
            source_type="document",
            source_id=doc.id,
            title=doc.title,
            text=doc.content,
        )
        count += 1
    for message in db.scalars(select(Message)).all():
        index_record(
            db,
            origin="gmail",
            source_type="message",
            source_id=message.id,
            title=message.subject,
            text=f"{message.sender_name} {message.subject} {message.body}",
        )
        count += 1
    for item in db.scalars(select(GitHubItem)).all():
        index_record(
            db,
            origin="github",
            source_type="github",
            source_id=item.id,
            title=item.title,
            text=f"{item.repo} {item.kind} {item.title} {item.body}",
        )
        count += 1
    for event in db.scalars(select(CalendarEvent)).all():
        names = " ".join(person.get("name", "") for person in event.attendees or [])
        index_record(
            db,
            origin="google_calendar",
            source_type="calendar",
            source_id=event.id,
            title=event.title,
            text=f"{event.title} {event.description} {event.location} {names}",
        )
        count += 1
    for task in db.scalars(select(Task)).all():
        index_record(
            db,
            origin="task",
            source_type="task",
            source_id=task.id,
            title=task.title,
            text=f"{task.title} {task.description}",
        )
        count += 1
    return count


def search(db: Session, query: str, limit: int = 8) -> list[dict]:
    query_vec = embed(query)
    best: dict[tuple[str, int], tuple[float, Chunk]] = {}
    for row in db.scalars(select(Chunk)).all():
        score = cosine(query_vec, row.embedding or [])
        title_l = row.title.lower()
        query_l = query.lower().strip()
        if query_l and title_l == query_l:
            score += 0.55
        elif query_l and (query_l in title_l or title_l in query_l):
            score += 0.08
        key = (row.source_type, row.source_id)
        current = best.get(key)
        if current is None or score > current[0]:
            best[key] = (score, row)
    ranked = sorted(best.values(), key=lambda item: item[0], reverse=True)
    results = []
    for score, row in ranked:
        if score < 0.08:
            continue
        results.append(
            {
                "title": row.title,
                "snippet": row.text[:220],
                "score": round(score, 3),
                "origin": row.origin,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "href": _href(row.source_type, row.source_id),
            }
        )
        if len(results) >= limit:
            break
    return results


def _href(source_type: str, source_id: int) -> str:
    if source_type == "document":
        return f"/docs/{source_id}"
    if source_type == "message":
        return f"/inbox/{source_id}"
    if source_type == "github":
        return "/github"
    if source_type == "calendar":
        return "/calendar"
    if source_type == "task":
        return "/tasks"
    return "/"
