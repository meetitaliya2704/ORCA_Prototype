from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import (
    IntegrityError,
    OperationalError,
    SQLAlchemyError,
    TimeoutError,
)


@dataclass(frozen=True, slots=True)
class SanitizedDatabaseError:
    code: str
    message: str
    retryable: bool


class DatabaseOperationError(RuntimeError):
    """Safe application-facing wrapper that never includes driver details."""

    def __init__(self, failure: SanitizedDatabaseError) -> None:
        super().__init__(failure.message)
        self.code = failure.code
        self.retryable = failure.retryable


class PersistenceNotFoundError(DatabaseOperationError):
    def __init__(self, entity: str) -> None:
        super().__init__(
            SanitizedDatabaseError(
                code="PERSISTENCE_RECORD_NOT_FOUND",
                message=f"The requested {entity} record was not found",
                retryable=False,
            )
        )


class PersistenceValidationError(DatabaseOperationError):
    def __init__(self, message: str) -> None:
        super().__init__(
            SanitizedDatabaseError(
                code="PERSISTENCE_VALIDATION_FAILED",
                message=message,
                retryable=False,
            )
        )


def sanitize_database_error(exc: BaseException) -> SanitizedDatabaseError:
    if isinstance(exc, IntegrityError):
        return SanitizedDatabaseError(
            code="DATABASE_CONSTRAINT_VIOLATION",
            message="The persistence operation conflicts with stored data",
            retryable=False,
        )
    if isinstance(exc, TimeoutError):
        return SanitizedDatabaseError(
            code="DATABASE_TIMEOUT",
            message="The persistence service timed out",
            retryable=True,
        )
    if isinstance(exc, OperationalError):
        return SanitizedDatabaseError(
            code="DATABASE_UNAVAILABLE",
            message="The persistence service is temporarily unavailable",
            retryable=True,
        )
    if isinstance(exc, SQLAlchemyError):
        return SanitizedDatabaseError(
            code="DATABASE_OPERATION_FAILED",
            message="The persistence operation could not be completed",
            retryable=False,
        )
    return SanitizedDatabaseError(
        code="DATABASE_OPERATION_FAILED",
        message="The persistence operation could not be completed",
        retryable=False,
    )
