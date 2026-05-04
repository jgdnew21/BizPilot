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

## 配置
见 `.env.example`：ERPNext连接信息、默认仓库别名、snapshot/master data路径。

## 后续扩展
- PO prepare/confirm
- PR prepare/confirm
- PostgreSQL snapshot repository
- ERPNext master data query
- OpenClaw 强类型 plugin/tool
- n8n 编排接入
