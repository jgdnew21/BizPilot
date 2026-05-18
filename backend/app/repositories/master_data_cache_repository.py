from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from app.core.config import DATABASE_URL


def _bool_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


class MasterDataCacheRepository:
    """Persistence boundary for ERPNext master-data cache tables."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or DATABASE_URL
        self.is_sqlite = self.database_url.startswith("sqlite:///") or self.database_url == "sqlite:///:memory:"
        self.is_postgres = self.database_url.startswith("postgresql://") or self.database_url.startswith("postgres://")
        if not self.is_sqlite and not self.is_postgres:
            raise ValueError("DATABASE_URL must start with sqlite:///, postgresql://, or postgres://")
        if self.is_sqlite:
            self.db_path = self._sqlite_path(self.database_url)
            if self.db_path != ":memory:":
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        else:
            self.db_path = ""

    @staticmethod
    def _sqlite_path(database_url: str) -> str:
        if database_url == "sqlite:///:memory:":
            return ":memory:"
        return database_url.removeprefix("sqlite:///")

    def connect(self):  # type: ignore[no-untyped-def]
        if self.is_sqlite:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError as exc:
            raise ValueError("PostgreSQL DATABASE_URL requires psycopg2-binary to be installed") from exc
        return psycopg2.connect(self.database_url, cursor_factory=psycopg2.extras.RealDictCursor)

    def init_schema(self) -> None:
        if self.is_sqlite:
            schema = """
            create table if not exists erpnext_item_cache (
              id integer primary key autoincrement,
              item_code text not null unique,
              item_name text,
              item_group text,
              stock_uom text,
              disabled integer,
              is_stock_item integer,
              description text,
              erp_modified text,
              synced_at text not null,
              raw_json text not null
            );

            create table if not exists erpnext_supplier_cache (
              id integer primary key autoincrement,
              supplier text not null unique,
              supplier_name text,
              supplier_group text,
              disabled integer,
              erp_modified text,
              synced_at text not null,
              raw_json text not null
            );

            create table if not exists erpnext_warehouse_cache (
              id integer primary key autoincrement,
              warehouse text not null unique,
              warehouse_name text,
              company text,
              is_group integer,
              disabled integer,
              erp_modified text,
              synced_at text not null,
              raw_json text not null
            );

            create table if not exists erpnext_uom_cache (
              id integer primary key autoincrement,
              uom text not null unique,
              enabled integer,
              erp_modified text,
              synced_at text not null,
              raw_json text not null
            );
            """
        else:
            schema = """
            create table if not exists erpnext_item_cache (
              id bigserial primary key,
              item_code varchar(255) not null unique,
              item_name varchar(255),
              item_group varchar(255),
              stock_uom varchar(100),
              disabled boolean,
              is_stock_item boolean,
              description text,
              erp_modified varchar(64),
              synced_at timestamptz not null,
              raw_json jsonb not null
            );

            create table if not exists erpnext_supplier_cache (
              id bigserial primary key,
              supplier varchar(255) not null unique,
              supplier_name varchar(255),
              supplier_group varchar(255),
              disabled boolean,
              erp_modified varchar(64),
              synced_at timestamptz not null,
              raw_json jsonb not null
            );

            create table if not exists erpnext_warehouse_cache (
              id bigserial primary key,
              warehouse varchar(255) not null unique,
              warehouse_name varchar(255),
              company varchar(255),
              is_group boolean,
              disabled boolean,
              erp_modified varchar(64),
              synced_at timestamptz not null,
              raw_json jsonb not null
            );

            create table if not exists erpnext_uom_cache (
              id bigserial primary key,
              uom varchar(255) not null unique,
              enabled boolean,
              erp_modified varchar(64),
              synced_at timestamptz not null,
              raw_json jsonb not null
            );
            """
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(schema) if self.is_postgres else cur.executescript(schema)
            conn.commit()

    def count(self, model: Any) -> int:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(f"select count(*) as count from {model.__tablename__}")
            row = cur.fetchone()
            return int(row["count"])

    def fetch_one_by_key(self, table: str, key_column: str, key_value: str) -> dict[str, Any] | None:
        placeholder = "%s" if self.is_postgres else "?"
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(f"select * from {table} where {key_column} = {placeholder}", (key_value,))
            row = cur.fetchone()
        return dict(row) if row else None

    def upsert_items(self, rows: Iterable[dict[str, Any]]) -> int:
        return self._upsert_many(
            rows=rows,
            table="erpnext_item_cache",
            key_column="item_code",
            columns=["item_code", "item_name", "item_group", "stock_uom", "disabled", "is_stock_item", "description", "erp_modified", "synced_at", "raw_json"],
            mapper=lambda row: {
                "item_code": row.get("item_code") or row.get("name"),
                "item_name": row.get("item_name"),
                "item_group": row.get("item_group"),
                "stock_uom": row.get("stock_uom"),
                "disabled": _bool_or_none(row.get("disabled")),
                "is_stock_item": _bool_or_none(row.get("is_stock_item")),
                "description": row.get("description"),
                "erp_modified": row.get("modified"),
                "raw_json": self._json_value(row),
            },
        )

    def upsert_suppliers(self, rows: Iterable[dict[str, Any]]) -> int:
        return self._upsert_many(
            rows=rows,
            table="erpnext_supplier_cache",
            key_column="supplier",
            columns=["supplier", "supplier_name", "supplier_group", "disabled", "erp_modified", "synced_at", "raw_json"],
            mapper=lambda row: {
                "supplier": row.get("name") or row.get("supplier_name"),
                "supplier_name": row.get("supplier_name") or row.get("name"),
                "supplier_group": row.get("supplier_group"),
                "disabled": _bool_or_none(row.get("disabled")),
                "erp_modified": row.get("modified"),
                "raw_json": self._json_value(row),
            },
        )

    def upsert_warehouses(self, rows: Iterable[dict[str, Any]]) -> int:
        return self._upsert_many(
            rows=rows,
            table="erpnext_warehouse_cache",
            key_column="warehouse",
            columns=["warehouse", "warehouse_name", "company", "is_group", "disabled", "erp_modified", "synced_at", "raw_json"],
            mapper=lambda row: {
                "warehouse": row.get("name") or row.get("warehouse_name"),
                "warehouse_name": row.get("warehouse_name") or row.get("name"),
                "company": row.get("company"),
                "is_group": _bool_or_none(row.get("is_group")),
                "disabled": _bool_or_none(row.get("disabled")),
                "erp_modified": row.get("modified"),
                "raw_json": self._json_value(row),
            },
        )

    def upsert_uoms(self, rows: Iterable[dict[str, Any]]) -> int:
        return self._upsert_many(
            rows=rows,
            table="erpnext_uom_cache",
            key_column="uom",
            columns=["uom", "enabled", "erp_modified", "synced_at", "raw_json"],
            mapper=lambda row: {
                "uom": row.get("name"),
                "enabled": _bool_or_none(row.get("enabled")),
                "erp_modified": row.get("modified"),
                "raw_json": self._json_value(row),
            },
        )

    def _json_value(self, row: dict[str, Any]) -> Any:
        if self.is_postgres:
            try:
                import psycopg2.extras
            except ImportError as exc:
                raise ValueError("PostgreSQL DATABASE_URL requires psycopg2-binary to be installed") from exc
            return psycopg2.extras.Json(row)
        return json.dumps(row, ensure_ascii=False)

    def _upsert_many(
        self,
        rows: Iterable[dict[str, Any]],
        table: str,
        key_column: str,
        columns: list[str],
        mapper: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        placeholder = "%s" if self.is_postgres else "?"
        placeholders = ", ".join(placeholder for _ in columns)
        update_columns = [column for column in columns if column != key_column]
        update_sql = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
        sql = (
            f"insert into {table} ({', '.join(columns)}) values ({placeholders}) "
            f"on conflict({key_column}) do update set {update_sql}"
        )
        upserted = 0
        with self.connect() as conn:
            cur = conn.cursor()
            for row in rows:
                values = mapper(row)
                if not values.get(key_column):
                    continue
                values["synced_at"] = now
                cur.execute(sql, tuple(values.get(column) for column in columns))
                upserted += 1
            conn.commit()
        return upserted
