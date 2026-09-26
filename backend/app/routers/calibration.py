"""校准记录接口：查看校准记录，检测人员提交申请，设备管理员处理校准。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import Operator, get_operator, get_optional_operator
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.calibration import CalibrationService, PermissionDenied

router = APIRouter(prefix="/api/calibration", tags=["校准记录"])

service = CalibrationService()

LIST_FIELDS = ["校准编号", "关联设备", "校准方式", "标准物质", "校准结果", "校准日期", "下次校准日", "校准状态"]
STATUSES = ["待校准", "校准中", "已合格", "不合格"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按校准编号检索"),
    status: str | None = Query(default=None, description="待校准、校准中、已合格、不合格"),
    page: int = 1,
    size: int = 20,
    operator: Operator | None = Depends(get_optional_operator),
) -> PageResult[dict]:
    """按校准编号与状态过滤校准记录列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        status=status,
        page=page,
        size=size,
        operator=operator,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出校准记录清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "calibration", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(
    entry_id: int,
    operator: Operator | None = Depends(get_optional_operator),
) -> dict:
    """读取单条校准记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id, operator)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"校准记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(
    payload: EntryPayload,
    operator: Operator = Depends(get_operator),
) -> ActionResult:
    """检测人员按设备提交校准申请；故障停用设备由业务规则拒绝。"""
    try:
        entry, message = service.create_entry(payload.values, operator)
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    operator: Operator = Depends(get_operator),
) -> ActionResult:
    """设备管理员对校准记录执行开始、合格或不合格判定。"""
    action = str(payload.values.get("action") or "").strip()
    try:
        entry, message = service.run_action(entry_id, action, operator)
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
