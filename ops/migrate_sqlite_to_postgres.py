"""One-time offline migration of SmartSupport business data to PostgreSQL.

LangGraph checkpoints are intentionally excluded. Run this while the API is stopped.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime, func, inspect, select, text


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.database import Base, Database  # noqa: E402


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate SmartSupport business tables to PostgreSQL")
    parser.add_argument("--source", required=True, type=Path, help="Path to the legacy SQLite business database")
    parser.add_argument("--target", required=True, help="postgresql+psycopg:// connection URL")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print row counts without writing")
    return parser.parse_args()


def source_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        if not row[0].startswith("sqlite_")
    }


def target_counts(database: Database) -> dict[str, int]:
    existing = set(inspect(database.engine).get_table_names())
    with database.engine.connect() as connection:
        return {
            table.name: connection.scalar(select(func.count()).select_from(table)) or 0
            for table in Base.metadata.sorted_tables
            if table.name in existing
        }


def converted_row(table, row: sqlite3.Row, common_columns: list[str]) -> dict:
    result = {}
    for name in common_columns:
        value = row[name]
        column = table.c[name]
        if value is not None and isinstance(column.type, DateTime) and isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        result[name] = value
    return result


def reset_sequences(database: Database) -> None:
    with database.engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            for column in table.primary_key.columns:
                if not column.autoincrement:
                    continue
                sequence = connection.scalar(
                    text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                    {"table_name": table.name, "column_name": column.name},
                )
                if sequence:
                    connection.execute(text(
                        f"SELECT setval(:sequence, COALESCE((SELECT MAX(\"{column.name}\") FROM \"{table.name}\"), 1), "
                        f"EXISTS(SELECT 1 FROM \"{table.name}\"))"
                    ), {"sequence": sequence})


def migrate(source: Path, target: str, dry_run: bool) -> dict[str, int]:
    if not source.is_file():
        raise ValueError(f"Source database does not exist: {source}")
    database = Database(target)
    with sqlite3.connect(source) as source_connection:
        source_connection.row_factory = sqlite3.Row
        available = source_tables(source_connection)
        planned = {
            table.name: source_connection.execute(f'SELECT COUNT(*) FROM "{table.name}"').fetchone()[0]
            for table in Base.metadata.sorted_tables
            if table.name in available
        }
        occupied = {name: count for name, count in target_counts(database).items() if count}
        if occupied:
            details = ", ".join(f"{name}={count}" for name, count in sorted(occupied.items()))
            raise RuntimeError(f"Target database is not empty: {details}")
        if dry_run:
            return planned

        database.create_all()
        with database.engine.begin() as target_connection:
            target_connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            for table in Base.metadata.sorted_tables:
                if table.name not in available:
                    continue
                source_columns = {
                    row[1] for row in source_connection.execute(f'PRAGMA table_info("{table.name}")')
                }
                common_columns = [column.name for column in table.columns if column.name in source_columns]
                if not common_columns:
                    continue
                selected_columns = ", ".join(f'"{name}"' for name in common_columns)
                cursor = source_connection.execute(f'SELECT {selected_columns} FROM "{table.name}"')
                while rows := cursor.fetchmany(500):
                    target_connection.execute(
                        table.insert(),
                        [converted_row(table, row, common_columns) for row in rows],
                    )
        reset_sequences(database)
        return planned


def main() -> int:
    options = arguments()
    try:
        counts = migrate(options.source.resolve(), options.target, options.dry_run)
    except (ValueError, RuntimeError, sqlite3.Error) as exc:
        print(f"Migration aborted: {exc}", file=sys.stderr)
        return 1
    mode = "Dry run" if options.dry_run else "Migration complete"
    print(mode)
    for name, count in counts.items():
        print(f"  {name}: {count}")
    print("LangGraph SQLite checkpoints were not migrated; conversation graph state will be rebuilt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
