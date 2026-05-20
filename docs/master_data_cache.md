# 主数据缓存说明（采购报单入库 MVP）

## 1. 设计目标
- ERPNext 是 Item / Supplier / Warehouse / UOM 的主数据事实源。
- BizPilot 将主数据同步到本地缓存，仅用于搜索、匹配、校验。
- 采购报单 `prepare` 阶段只读缓存，避免高频直连 ERPNext。

## 2. 当前缓存实现
- 当前配置：`MASTER_DATA_CACHE_DB=data/master_data_cache.sqlite3`
- 实现形态：本地 SQLite（MVP）。
- 后续可替换为 PostgreSQL，但应保持 service/repository 接口稳定。

## 3. 缓存表
- `erpnext_items`：`item_code`、`item_name`、`stock_uom`、`disabled`、`is_stock_item`、`erp_modified`、`raw_json`。
- `erpnext_suppliers`：`supplier`、`supplier_name`、`disabled`、`erp_modified`、`raw_json`。
- `erpnext_warehouses`：`warehouse`、`warehouse_name`、`company`、`is_group`、`disabled`、`raw_json`。
- `erpnext_uoms`：`uom`、`enabled`、`erp_modified`、`raw_json`。

## 4. 同步接口
- `POST /api/erpnext/sync/master-data`
- `POST /api/erpnext/sync/items`
- `POST /api/erpnext/sync/suppliers`
- `POST /api/erpnext/sync/warehouses`
- `POST /api/erpnext/sync/uoms`

## 5. 搜索接口
- `GET /api/master-data/items/search?q=鸡蛋`
- `GET /api/master-data/suppliers/search?q=市场`
- `GET /api/master-data/warehouses/search?q=仓库`
- `GET /api/master-data/uoms/search?q=斤`

## 6. 本地验证命令
```bash
curl -X POST http://localhost:8000/api/erpnext/sync/master-data
sqlite3 data/master_data_cache.sqlite3 ".tables"
sqlite3 data/master_data_cache.sqlite3 "SELECT COUNT(*) FROM erpnext_items;"
curl "http://localhost:8000/api/master-data/items/search?q=鸡蛋"
```

## 7. 常见问题
- 401 AuthenticationError：检查 ERPNext API Key / Secret 是否正确。
- 表不存在：当前是 SQLite，不是 PostgreSQL；检查 `data/master_data_cache.sqlite3`。
- 搜索不到商品：先执行 master-data sync，确认 ERPNext Item 未禁用。
- 仓库搜不到：ERPNext 仓库常含公司后缀/缩写，请按真实名称匹配。
- UOM 搜不到：请先在 ERPNext 维护对应单位。
