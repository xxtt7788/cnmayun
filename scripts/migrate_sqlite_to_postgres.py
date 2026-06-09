from __future__ import annotations

import argparse
from collections.abc import Iterable

from sqlalchemy import create_engine, select, text

import app.models  # noqa: F401 - populate SQLAlchemy metadata before migration
from app.db import Base


def batched(iterable: Iterable[dict], size: int) -> Iterable[list[dict]]:
    batch: list[dict] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def reset_postgres_sequences(connection) -> None:
    for table in Base.metadata.sorted_tables:
        if "id" not in table.c:
            continue
        connection.execute(
            text(
                """
                SELECT setval(
                    pg_get_serial_sequence(:table_name, 'id'),
                    COALESCE((SELECT MAX(id) FROM {table_name}), 1),
                    true
                )
                """.format(table_name=table.name)
            ),
            {"table_name": table.name},
        )


def migrate(source_url: str, target_url: str, batch_size: int, truncate: bool) -> None:
    source_engine = create_engine(source_url, future=True)
    target_engine = create_engine(target_url, future=True)

    Base.metadata.create_all(target_engine)

    with source_engine.connect() as source_conn, target_engine.begin() as target_conn:
        if truncate:
            for table in reversed(Base.metadata.sorted_tables):
                target_conn.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))

        for table in Base.metadata.sorted_tables:
            rows = source_conn.execute(select(table)).mappings()
            copied = 0
            for chunk in batched((dict(row) for row in rows), batch_size):
                target_conn.execute(table.insert(), chunk)
                copied += len(chunk)
            print(f"{table.name}: copied {copied} rows")

        reset_postgres_sequences(target_conn)


def main() -> None:
    parser = argparse.ArgumentParser(description="将本地 SQLite 数据迁移到 PostgreSQL")
    parser.add_argument("--source", required=True, help="源数据库 URL，例如 sqlite:///./data/china_succession.db")
    parser.add_argument("--target", required=True, help="目标数据库 URL，例如 postgresql+psycopg://user:pass@host:5432/db")
    parser.add_argument("--batch-size", type=int, default=1000, help="每批写入行数")
    parser.add_argument("--truncate", action="store_true", help="迁移前清空目标库")
    args = parser.parse_args()

    if not args.source.startswith("sqlite"):
        raise SystemExit("source 必须是 SQLite URL")
    if "postgresql" not in args.target:
        raise SystemExit("target 必须是 PostgreSQL URL")

    migrate(args.source, args.target, args.batch_size, args.truncate)
    print("迁移完成")


if __name__ == "__main__":
    main()
