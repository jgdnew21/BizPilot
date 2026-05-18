import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class MasterDataCacheRepository:
    """SQLite-backed cache for ERPNext master data snapshots."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS erpnext_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_code TEXT NOT NULL UNIQUE,
                    item_name TEXT,
                    item_group TEXT,
                    stock_uom TEXT,
                    disabled INTEGER,
                    is_stock_item INTEGER,
                    description TEXT,
                    erp_modified TEXT,
                    synced_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS erpnext_suppliers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    supplier TEXT NOT NULL UNIQUE,
                    supplier_name TEXT,
                    supplier_group TEXT,
                    disabled INTEGER,
                    erp_modified TEXT,
                    synced_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS erpnext_warehouses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    warehouse TEXT NOT NULL UNIQUE,
                    warehouse_name TEXT,
                    company TEXT,
                    is_group INTEGER,
                    disabled INTEGER,
                    erp_modified TEXT,
                    synced_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS erpnext_uoms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uom TEXT NOT NULL UNIQUE,
                    enabled INTEGER,
                    erp_modified TEXT,
                    synced_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );
                """
            )

    def upsert_items(self, rows: list[dict[str, Any]]) -> int:
        synced_at = self._now()
        payload = []
        for row in rows:
            item_code = row.get("item_code") or row.get("name")
            if not item_code:
                continue
            payload.append(
                (
                    item_code,
                    row.get("item_name"),
                    row.get("item_group"),
                    row.get("stock_uom"),
                    self._bool_to_int(row.get("disabled")),
                    self._bool_to_int(row.get("is_stock_item")),
                    row.get("description"),
                    row.get("modified"),
                    synced_at,
                    self._dump(row),
                )
            )
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO erpnext_items (
                    item_code, item_name, item_group, stock_uom, disabled,
                    is_stock_item, description, erp_modified, synced_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_code) DO UPDATE SET
                    item_name=excluded.item_name,
                    item_group=excluded.item_group,
                    stock_uom=excluded.stock_uom,
                    disabled=excluded.disabled,
                    is_stock_item=excluded.is_stock_item,
                    description=excluded.description,
                    erp_modified=excluded.erp_modified,
                    synced_at=excluded.synced_at,
                    raw_json=excluded.raw_json
                """,
                payload,
            )
        return len(payload)

    def upsert_suppliers(self, rows: list[dict[str, Any]]) -> int:
        synced_at = self._now()
        payload = []
        for row in rows:
            supplier = row.get("name") or row.get("supplier_name")
            if not supplier:
                continue
            payload.append(
                (
                    supplier,
                    row.get("supplier_name") or row.get("name"),
                    row.get("supplier_group"),
                    self._bool_to_int(row.get("disabled")),
                    row.get("modified"),
                    synced_at,
                    self._dump(row),
                )
            )
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO erpnext_suppliers (
                    supplier, supplier_name, supplier_group, disabled,
                    erp_modified, synced_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(supplier) DO UPDATE SET
                    supplier_name=excluded.supplier_name,
                    supplier_group=excluded.supplier_group,
                    disabled=excluded.disabled,
                    erp_modified=excluded.erp_modified,
                    synced_at=excluded.synced_at,
                    raw_json=excluded.raw_json
                """,
                payload,
            )
        return len(payload)

    def upsert_warehouses(self, rows: list[dict[str, Any]]) -> int:
        synced_at = self._now()
        payload = []
        for row in rows:
            warehouse = row.get("name") or row.get("warehouse_name")
            if not warehouse:
                continue
            payload.append(
                (
                    warehouse,
                    row.get("warehouse_name") or row.get("name"),
                    row.get("company"),
                    self._bool_to_int(row.get("is_group")),
                    self._bool_to_int(row.get("disabled")),
                    row.get("modified"),
                    synced_at,
                    self._dump(row),
                )
            )
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO erpnext_warehouses (
                    warehouse, warehouse_name, company, is_group, disabled,
                    erp_modified, synced_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(warehouse) DO UPDATE SET
                    warehouse_name=excluded.warehouse_name,
                    company=excluded.company,
                    is_group=excluded.is_group,
                    disabled=excluded.disabled,
                    erp_modified=excluded.erp_modified,
                    synced_at=excluded.synced_at,
                    raw_json=excluded.raw_json
                """,
                payload,
            )
        return len(payload)

    def upsert_uoms(self, rows: list[dict[str, Any]]) -> int:
        synced_at = self._now()
        payload = []
        for row in rows:
            uom = row.get("name")
            if not uom:
                continue
            payload.append((uom, self._bool_to_int(row.get("enabled")), row.get("modified"), synced_at, self._dump(row)))
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO erpnext_uoms (uom, enabled, erp_modified, synced_at, raw_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(uom) DO UPDATE SET
                    enabled=excluded.enabled,
                    erp_modified=excluded.erp_modified,
                    synced_at=excluded.synced_at,
                    raw_json=excluded.raw_json
                """,
                payload,
            )
        return len(payload)

    def count(self, table_name: str) -> int:
        allowed_tables = {"erpnext_items", "erpnext_suppliers", "erpnext_warehouses", "erpnext_uoms"}
        if table_name not in allowed_tables:
            raise ValueError(f"Unsupported master data cache table: {table_name}")
        with self._connect() as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    def _dump(self, row: dict[str, Any]) -> str:
        return json.dumps(row, ensure_ascii=False, sort_keys=True)

    def _bool_to_int(self, value: Any) -> int | None:
        if value is None:
            return None
        return int(bool(value))
