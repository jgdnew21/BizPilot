# 采购报单入库流程说明（MVP）

## 1. 业务语义
- 采购需求（Material Request）：还没买，准备买。
- 采购报单入库（Purchase Inbound）：已经买了/到货了，要登记入库。

## 2. 当前流程
用户报单文本/图片候选
→ `POST /api/purchase/inbound/prepare`
→ 解析报单
→ 缓存匹配商品/供应商/仓库/UOM
→ 生成 Markdown 确认单
→ 保存 snapshot
→ 用户确认入库
→ `POST /api/purchase/inbound/confirm`
→ 读取 snapshot
→ 创建 ERPNext Purchase Receipt Draft
→ 返回 ERPNext 单号

## 3. prepare 阶段
- 接收用户报单。
- 可解析自然语言或固定格式文本。
- 生成 `structured_payload`。
- 做主数据匹配与金额校验。
- 生成 Markdown 确认单。
- 保存 snapshot。
- **不写 ERPNext**。

## 4. confirm 阶段
- **必须基于 snapshot**。
- 不允许重新解析 `raw_text`。
- 不允许重新调用 LLM 生成新 payload。
- 不允许自动替换商品。
- 仅做轻量结构校验。
- 创建 ERPNext Purchase Receipt **Draft**。
- 不自动 submit。

## 5. Snapshot 价值
Snapshot 是“用户确认内容”和“ERP 写入内容”的一致性桥梁，保障“所见即所写”。

关键字段：
`snapshot_id`、`session_id`、`user_id`、`user_name`、`source_channel`、`source_type`、`raw_text`、`raw_supplier_name`、`erp_supplier_name`、`warehouse`、`markdown_text`、`structured_payload`、`validation_result`、`status`、`erp_purchase_receipt_name`、`created_at`、`confirmed_at`、`submitted_at`、`error_message`。

## 6. Markdown 示例
```md
# 采购入库确认单（待确认）

来源：微信文字报单
供应商：市场采购供应商
入库仓库：仓库-华食泰
状态：待确认

| # | 报单商品 | ERP商品 | 数量 | 单位 | 单价 | 金额 | 状态 |
|---|---|---|---:|---|---:|---:|---|
| 1 | 鲜鸡蛋 | 鲜鸡蛋 | 90 | 斤 | 4.66 | 419.40 | 已匹配 |
| 2 | 土鸡蛋 | 土鸡蛋 | 35 | 斤 | 5.14 | 179.90 | 已匹配 |

报单合计：599.30
系统计算合计：599.30

回复“确认入库”后，将创建 ERPNext 采购入库草稿。
```

## 7. API 示例
```bash
curl -X POST http://localhost:8000/api/purchase/inbound/prepare \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session-001",
    "user_id": "u001",
    "user_name": "测试用户",
    "source_channel": "wechat",
    "source_type": "text",
    "text": "鲜鸡蛋90斤 4.66元/斤，土鸡蛋35斤 5.14元/斤，共599.3元",
    "supplier_name": "市场采购供应商",
    "warehouse": "仓库-华食泰"
  }'

curl -X POST http://localhost:8000/api/purchase/inbound/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session-001",
    "user_id": "u001",
    "confirm_text": "确认入库",
    "snapshot_id": "替换为prepare返回的snapshot_id"
  }'
```
