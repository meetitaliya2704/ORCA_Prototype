from sqlalchemy.exc import IntegrityError, OperationalError, TimeoutError

from app.db.errors import sanitize_database_error

SECRET = "postgresql://user:private@secret-host/database"


def test_database_errors_are_sanitized() -> None:
    failures = [
        sanitize_database_error(IntegrityError("insert", {}, RuntimeError(SECRET))),
        sanitize_database_error(OperationalError("connect", {}, RuntimeError(SECRET))),
        sanitize_database_error(TimeoutError(SECRET)),
        sanitize_database_error(RuntimeError(SECRET)),
    ]
    rendered = " ".join(f"{failure.code} {failure.message}" for failure in failures)
    assert "private" not in rendered
    assert "secret-host" not in rendered
    assert failures[0].retryable is False
    assert failures[1].retryable is True
    assert failures[2].retryable is True
