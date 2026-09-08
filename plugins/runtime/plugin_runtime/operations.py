"""Plugin-owned operation journal; the business effect and result commit atomically."""

import hashlib

from sqlalchemy import JSON, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .server import digest


class OperationBase(DeclarativeBase):
    pass


class Operation(OperationBase):
    __tablename__ = "plugin_operations"
    operation_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    tool_id: Mapped[str] = mapped_column(String(200))
    input_digest: Mapped[str] = mapped_column(String(71))
    result: Mapped[dict] = mapped_column(JSON)
    scope_digest: Mapped[str] = mapped_column(String(71))


class Journal:
    def __init__(self, sessions):
        self.sessions = sessions

    def write(self, operation_id, tool_id, arguments, effect, *, scope=None):
        scope_digest = digest(scope or {})
        fingerprint = digest(
            {"toolId": tool_id, "arguments": arguments, "scopeDigest": scope_digest}
        )
        lock = int.from_bytes(
            hashlib.sha256(operation_id.encode()).digest()[:8], "big", signed=True
        )
        with self.sessions.begin() as session:
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
            previous = session.get(Operation, operation_id)
            if previous:
                if previous.input_digest != fingerprint:
                    raise ValueError("operation_input_conflict")
                return previous.result
            result = effect(session)
            session.add(
                Operation(
                    operation_id=operation_id,
                    tool_id=tool_id,
                    input_digest=fingerprint,
                    result=result,
                    scope_digest=scope_digest,
                )
            )
            return result

    def query(self, operation_id, scope=None, grants=None):
        lock = int.from_bytes(
            hashlib.sha256(operation_id.encode()).digest()[:8], "big", signed=True
        )
        with self.sessions.begin() as session:
            available = session.scalar(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": lock}
            )
            if not available:
                return {"status": "unknown", "code": "operation_in_progress"}
            entry = session.get(Operation, operation_id)
            if entry and grants is not None and entry.tool_id not in grants:
                raise ValueError("operation_tool_not_granted")
            if entry and scope is not None and entry.scope_digest != digest(scope):
                raise ValueError("operation_scope_conflict")
            return (
                {"status": "succeeded", "output": entry.result}
                if entry
                else {"status": "not_found"}
            )
