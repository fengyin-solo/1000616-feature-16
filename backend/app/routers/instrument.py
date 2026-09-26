"""仪器设备接口：维护仪器设备，覆盖提交校准、恢复在运、停用设备等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import (
    Operator,
    get_operator,
    get_optional_operator,
    require_equipment_admin,
)
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.instrument import BusinessConflict, InstrumentService, PermissionDenied

router = APIRouter(prefix="/api/instrument", tags=["仪器设备"])

service = InstrumentService()

LIST_FIELDS = ["设备编号", "设备名称", "设备型号", "量程范围", "校准周期", "校准到期日", "责任人", "设备状态"]
STATUSES = ["待校准", "在运正常", "故障停机", "已停用"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按设备编号检索"),
    status: str | None = Query(default=None, description="待校准、在运正常、故障停机、已停用"),
    page: int = 1,
    size: int = 20,
    operator: Operator | None = Depends(get_optional_operator),
) -> PageResult[dict]:
    """按设备编号与状态过滤仪器设备列表；没有数据时返回空页，不报错。"""
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
    """导出仪器设备清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "instrument", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(
    entry_id: int,
    operator: Operator | None = Depends(get_optional_operator),
) -> dict:
    """读取单条仪器设备明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id, operator)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"仪器设备 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(
    payload: EntryPayload,
    operator: Operator = Depends(require_equipment_admin),
) -> ActionResult:
    """登记一条仪器设备；只有设备管理员可维护设备编号、型号与量程。"""
    try:
        entry, missing = service.create_entry(payload.values, operator)
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except BusinessConflict as exc:
        return ActionResult(ok=False, message=str(exc))
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="仪器设备已登记", entry=entry)


@router.patch("/{entry_id}", response_model=ActionResult)
def update_entry(
    entry_id: int,
    payload: EntryPayload,
    operator: Operator = Depends(require_equipment_admin),
) -> ActionResult:
    """设备管理员维护设备编号、设备名称、设备型号与量程范围。"""
    try:
        entry, message = service.update_entry(entry_id, payload.values, operator)
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
    """对单条仪器设备执行申请、恢复或停用；越权动作返回 403 并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    confirm = bool(payload.values.get("confirm") or payload.values.get("confirmed") or False)
    try:
        entry, message = service.run_action(entry_id, action, operator, confirm=confirm)
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
