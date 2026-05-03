from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import DEFAULT_WAREHOUSE, SNAPSHOT_DIR
from app.services.erpnext_tool import ERPNextClient, ERPNextError

# =============================================================================
# BizPilot / Purchase Skill Runtime
# =============================================================================
#
# 这个文件是“采购确认业务内核”。
#
# 设计原则：
# 1. main.py 只做 HTTP 壳，不做业务判断
# 2. 所有“解析 / 标准化 / 生成确认单 / 保存快照 / 提交 ERPNext / 更新状态”
#    都在本文件完成
# 3. confirm 阶段严格基于已保存的确认快照执行，绝不重新自由解析原始话术
#
# 与 main.py 的契约（必须保持一致）：
#
# - prepare_purchase(
#       session_id: str,
#       user_id: str,
#       user_name: Optional[str],
#       raw_text: str,
#   ) -> dict
#
#   返回至少包含：
#   {
#       "success": bool,
#       "mode": "prepare",
#       "session_id": str,
#       "snapshot_id": str,
#       "status": str,
#       "markdown": str,
#       "message": Optional[str],
#   }
#
# - confirm_purchase(
#       session_id: str,
#       user_id: Optional[str],
#       user_name: Optional[str],
#       confirm_text: str,
#   ) -> dict
#
#   返回至少包含：
#   {
#       "success": bool,
#       "mode": "confirm",
#       "session_id": str,
#       "snapshot_id": str,
#       "status": str,
#       "message": str,
#       "po_no": Optional[str],
#       "raw": Optional[dict],
#   }
#
# =============================================================================


# =============================================================================
# 第一版硬编码主数据映射
# =============================================================================
#
# 说明：
# 当前仍处于 MVP 阶段，为了优先跑通完整闭环，这里保留最小硬编码映射。
# 后续应逐步迁移到：
# - PostgreSQL 主数据映射表
# - ERPNext 主数据查询
# - 可维护的别名配置表
# =============================================================================

SUPPLIER_MAP = {
    "采无忧": "采无忧供应有限公司",
    "采无忧供应": "采无忧供应有限公司",
    "采无忧供应有限公司": "采无忧供应有限公司",
}

# 当前阶段仓库先固定映射。
# 后续如果要支持“南宁仓 / 上海仓 / 冷库 / 门店仓”等多种说法，
# 可以把这里替换为仓库别名表。
WAREHOUSE_MAP = {
    "南宁仓": DEFAULT_WAREHOUSE,
    DEFAULT_WAREHOUSE: DEFAULT_WAREHOUSE,
}

# 注意：
# 这里保留了你原始版本中的“测试主数据映射”。
# 也就是说：
# - 用户看到的是输入商品名
# - ERPNext 实际写入的 item_code / item_name 可能是测试主数据
#
# 这是当前阶段为了验证 ERP 闭环保留的做法。
# 等你换成真实主数据后，只需要改这里或迁移到数据库映射表。
ITEM_MAP = {
    "大头鱼": {
        "item_code": "002130",
        "item_name": "大头鱼",   # 当前 ERPNext 测试主数据
        "uom": "斤",
    },
    "火石枪": {
        "item_code": "002132",
        "item_name": "火石枪",   # 当前 ERPNext 测试主数据
        "uom": "个",
    },
    "萌考拉冰淇淋": {
        "item_code": "002136",
        "item_name": "萌考拉冰淇淋",
        "uom": "个",
    },
    "五常大米": {
        "item_code": "002138",
        "item_name": "五常大米",   # 当前 ERPNext 测试主数据
        "uom": "斤",
    },
}


# =============================================================================
# 数据结构定义
# =============================================================================

@dataclass
class ParsedItem:
    """
    单条采购商品在“确认前”的标准化结果。

    字段说明：
    - input_name: 用户原始表达的商品名
    - item_code: ERPNext 标准商品编码
    - item_name: ERPNext 标准商品名称（当前可能是测试主数据名）
    - qty: 数量
    - uom: 执行单位（当前第一版先按映射表强制落标准单位）
    - status: 当前匹配状态，第一版只有“已匹配”
    """
    input_name: str
    item_code: str
    item_name: str
    qty: float
    uom: str
    status: str = "已匹配"


