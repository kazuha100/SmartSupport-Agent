import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from sqlalchemy.engine import make_url


BASE_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://smart_support:smart_support_dev@127.0.0.1:5432/smart_support",
    ),
)


def _psycopg_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _admin_url(url: str) -> str:
    parameters = conninfo_to_dict(_psycopg_url(url))
    parameters["dbname"] = "postgres"
    return make_conninfo(**parameters)


def _database_url(url: str, database_name: str) -> str:
    return make_url(url).set(database=database_name).render_as_string(hide_password=False)


def _create_database(database_name: str) -> None:
    with psycopg.connect(_admin_url(BASE_DATABASE_URL), autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))


def _drop_database(database_name: str) -> None:
    with psycopg.connect(_admin_url(BASE_DATABASE_URL), autocommit=True) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
            (database_name,),
        )
        connection.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name)))


API_DATABASE_NAME = f"smart_support_api_test_{uuid4().hex[:10]}"
_create_database(API_DATABASE_NAME)
os.environ["DATABASE_URL"] = _database_url(BASE_DATABASE_URL, API_DATABASE_NAME)
os.environ["EMBEDDING_MODE"] = "disabled"
os.environ["LLM_MODE"] = "mock"


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    _drop_database(API_DATABASE_NAME)


@pytest.fixture
def postgres_database() -> Iterator["Database"]:
    from app.database import Database

    database_name = f"smart_support_test_{uuid4().hex[:12]}"
    _create_database(database_name)
    database = Database(_database_url(BASE_DATABASE_URL, database_name))
    database.create_all()
    try:
        yield database
    finally:
        database.engine.dispose()
        _drop_database(database_name)
