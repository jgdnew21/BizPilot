# OpenClaw 采购意图分流 Skill 对接说明（BizPilot v0.2）

本文档用于约束 OpenClaw 与 BizPilot 采购接口的集成方式，确保 OpenClaw 只做“转发与展示”，不介入 ERPNext 业务判断。

## 1. 职责边界

OpenClaw 在采购场景中**只负责**：

1. 做“采购需求”与“采购报单入库”的意图分流。
2. 原样传用户输入到对应 `prepare`。
3. 原样展示 `response.markdown_text`（或 inbound 的 `response.markdown`）。
4. 保存最新 `snapshot_id`。
5. 根据用户确认指令调用对应 `confirm`。
6. 不自行判断商品/供应商/仓库是否匹配。
7. 不生成自己的确认 Markdown。
8. 不展示 `structured_payload` JSON 给用户。

> 关键原则：BizPilot 输出什么确认单，OpenClaw 就展示什么确认单。

---

## 2. 意图分流规则

### 2.1 走采购需求链路（request）

典型用户表达：

- 我要采购
- 明天需要买
- 帮我生成采购需求
- 计划采购

调用：

- `POST /api/purchase/request/prepare`
- `POST /api/purchase/request/confirm`

（也兼容历史接口 `/api/purchase/material-requests/*`。）

### 2.2 走采购报单入库链路（inbound）

典型用户表达：

- 今天采购了
- 已到货
- 已入库
- 送货单 / 小票
- 报单
- 采购如下
- 买了
- 收到货了

调用：

- `POST /api/purchase/inbound/prepare`
- `POST /api/purchase/inbound/confirm`

### 2.3 无法判断时

必须追问：

> 你是要提交采购需求，还是要登记已经采购到货的入库报单？

---

## 3. `curl_http` 工具调用方式

若 OpenClaw 使用 `curl_http`（或等价 HTTP 工具），请遵循：

- 方法：`POST`
- Header：`Content-Type: application/json`
- URL：
  - `http://host.docker.internal:8000/api/purchase/request/prepare`
  - `http://host.docker.internal:8000/api/purchase/request/confirm`
  - `http://host.docker.internal:8000/api/purchase/inbound/prepare`
  - `http://host.docker.internal:8000/api/purchase/inbound/confirm`
- Body：JSON；字段名与大小写必须与接口定义一致。

---

## 4. 确认词与 confirm 路由

- 用户回复 **“确认入库”**：调用 `/api/purchase/inbound/confirm`。
- 用户回复 **“确认采购需求”** 或 **“确认”**：调用 `/api/purchase/request/confirm`。

> `snapshot_id` 必须使用当前会话最近一次对应链路 `prepare` 返回的最新值。

---

## 5. 展示要求

`prepare` 返回 Markdown 后，OpenClaw 必须原样展示。

- 采购需求链路展示 `markdown_text`
- 采购报单入库链路展示 `markdown`

禁止向用户展示 `structured_payload` JSON。

## 6. 采购入库 prepare 字段契约

OpenClaw 调用 `POST /api/purchase/inbound/prepare` 时，**推荐传 `text`**：

```json
{
  "session_id": "<当前会话ID>",
  "user_id": "<当前用户ID>",
  "user_name": "<当前用户名称>",
  "source_channel": "openclaw",
  "source_type": "text",
  "text": "<用户原始报单文本>"
}
```

BizPilot Backend 当前兼容 `text` 与 `raw_text`；OpenClaw Skill 推荐传 `text`，后端保存 snapshot 时会统一保留 `raw_text` 用于追溯。
