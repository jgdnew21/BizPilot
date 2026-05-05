# OpenClaw MR Skill 对接说明（BizPilot v0.2）

本文档用于约束 OpenClaw 与 BizPilot `material-requests` 接口的集成方式，确保 OpenClaw 只做“转发与展示”，不介入业务判断。

## 1. 职责边界

OpenClaw 在 MR 场景中**只负责**：

1. 原样传用户输入到 `prepare`。
2. 原样展示 `response.markdown_text`。
3. 保存最新 `snapshot_id`。
4. 用户回复“确认”时调用 `confirm`。
5. 不自行判断商品/供应商/仓库是否匹配。
6. 不生成自己的 Markdown。

> 关键原则：BizPilot 输出什么确认单，OpenClaw 就展示什么确认单。

---

## 2. `curl_http` 工具调用方式

若 OpenClaw 使用 `curl_http`（或等价 HTTP 工具），请遵循：

- 方法：`POST`
- Header：`Content-Type: application/json`
- URL：
  - `http://host.docker.internal:8000/api/purchase/material-requests/prepare`
  - `http://host.docker.internal:8000/api/purchase/material-requests/confirm`
- Body：JSON；字段名与大小写必须与接口定义一致。

示例（等价 curl）：

```bash
curl -X POST http://host.docker.internal:8000/api/purchase/material-requests/prepare \
  -H "Content-Type: application/json" \
  -d '{...}'
```

---

## 3. `prepare` 调用示例

当用户输入采购需求时，调用：

`POST http://host.docker.internal:8000/api/purchase/material-requests/prepare`

请求体：

```json
{
  "session_id": "<当前会话ID>",
  "user_id": "<当前用户ID>",
  "user_name": "<当前用户名称>",
  "text": "<用户本轮消息原文>"
}
```

### `prepare` 返回后，OpenClaw 必须执行

1. 保存 `response.snapshot_id` 为最新 `snapshot_id`。
2. 原样输出 `response.markdown_text`。
3. 不要自己补充业务判断。
4. 不要提示用户确认，除非 `markdown_text` 里已经提示可以确认。

---

## 4. `confirm` 调用示例

当用户回复“确认”时，调用：

`POST http://host.docker.internal:8000/api/purchase/material-requests/confirm`

请求体：

```json
{
  "session_id": "<当前会话ID>",
  "user_id": "<当前用户ID>",
  "snapshot_id": "<最新 snapshot_id>",
  "confirm_text": "确认"
}
```

> `snapshot_id` 必须是当前会话最近一次 `prepare` 返回的最新值。

---

## 5. 多轮修改（`previous_snapshot_id`）调用示例

如果当前会话已有最新 `snapshot_id`，且用户是在修改上一轮确认单，则 `prepare` body 必须增加：

```json
{
  "previous_snapshot_id": "<上一轮最新 snapshot_id>"
}
```

完整示例流程：

### 第 1 轮

用户：

> 我明天采购五常大米 80斤，供应商采无忧

OpenClaw 调用：

```json
{
  "session_id": "s_001",
  "user_id": "u_001",
  "user_name": "店长张三",
  "text": "我明天采购五常大米 80斤，供应商采无忧"
}
```

系统返回确认单和 `snapshot_id = snap_001`。

### 第 2 轮（修改）

用户：

> 仓库改成广州仓

OpenClaw 调用：

```json
{
  "session_id": "s_001",
  "user_id": "u_001",
  "user_name": "店长张三",
  "text": "仓库改成广州仓",
  "previous_snapshot_id": "snap_001"
}
```

系统返回新确认单和 `snapshot_id = snap_002`。

OpenClaw 必须把当前最新 `snapshot_id` 更新为 `snap_002`。

### 第 3 轮（确认）

用户：

> 确认

OpenClaw 调用 `confirm` 时必须使用 `snap_002`，不要使用 `snap_001`。

---

## 6. 健康检测方式

### 6.1 后端可用性

```bash
curl http://localhost:8000/health/ready
```

期望：返回 `ready=true`（或等价就绪状态）。

### 6.2 prepare 快速自检

```bash
curl -X POST http://localhost:8000/api/purchase/material-requests/prepare \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "health_check_s",
    "user_id": "health_check_u",
    "user_name": "健康检查账号",
    "text": "明天采购五常大米80斤，供应商采无忧"
  }'
```

期望：返回 `snapshot_id` 与 `markdown_text`。

---

## 7. 常见排查方法

1. **后端是否可用**
   ```bash
   curl http://localhost:8000/health/ready
   ```

2. **LLM 是否启用**
   检查 `.env` 是否包含：
   ```dotenv
   ENABLE_LLM_EXTRACTOR=true
   ```

3. **prepare 返回是否正确**
   用 curl 直接调用并检查是否包含：
   - `snapshot_id`
   - `markdown_text`

4. **snapshot 文件检查**
   ```bash
   ls -lt data/snapshots | head
   cat data/snapshots/<snapshot_id>.json
   ```

5. **OpenClaw 显示和 curl 不一致时，优先检查**
   - OpenClaw 是否原样展示 `markdown_text`
   - OpenClaw 是否自己追加判断
   - OpenClaw 传入的 `text` 是否被改写
   - OpenClaw `confirm` 是否使用最新 `snapshot_id`

---

## 8. 建议的端到端脚本

仓库提供 `scripts/e2e_mr_flow.sh`，覆盖以下流程：

1. health ready
2. prepare 第一次
3. 从返回中提取 `snapshot_id`
4. prepare 修改（传 `previous_snapshot_id`）
5. confirm 最新 `snapshot_id`

脚本依赖 `jq`。若环境无 `jq`，可改为手工复制 `snapshot_id` 执行。
