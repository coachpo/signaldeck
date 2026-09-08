"""Project only stable application failure codes out of Temporal exception chains."""

import re

from temporalio.exceptions import ApplicationError

_CODE = re.compile(r"[a-z][a-z0-9_]{0,99}\Z")


def failure_code(error: BaseException, fallback: str) -> str:
    cause: BaseException | None = error
    for _ in range(16):
        if cause is None:
            break
        if isinstance(cause, ApplicationError) and _CODE.fullmatch(cause.message):
            return cause.message
        cause = cause.__cause__
    return fallback
