from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# 注意：
# 这里先约定新版 purchase_skill_runtime.py 会暴露这两个函数：
# 1) prepare_purchase(...)
# 2) confirm_purchase(...)
#
# 下一步我给你更新 runtime 文件时，会严格按这个接口实现，
# 这样 main.py 和 runtime.py 两边保持完全一致。
from app.api.erpnext_sync import router as erpnext_sync_router
from app.services.purchase_skill_runtime import confirm_purchase, prepare_purchase

app = FastAPI(
    title="BizPilot Backend",
    version="0.1.0",
    description=(
        "BizPilot 后端接口。"
        "当前先提供采购场景的两阶段接口："
        "prepare（整理并生成确认单） + confirm（基于确认快照正式提交）。"
    ),
)

app.include_router(erpnext_sync_router)


# =========================
# 通用响应模型
# =========================

class HealthResponse(BaseModel):
    """
    健康检查接口返回模型。
    用于确认 FastAPI 服务已启动成功。
    """
    ok: bool
    service: str
    version: str


# =========================
# /api/purchase/prepare
# =========================

class PurchasePrepareRequest(BaseModel):
    """
    prepare 阶段请求体。

    设计说明：
    - session_id：用于绑定一次对话上下文下的确认快照
    - user_id：用于审计/追踪
    - user_name：当前阶段不是强依赖，但建议保留，后续 markdown / 审计都可用
    - text：用户原始采购话术
    """
    session_id: str = Field(..., description="会话ID，用于绑定确认快照")
    user_id: str = Field(..., description="用户ID")
    user_name: Optional[str] = Field(default=None, description="用户显示名，可选")
    text: str = Field(..., description="用户原始采购话术")


class PurchasePrepareResponse(BaseModel):
    """
    prepare 阶段响应体。

    设计目标：
    - 直接返回 markdown 给调用方展示
    - 返回 snapshot_id，供后续 confirm 追踪
    - 返回 status，便于后续扩展状态机
    """
    ok: bool
    mode: str
    session_id: str
    snapshot_id: str
    status: str
    markdown: str


# =========================
# /api/purchase/confirm
# =========================

class PurchaseConfirmRequest(BaseModel):
    """
    confirm 阶段请求体。

    设计说明：
    - 当前阶段仍要求调用方传 session_id
    - confirm_text 当前只接受“确认”
    - user_id / user_name 保留为审计字段，不作为当前业务判断依据
    """
    session_id: str = Field(..., description="会话ID，必须与 prepare 阶段一致")
    user_id: Optional[str] = Field(default=None, description="用户ID，可选")
    user_name: Optional[str] = Field(default=None, description="用户显示名，可选")
    confirm_text: str = Field(..., description='通常应为"确认"')


class PurchaseConfirmResponse(BaseModel):
    """
    confirm 阶段响应体。

    设计目标：
    - 返回是否成功提交
    - 返回业务消息（给 OpenClaw / 调试工具直接展示）
    - 返回采购单号，便于后续链路对接
    """
    ok: bool
    mode: str
    session_id: str
    snapshot_id: str
    status: str
    message: str
    # po_no: Optional[str] = None
    mr_no: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


# =========================
# 健康检查
# =========================

@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """
    最基础健康检查接口。
    可用于：
    - 本地 curl 验证
    - Docker 健康检查
    - OpenClaw / 网关侧连通性测试
    """
    return HealthResponse(
        ok=True,
        service="bizpilot-backend",
        version="0.1.0",
    )


# =========================
# 采购：prepare
# =========================

@app.post("/api/purchase/prepare", response_model=PurchasePrepareResponse)
def purchase_prepare(req: PurchasePrepareRequest) -> PurchasePrepareResponse:
    """
    第一步：整理采购需求，生成 Markdown 确认单，并保存确认快照。

    这里故意保持“薄接口层”：
    - 不在 main.py 里解析商品
    - 不在 main.py 里匹配供应商
    - 不在 main.py 里生成 snapshot
    - 不在 main.py 里拼 ERP payload

    这些都应由 runtime 层统一负责。
    这样才能保证高内聚低耦合，也避免出现两处业务逻辑不一致。
    """
    try:
        result = prepare_purchase(
            session_id=req.session_id,
            user_id=req.user_id,
            user_name=req.user_name,
            raw_text=req.text,
        )

        # 约定：
        # 新版 runtime 的 prepare_purchase(...) 返回 dict，
        # 至少包含以下字段：
        # - success: bool
        # - mode: "prepare"
        # - session_id: str
        # - snapshot_id: str
        # - status: str
        # - markdown: str
        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "prepare failed"),
            )

        return PurchasePrepareResponse(
            ok=True,
            mode=result.get("mode", "prepare"),
            session_id=result.get("session_id", req.session_id),
            snapshot_id=result["snapshot_id"],
            status=result.get("status", "pending_confirmation"),
            markdown=result["markdown"],
        )

    except HTTPException:
        raise
    except ValueError as exc:
        # 业务校验类错误：如未匹配到供应商、未匹配到商品等
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # 未预期异常：统一兜底成 500
        raise HTTPException(status_code=500, detail=f"prepare failed: {exc}") from exc



# =========================
# 采购：confirm
# =========================

@app.post("/api/purchase/confirm", response_model=PurchaseConfirmResponse)
def purchase_confirm(req: PurchaseConfirmRequest) -> PurchaseConfirmResponse:
    """
    第二步：基于已生成的确认快照正式提交采购订单。

    关键原则：
    - 用户确认什么，就提交什么
    - confirm 阶段绝不能重新自由解析原始采购话术
    - 真正的快照读取、状态校验、ERP 提交都放在 runtime 层完成

    main.py 这里仅负责：
    - 接收 HTTP 请求
    - 做最薄的一层输入校验
    - 调 runtime
    - 把结果转成稳定响应
    """
    try:
        normalized_confirm_text = req.confirm_text.strip()
        if normalized_confirm_text != "确认":
            raise HTTPException(
                status_code=400,
                detail='当前 confirm 接口只接受明确指令："确认"',
            )

        result = confirm_purchase(
            session_id=req.session_id,
            user_id=req.user_id,
            user_name=req.user_name,
            confirm_text=normalized_confirm_text,
        )

        # 约定：
        # 新版 runtime 的 confirm_purchase(...) 返回 dict，
        # 至少包含以下字段：
        # - success: bool
        # - mode: "confirm"
        # - session_id: str
        # - snapshot_id: str
        # - status: str
        # - message: str
        # - mr_no: Optional[str]
        # - raw: Optional[dict]
        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "confirm failed"),
            )

        return PurchaseConfirmResponse(
            ok=True,
            mode=result.get("mode", "confirm"),
            session_id=result.get("session_id", req.session_id),
            snapshot_id=result["snapshot_id"],
            status=result.get("status", "submitted"),
            message=result["message"],
            # po_no=result.get("po_no"),
            mr_no=result.get("mr_no"),
            raw=result.get("raw"),
        )

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"confirm failed: {exc}") from exc