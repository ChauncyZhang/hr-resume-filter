import os
import subprocess

import pytest
from sqlalchemy import create_engine, inspect


TABLES = {"organizations", "departments", "users", "user_roles", "user_sessions", "jobs", "job_collaborators", "audit_logs"}


@pytest.mark.skipif(not os.getenv("POSTGRES_SMOKE_URL"), reason="PostgreSQL smoke URL not configured")
def test_migration_upgrades_and_downgrades_empty_baseline() -> None:
    url = os.environ["POSTGRES_SMOKE_URL"]
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(["python", "-m", "alembic", "-c", "server/alembic.ini", "upgrade", "head"], check=True, env=env)
    sync_url = url.replace("+asyncpg", "+psycopg")
    engine = create_engine(sync_url)
    assert TABLES <= set(inspect(engine).get_table_names())
    subprocess.run(["python", "-m", "alembic", "-c", "server/alembic.ini", "downgrade", "base"], check=True, env=env)
    assert not (TABLES & set(inspect(engine).get_table_names()))

