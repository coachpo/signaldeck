from __future__ import annotations

from collections.abc import Collection

from sqlalchemy.exc import IntegrityError

_POSTGRES_UNIQUE_VIOLATION_SQLSTATE = "23505"


def is_unique_constraint_violation(
    exc: IntegrityError,
    constraint_names: Collection[str],
) -> bool:
    sqlstate = _integrity_error_sqlstate(exc)
    if sqlstate is not None and sqlstate != _POSTGRES_UNIQUE_VIOLATION_SQLSTATE:
        return False

    constraint_name = _integrity_error_constraint_name(exc)
    if constraint_name is not None:
        return constraint_name in constraint_names

    message = str(exc.orig)
    return any(name in message for name in constraint_names)


def _integrity_error_sqlstate(exc: IntegrityError) -> str | None:
    raw_sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
    return raw_sqlstate if isinstance(raw_sqlstate, str) else None


def _integrity_error_constraint_name(exc: IntegrityError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    raw_constraint_name = getattr(diag, "constraint_name", None)
    return raw_constraint_name if isinstance(raw_constraint_name, str) else None
