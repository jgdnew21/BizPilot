# BizPilot v0.2

BizPilot 是面向中小企业的对话驱动业务操作层，不替代 ERPNext。

## 当前范围
仅实现采购 **MR (Material Request)** 最小闭环：
自然语言 -> 解析/标准化 -> Markdown确认单 -> snapshot -> 确认 -> 创建ERPNext MR。

- MR: 采购需求/计划
- PO: 实际采购订单（预留）
- PR: 实际入库事实（预留）

## API 设计
采用明确单据类型路径，避免 `/purchase/prepare` 语义冲突：
- `POST /api/purchase/material-requests/prepare`
- `POST /api/purchase/material-requests/confirm`

预留：
- `/api/purchase/purchase-orders/*`
- `/api/purchase/purchase-receipts/*`

## 运行服务
```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## 运行测试
```bash
pytest -q
```

## OpenClaw 对接文档

- OpenClaw MR Skill 对接说明：`docs/openclaw_mr_skill.md`
- 端到端调试脚本：`scripts/e2e_mr_flow.sh`

## 配置
见 `.env.example`：ERPNext连接信息、默认仓库别名、snapshot/master data路径。

## 后续扩展
- PO prepare/confirm
- PR prepare/confirm
- PostgreSQL snapshot repository
- ERPNext master data query
- OpenClaw 强类型 plugin/tool
- n8n 编排接入

## 本地验证 MR 最小闭环

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 准备 `.env`

从 `.env.example` 复制：

```bash
cp .env.example .env
```

并配置：

```dotenv
ERPNEXT_BASE_URL=http://site1.localhost:8080
ERPNEXT_API_KEY=your_api_key
ERPNEXT_API_SECRET=your_api_secret
DEFAULT_WAREHOUSE_ALIAS=南宁仓
SNAPSHOT_DIR=data/snapshots
MASTER_DATA_DIR=data/master_data
```

3. 启动服务

```bash
uvicorn app.main:app --reload --port 8000
```

4. 检查服务健康

```bash
curl http://localhost:8000/health
```

5. 检查就绪状态

```bash
curl http://localhost:8000/health/ready
```

6. 检查 ERPNext 连接

```bash
curl http://localhost:8000/health/erpnext
```

7. 调用 MR prepare

```bash
curl -X POST http://localhost:8000/api/purchase/material-requests/prepare \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "wechat_group_001",
    "user_id": "u_001",
    "user_name": "店长张三",
    "text": "后天要买五常大米80斤，嘉木东来寿眉白茶10盒，萌考拉冰淇淋100个，供应商采无忧，入南宁仓"
  }'
```

响应中应返回 `snapshot_id` 和 `markdown_text`。

8. 调用 MR confirm

将上一步返回的 `snapshot_id` 替换进去：

```bash
curl -X POST http://localhost:8000/api/purchase/material-requests/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "wechat_group_001",
    "user_id": "u_001",
    "snapshot_id": "替换为上一步返回的 snapshot_id",
    "confirm_text": "确认"
  }'
```

成功后应返回：

```json
{
  "status": "submitted",
  "erpnext_doc_no": "MAT-MR-..."
}
```


## LLM Extractor

LLM 只负责自然语言字段抽取，不生成 Markdown，不提交 ERPNext。

BizPilot 安全链路：

用户原话
→ LLM 抽取候选字段
→ Pydantic 校验
→ 主数据匹配
→ BusinessValidator
→ Markdown 确认
→ Snapshot
→ 用户确认
→ ERPNext MR

提取策略（v0.2）：
- `ENABLE_LLM_EXTRACTOR=true`：优先使用 LLM 抽取；若 LLM 失败/超时/返回非法结构，将自动回退到规则抽取。
- `ENABLE_LLM_EXTRACTOR=false`：只使用规则抽取。
- 无论 LLM 还是规则抽取，prepare API 始终返回 Markdown 确认单；抽取器元信息会记录到 snapshot（如 `extractor_name`、`extractor_warnings`、`confidence`）。

## 多轮确认单修订策略

- `prepare` 支持可选 `previous_snapshot_id`，用于基于上一版确认单继续修改。
- 每次修改都会生成全新的 snapshot（revision 递增），并记录 `previous_snapshot_id` 引用。
- 基于上一版生成新版本后，上一版若仍处于 `ready_for_confirmation` 或 `pending_confirmation`，会被标记为 `superseded`。
- `confirm` 遇到 `superseded` snapshot 会拒绝提交，并提示“该确认单已有更新版本，请确认最新确认单”。

## Confirm Safety Boundary

confirm 阶段不再调用 AI，不再解析用户文本，只提交用户已确认的 snapshot。

这是 BizPilot “所见即所写”的核心。

## 采购报单入库 MVP

### BizPilot 采购模块当前能力

#### 1. 采购需求链路（采购前）
- 路径：`/api/purchase/material-requests/*`
- 用于“还没买，准备买”的场景，目标是 Material Request。

#### 2. 采购报单入库链路（采购后）
- 路径：`/api/purchase/inbound/prepare` + `/api/purchase/inbound/confirm`
- 用于“已经买了/已到货/要登记入库”，目标是 ERPNext Purchase Receipt Draft。

#### 3. 主数据缓存
- ERPNext 是事实源。
- BizPilot 将 Item/Supplier/Warehouse/UOM 同步到 SQLite 缓存后再做匹配和校验。

#### 4. 本地运行
```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

#### 5. 本地验证命令
```bash
# sync
curl -X POST http://localhost:8000/api/erpnext/sync/master-data

# search
curl "http://localhost:8000/api/master-data/items/search?q=鸡蛋"

# prepare
curl -X POST http://localhost:8000/api/purchase/inbound/prepare -H "Content-Type: application/json" -d '{"session_id":"s1","user_id":"u1","user_name":"测试","source_channel":"wechat","source_type":"text","text":"鲜鸡蛋90斤 4.66元/斤，共419.4元","supplier_name":"市场采购供应商","warehouse":"仓库-华食泰"}'

# confirm
curl -X POST http://localhost:8000/api/purchase/inbound/confirm -H "Content-Type: application/json" -d '{"session_id":"s1","user_id":"u1","confirm_text":"确认入库","snapshot_id":"替换为prepare返回snapshot_id"}'
```

#### 6. 设计原则
- ERPNext 是主数据事实源。
- BizPilot 是业务解释层和确认快照层。
- OpenClaw 是对话入口和意图分流层。
- 所见即所写：Markdown 确认单与 structured payload 一致。
- confirm 必须基于 snapshot。
- 只创建 ERPNext Draft，不直接 submit。

更多细节：
- `docs/master_data_cache.md`
- `docs/purchase_inbound_flow.md`
- `docs/local_validation.md`
