"""Transaction-scoped identity serialization for concurrent immutable inserts."""

from sqlalchemy import text
from sqlalchemy.orm import Session


def lock_identity(session: Session, identity: str) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
        {"identity": identity},
    )
