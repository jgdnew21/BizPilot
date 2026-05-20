# 本地验证手册

## 1) 环境变量
`.env` 至少包含：
- `ERPNEXT_BASE_URL`
- `ERPNEXT_API_KEY`
- `ERPNEXT_API_SECRET`
- `ERPNEXT_COMPANY`
- `DEFAULT_PURCHASE_WAREHOUSE`
- `DEFAULT_PURCHASE_SUPPLIER`
- `MASTER_DATA_CACHE_DB`
- `SNAPSHOT_DIR`

## 2) 启动
```bash
uvicorn app.main:app --reload --port 8000
```

## 3) 验证 ERPNext API Key
```bash
curl -i \
  -H "Authorization: token $ERPNEXT_API_KEY:$ERPNEXT_API_SECRET" \
  "$ERPNEXT_BASE_URL/api/resource/Item?fields=[\"name\"]&limit_page_length=1"
```

## 4) 同步主数据
```bash
curl -X POST http://localhost:8000/api/erpnext/sync/master-data
```

## 5) 检查 SQLite 缓存
```bash
sqlite3 data/master_data_cache.sqlite3 ".tables"
sqlite3 data/master_data_cache.sqlite3 "SELECT COUNT(*) FROM erpnext_items;"
sqlite3 data/master_data_cache.sqlite3 "SELECT COUNT(*) FROM erpnext_suppliers;"
sqlite3 data/master_data_cache.sqlite3 "SELECT COUNT(*) FROM erpnext_warehouses;"
sqlite3 data/master_data_cache.sqlite3 "SELECT COUNT(*) FROM erpnext_uoms;"
```

## 6) 搜索主数据
```bash
curl "http://localhost:8000/api/master-data/items/search?q=鸡蛋"
curl "http://localhost:8000/api/master-data/suppliers/search?q=市场"
curl "http://localhost:8000/api/master-data/warehouses/search?q=仓库"
curl "http://localhost:8000/api/master-data/uoms/search?q=斤"
```

## 7) 测试采购报单 prepare
```bash
curl -X POST http://localhost:8000/api/purchase/inbound/prepare \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "debug-inbound-text-001",
    "user_id": "debug",
    "user_name": "debug",
    "source_channel": "debug",
    "source_type": "text",
    "text": "我今天买了大头鱼 5千克，单价 12.5元，供应商 其它"
  }'
```

兼容 `raw_text` 的历史验证：

```bash
curl -X POST http://localhost:8000/api/purchase/inbound/prepare \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "debug-inbound-raw-text-001",
    "user_id": "debug",
    "user_name": "debug",
    "source_channel": "debug",
    "source_type": "text",
    "raw_text": "我今天买了大头鱼 5千克，单价 12.5元，供应商 其它"
  }'
```

说明：
- OpenClaw 推荐传 `text`。
- Backend 兼容 `raw_text` 是为了容错和历史兼容。
- snapshot 中统一保留 `raw_text` 作为追溯字段。

## 8) 测试采购报单 confirm
见 `docs/purchase_inbound_flow.md` 中 confirm 示例。

## 9) ERPNext 中验证
- confirm 成功后，应在 Purchase Receipt 中看到 Draft。
- 该单据不应自动 submit。

## 10) 常见错误
- ERPNext 401 AuthenticationError
- ERPNext 403 PermissionError
- localhost / host.docker.internal 访问问题
- SQLite 表不存在
- 缓存为空
- 商品匹配 ambiguous
- UOM 不存在
- 仓库不存在
- 供应商不存在
- 重复 confirm 不应重复创建 Purchase Receipt

## 11) 采购报单主数据匹配诊断日志
当 prepare 阶段提示商品、供应商、仓库或单位找不到，但确认 SQLite 中已有数据时，可在 `.env` 打开：

```env
BIZPILOT_DEBUG_PURCHASE_INBOUND=true
BIZPILOT_DEBUG_MASTER_DATA_MATCH=true
BIZPILOT_DEBUG_SQLITE_CACHE=true
```

默认值均为 `false`，仅在排查时开启。

重启 Backend：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

测试：

```bash
curl -X POST http://localhost:8000/api/purchase/inbound/prepare \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "debug-cache-001",
    "user_id": "debug",
    "user_name": "debug",
    "source_channel": "debug",
    "source_type": "text",
    "text": "我今天买了大头鱼 1千克，单价 12.5元，供应商 其它"
  }'
```

重点查看日志：

- `[sqlite-cache-debug] MASTER_DATA_CACHE_DB ...`
- `[sqlite-cache-debug] table_counts ...`
- `[master-data-match-debug] match_item ...`
- `[master-data-match-debug] match_supplier ...`
- `[purchase-inbound-debug] validation error ...`