@dataclass
class Snapshot:
    """
    确认快照。

    这是“所见即所写”的核心载体：
    用户在确认阶段看到的 markdown_text 与 structured_payload
    会被固化在这里；确认时必须基于该快照执行。

    当前持久化方式：文件
    后续建议迁移：PostgreSQL

    关键字段：
    - snapshot_id: 快照唯一 ID
    - session_id: 会话 ID；当前仍以 session_id 作为文件索引键
    - user_id / user_name: 审计与回显字段
    - status: 状态机
    - raw_text: 用户原始输入
    - markdown_text: 用户实际看到的确认单
    - structured_payload: 后续提交 ERPNext 时使用的结构化数据
    - event_logs: 可选审计日志，便于后续排错/追溯
    """
    snapshot_id: str
    session_id: str
    user_id: str
    user_name: Optional[str]
    status: str
    raw_text: str
    markdown_text: str
    structured_payload: Dict[str, Any]
    created_at: str
    updated_at: str
    event_logs: List[Dict[str, Any]] = field(default_factory=list)


# =============================================================================
# 基础工具函数
# =============================================================================

def now_iso() -> str:
    """
    返回当前时间的 ISO 字符串。

    这里保留到秒级即可，便于调试阅读。
    后续如果你要做严格并发控制 / 排序，可以升到微秒级。
    """
    return datetime.now().isoformat(timespec="seconds")


def snapshot_path(session_id: str) -> Path:
    """
    根据 session_id 计算快照文件路径。

    为什么当前用 session_id 作为文件名？
    - 和现阶段 main.py 契约最匹配
    - 当前 MVP 是一轮 prepare + 一轮 confirm 的最小闭环
    - 落地最快，调试最简单

    风险：
    - 同一个 session 多次 prepare 会覆盖旧快照

    后续建议：
    - 改为 snapshot_id 为主键
    - main.py / OpenClaw confirm 时显式携带 snapshot_id
    """
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
    return SNAPSHOT_DIR / f"{safe}.json"


