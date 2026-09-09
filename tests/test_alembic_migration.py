from io import StringIO

from alembic.config import Config

from alembic import command


def migration_sql(revision: str, *, downgrade: bool = False) -> str:
    output = StringIO()
    configuration = Config("alembic.ini", output_buffer=output)
    if downgrade:
        command.downgrade(configuration, revision, sql=True)
    else:
        command.upgrade(configuration, revision, sql=True)
    return output.getvalue()


def test_initial_migration_uses_required_postgresql_types() -> None:
    sql = migration_sql("head")
    for table in (
        "conversations",
        "messages",
        "assistant_runs",
        "evidence_snapshots",
    ):
        assert f"CREATE TABLE {table}" in sql
    assert " UUID " in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert sql.count("JSONB NOT NULL") == 3


def test_downgrade_only_removes_owned_tables() -> None:
    sql = migration_sql("20260908_0001:base", downgrade=True)
    dropped = {
        line.removeprefix("DROP TABLE ").removesuffix(";")
        for line in sql.splitlines()
        if line.startswith("DROP TABLE ")
    }
    assert dropped == {
        "alembic_version",
        "conversations",
        "messages",
        "assistant_runs",
        "evidence_snapshots",
    }
