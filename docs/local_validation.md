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
见 `docs/purchase_inbound_flow.md` 中 prepare 示例。

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