def save_snapshot(snapshot: Snapshot) -> None:
    """
    保存确认快照到文件。

    注意：
    这里使用 dataclass -> dict -> json 的方式，结构直观，方便肉眼查看。
    """
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = snapshot_path(snapshot.session_id)
    path.write_text(
        json.dumps(asdict(snapshot), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_snapshot(session_id: str) -> Optional[Snapshot]:
    """
    读取 session_id 对应的确认快照。

    若不存在则返回 None，而不是直接抛异常。
    这样上层业务可以返回更友好的提示。
    """
    path = snapshot_path(session_id)
    if not path.exists():
        return None

    data = json.loads(path.read_text(encoding="utf-8"))
    return Snapshot(**data)


def append_snapshot_event(snapshot: Snapshot, event_type: str, raw_payload: Dict[str, Any]) -> None:
    """
    给快照追加一条简易审计日志。

    当前只是轻量实现，便于：
    - 后续排查 prepare / confirm 发生了什么
    - 保留调用输入、失败原因等
    """
    snapshot.event_logs.append(
        {
            "timestamp": now_iso(),
            "event_type": event_type,
            "raw_payload": raw_payload,
        }
    )


def format_qty(qty: float) -> str:
    """
    将数量格式化为更适合 markdown 展示的形式。

    例如：
    - 80.0 -> "80"
    - 10.5 -> "10.5"
    """
    if float(qty).is_integer():
        return str(int(qty))
    return str(qty)


# =============================================================================
# 标准化解析逻辑
# =============================================================================

def resolve_relative_date(text: str, today: Optional[date] = None) -> tuple[str, str]:
    """
    解析用户输入中的相对日期表达。

    当前支持：
    - 今天
    - 明天
    - 后天

    返回：
    - schedule_date_text: 用户可理解的原始/解释性文案
    - schedule_date: ERPNext 使用的 ISO 日期

    当前第一版策略：
    如果没识别到日期，则默认今天。

    后续更稳的做法：
    - 改为阻断提交并要求用户补充日期
    - 增加“周五 / 下周一 / 4月30日”等识别
    """
    today = today or date.today()

    if "后天" in text:
        d = today + timedelta(days=2)
        return "后天", d.isoformat()

    if "明天" in text:
        d = today + timedelta(days=1)
        return "明天", d.isoformat()

    if "今天" in text:
        return "今天", today.isoformat()

    return "今天(默认)", today.isoformat()


def resolve_supplier(text: str) -> tuple[str, str]:
    """
    从用户原文中解析供应商简称，并映射到标准供应商名称。

    返回：
    - supplier_input: 用户命中的原始说法/简称
    - supplier_standard: 标准供应商名称

    当前策略：
    - 只要某个 alias 是 text 的子串，即视为命中
    - 若未命中，直接抛出 ValueError，让上层阻断流程
    """
    for alias, standard in SUPPLIER_MAP.items():
        if alias in text:
            return alias, standard

    raise ValueError("未匹配到供应商")


def resolve_warehouse(text: str) -> tuple[str, str]:
    """
    解析仓库。

    当前阶段：
    - 先不从文本里复杂提取仓库
    - 直接返回默认仓库映射
    - 保证最小闭环先跑通

    返回：
    - warehouse_input: 对用户可展示的输入语义
    - warehouse_standard: ERPNext 实际执行的标准仓库名
    """
    # 如果后续用户文本里明确提到某个仓库，可在这里加规则判断。
    if "南宁仓" in text:
        return "南宁仓", WAREHOUSE_MAP["南宁仓"]

    # 默认兜底为南宁仓 / 默认仓
    return "南宁仓", DEFAULT_WAREHOUSE


def parse_items(text: str) -> List[ParsedItem]:
    """
    从用户文本中解析商品行。

    当前支持的最小格式示例：
    - 五常大米80斤
    - 嘉木东来寿眉白茶10盒
    - 萌考拉冰淇淋100个

    解析策略：
    - 先遍历 ITEM_MAP 的商品别名
    - 用正则查找 “商品名 + 数量 + 单位”
    - 若用户单位与标准单位不同，当前第一版仍强制按标准单位落地

    注意：
    这是 MVP 的“保守可跑通版”，不是通用 NLP 解析器。

    后续演进方向：
    - 识别更多自然语言表达
    - 单位合法性校验
    - 单位换算
    - 多候选匹配阻断
    """
    found: List[ParsedItem] = []

    for input_name, meta in ITEM_MAP.items():
        # 说明：
        # [^\s，,；;。]* 用于尽量抓住单位，如 斤 / 个 / 盒
        # 如果用户没写单位，则落回 meta["uom"]
        pattern = rf"{re.escape(input_name)}\s*(\d+(?:\.\d+)?)\s*([^\s，,；;。]*)"
        match = re.search(pattern, text)
        if not match:
            continue

        qty = float(match.group(1))
        user_uom = match.group(2).strip() or meta["uom"]

        found.append(
            ParsedItem(
                input_name=input_name,
                item_code=meta["item_code"],
                item_name=meta["item_name"],
                qty=qty,
                # 当前版本先强制使用标准执行单位，避免 ERPNext 校验失败
                uom=meta["uom"] if meta["uom"] else user_uom,
                status="已匹配",
            )
        )

    if not found:
        raise ValueError("未匹配到任何商品")

    return found


# =============================================================================
# 确认单 / payload 构造逻辑
# =============================================================================

def build_markdown(
    items: List[ParsedItem],
    supplier_input: str,
    supplier_standard: str,
    schedule_date_text: str,
    schedule_date: str,
    warehouse_input: str,
    warehouse_standard: str,
    user_name: Optional[str] = None,
) -> str:
    """
    生成用户可见的 Markdown 确认单。

    关键要求：
    - 用户看的是 markdown
    - 用户确认的是 markdown 所表达的业务内容
    - 所以 markdown_text 必须保存进 snapshot，作为“所见即所写”的依据
    """
    lines: List[str] = []
    lines.append("### 采购需求（待确认）")
    lines.append("")
    lines.append("| # | 商品 | 数量 | 单位 | ERP匹配商品 | 状态 |")
    lines.append("|---|---|---:|---|---|---|")

    for idx, item in enumerate(items, start=1):
        lines.append(
            f"| {idx} | {item.input_name} | {format_qty(item.qty)} | "
            f"{item.uom} | {item.item_name} | {item.status} |"
        )

    lines.append("")
    lines.append(f"- **供应商**：{supplier_input} → {supplier_standard}")
    lines.append(f"- **需求日期**：{schedule_date_text} → {schedule_date}")
    lines.append(f"- **入库仓库**：{warehouse_input} → {warehouse_standard}")
    if user_name:
        lines.append(f"- **录入人**：{user_name}")
    lines.append("")
    lines.append("请回复 **确认** 提交采购订单；如需修改，请直接回复修改内容。")

    return "\n".join(lines)


def build_structured_payload(
    items: List[ParsedItem],
    supplier_input: str,
    supplier_standard: str,
    schedule_date_text: str,
    schedule_date: str,
    warehouse_input: str,
    warehouse_standard: str,
) -> Dict[str, Any]:
    """
    构造结构化 payload。

    注意区分两个层面：
    1. 给 BizPilot / 审计 / 回显用的字段
    2. 给 ERPNext 提交真正需要用的字段

    当前先把两类信息都保留在 structured_payload 中，
    这样后续更容易做追溯与排错。
    """
    return {
        "supplier_input": supplier_input,
        "supplier_standard_name": supplier_standard,
        "supplier": supplier_standard,
        "schedule_date_text": schedule_date_text,
        "schedule_date": schedule_date,
        "warehouse_input": warehouse_input,
        "warehouse_standard_name": warehouse_standard,
        "warehouse": warehouse_standard,
        "items": [
            {
                "item_input_name": item.input_name,
                "input_name": item.input_name,   # 为兼容你原有字段名，暂时保留
                "item_code": item.item_code,
                "item_name_snapshot": item.item_name,
                "item_name": item.item_name,     # 为兼容你原有字段名，暂时保留
                "qty": item.qty,
                "uom": item.uom,
                "status": item.status,
            }
            for item in items
        ],
    }


def build_erpnext_payload(structured_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 snapshot 中的 structured_payload 转成 ERPNext 创建采购单所需的最小 payload。

    关键原则：
    - confirm 阶段只能使用 snapshot 里已经固化的 structured_payload
    - 绝不能重新解析 raw_text
    """
    return {
        "supplier": structured_payload["supplier"],
        "schedule_date": structured_payload["schedule_date"],
        "warehouse": structured_payload["warehouse"],
        "items": [
            {
                "item_code": item["item_code"],
                "qty": item["qty"],
                "uom": item["uom"],
            }
            for item in structured_payload["items"]
        ],
    }


# =============================================================================
# 对外契约：prepare / confirm
# =============================================================================

def prepare_purchase(
    session_id: str,
    user_id: str,
    user_name: Optional[str],
    raw_text: str,
) -> Dict[str, Any]:
    """
    采购 prepare 阶段。

    责任：
    1. 解析用户原始采购话术
    2. 解析供应商 / 日期 / 仓库 / 商品
    3. 生成 markdown 确认单
    4. 生成 structured_payload
    5. 保存确认快照
    6. 返回给 main.py 统一响应

    这是 main.py 调用的正式入口，必须与 main.py 契约保持一致。
    """
    if not session_id.strip():
        raise ValueError("session_id 不能为空")
    if not user_id.strip():
        raise ValueError("user_id 不能为空")
    if not raw_text.strip():
        raise ValueError("采购内容不能为空")

    supplier_input, supplier_standard = resolve_supplier(raw_text)
    schedule_date_text, schedule_date = resolve_relative_date(raw_text)
    warehouse_input, warehouse_standard = resolve_warehouse(raw_text)
    items = parse_items(raw_text)

    markdown_text = build_markdown(
        items=items,
        supplier_input=supplier_input,
        supplier_standard=supplier_standard,
        schedule_date_text=schedule_date_text,
        schedule_date=schedule_date,
        warehouse_input=warehouse_input,
        warehouse_standard=warehouse_standard,
        user_name=user_name,
    )

    structured_payload = build_structured_payload(
        items=items,
        supplier_input=supplier_input,
        supplier_standard=supplier_standard,
        schedule_date_text=schedule_date_text,
        schedule_date=schedule_date,
        warehouse_input=warehouse_input,
        warehouse_standard=warehouse_standard,
    )

    ts = now_iso()
    snapshot = Snapshot(
        snapshot_id=str(uuid.uuid4()),
        session_id=session_id,
        user_id=user_id,
        user_name=user_name,
        status="pending_confirmation",
        raw_text=raw_text,
        markdown_text=markdown_text,
        structured_payload=structured_payload,
        created_at=ts,
        updated_at=ts,
    )
    append_snapshot_event(
        snapshot,
        event_type="purchase_prepare",
        raw_payload={
            "session_id": session_id,
            "user_id": user_id,
            "user_name": user_name,
            "raw_text": raw_text,
        },
    )
    save_snapshot(snapshot)

    return {
        "success": True,
        "mode": "prepare",
        "session_id": session_id,
        "snapshot_id": snapshot.snapshot_id,
        "status": snapshot.status,
        "markdown": markdown_text,
        "message": "采购需求已整理完成，等待用户确认。",
    }


def confirm_purchase(
    session_id: str,
    user_id: Optional[str],
    user_name: Optional[str],
    confirm_text: str,
) -> Dict[str, Any]:
    """
    采购 confirm 阶段。

    责任：
    1. 读取已保存的确认快照
    2. 校验状态
    3. 基于 snapshot 中的 structured_payload 构建 ERPNext payload
    4. 调用 ERPNext 创建采购单
    5. 更新快照状态
    6. 返回给 main.py 统一响应

    关键原则：
    绝不重新解析原始 raw_text。
    """
    if not session_id.strip():
        raise ValueError("session_id 不能为空")

    normalized_confirm_text = (confirm_text or "").strip()
    if normalized_confirm_text != "确认":
        raise ValueError('当前 confirm 只接受明确指令："确认"')

    snapshot = load_snapshot(session_id)
    if not snapshot:
        return {
            "success": False,
            "mode": "confirm",
            "session_id": session_id,
            "snapshot_id": "",
            "status": "not_found",
            "message": "未找到待确认的采购需求，请先发送采购内容。",
            "po_no": None,
            "raw": None,
        }

    if snapshot.status != "pending_confirmation":
        return {
            "success": False,
            "mode": "confirm",
            "session_id": session_id,
            "snapshot_id": snapshot.snapshot_id,
            "status": snapshot.status,
            "message": f"当前快照状态为 {snapshot.status}，不能重复提交。",
            "po_no": None,
            "raw": None,
        }

    append_snapshot_event(
        snapshot,
        event_type="purchase_confirm_requested",
        raw_payload={
            "session_id": session_id,
            "user_id": user_id,
            "user_name": user_name,
            "confirm_text": normalized_confirm_text,
        },
    )

    payload = build_erpnext_payload(snapshot.structured_payload)
    client = ERPNextClient()

    try:
        # result = client.create_purchase_order(payload)
        result = client.create_material_request(payload)
    except ERPNextError as exc:
        snapshot.status = "submit_failed"
        snapshot.updated_at = now_iso()
        append_snapshot_event(
            snapshot,
            event_type="material_request_failed",
            raw_payload={
                "error": str(exc),
                "erp_payload": payload,
            },
        )
        save_snapshot(snapshot)

        return {
            "success": False,
            "mode": "confirm",
            "session_id": session_id,
            "snapshot_id": snapshot.snapshot_id,
            "status": snapshot.status,
            "message": f"采购订单提交失败：{exc}",
            "po_no": None,
            "raw": None,
        }

    snapshot.status = "submitted"
    snapshot.updated_at = now_iso()
    append_snapshot_event(
        snapshot,
        event_type="purchase_submitted",
        raw_payload={
            "erp_payload": payload,
            "erp_result": result,
        },
    )
    save_snapshot(snapshot)

    po_no = result["po_no"]
    return {
        "success": True,
        "mode": "confirm",
        "session_id": session_id,
        "snapshot_id": snapshot.snapshot_id,
        "status": snapshot.status,
        "message": (
            "已提交采购订单。\n\n"
            f"- **采购单号**：{po_no}\n"
            f"- **供应商**：{snapshot.structured_payload['supplier']}\n"
            f"- **需求日期**：{snapshot.structured_payload['schedule_date']}\n"
            f"- **入库仓库**：{snapshot.structured_payload['warehouse']}"
        ),
        "po_no": po_no,
        "raw": result.get("raw"),
    }


# =============================================================================
# 向后兼容包装器
# =============================================================================
#
# 说明：
# 你原来文件里用的是：
# - prepare_purchase_confirmation(...)
# - submit_confirmed_purchase_order(...)
#
# 为了避免你本地临时脚本或其他调用点全部立刻改名，
# 这里保留兼容包装器。
#
# 但从现在开始，推荐外部统一调用：
# - prepare_purchase(...)
# - confirm_purchase(...)
# =============================================================================

def prepare_purchase_confirmation(
    session_id: str,
    user_id: str,
    raw_text: str,
) -> Dict[str, Any]:
    """
    旧入口兼容包装器。

    兼容策略：
    - 旧入口没有 user_name，因此这里传 None
    - 返回结构保持与新版基本一致，但额外保留旧字段习惯
    """
    result = prepare_purchase(
        session_id=session_id,
        user_id=user_id,
        user_name=None,
        raw_text=raw_text,
    )
    return {
        "success": result["success"],
        "mode": result["mode"],
        "session_id": result["session_id"],
        "snapshot_id": result["snapshot_id"],
        "status": result["status"],
        "markdown": result["markdown"],
        "message": result["message"],
    }


def submit_confirmed_purchase_order(session_id: str) -> Dict[str, Any]:
    """
    旧入口兼容包装器。

    兼容策略：
    - 旧入口没有 user_id / user_name / confirm_text
    - 这里默认视为已经拿到了明确的“确认”
    """
    return confirm_purchase(
        session_id=session_id,
        user_id=None,
        user_name=None,
        confirm_text="确认",
    )


def handle_message(session_id: str, user_id: str, text: str) -> Dict[str, Any]:
    """
    本地手测/旧风格兼容入口。

    行为：
    - 输入“确认”时，走 confirm_purchase
    - 其他文本走 prepare_purchase

    注意：
    正式 HTTP 接入后，推荐只通过 main.py 的两个接口来调用，
    不再依赖这个路由函数。
    """
    text = text.strip()

    if text == "确认":
        return confirm_purchase(
            session_id=session_id,
            user_id=user_id,
            user_name=None,
            confirm_text=text,
        )

    return prepare_purchase(
        session_id=session_id,
        user_id=user_id,
        user_name=None,
        raw_text=text,
    )


# =============================================================================
# 本地手测
# =============================================================================

if __name__ == "__main__":
    session_id = "demo_session_001"
    user_id = "guodong"
    user_name = "果冻"

    first = prepare_purchase(
        session_id=session_id,
        user_id=user_id,
        user_name=user_name,
        raw_text="我后天要买五常大米80斤，嘉木东来寿眉白茶10盒，萌考拉冰淇淋100个，供应商是采无忧",
    )
    print(first["markdown"])
    print("------")

    second = confirm_purchase(
        session_id=session_id,
        user_id=user_id,
        user_name=user_name,
        confirm_text="确认",
    )
    print(second)