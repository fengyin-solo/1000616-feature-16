"""仪器设备接口：维护仪器设备，覆盖提交校准、恢复在运、停用设备等动作。

角色通过请求头 X-Operator-Role 传入（admin=设备管理员，inspector=检测人员），
未携带时按最小权限的检测人员处理；越权请求一律拒绝并说明原因。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.instrument import InstrumentService, normalize_role

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
    x_operator_role: str | None = Header(default=None),
) -> PageResult[dict]:
    """按设备编号与状态过滤仪器设备列表；每行附带当前角色可执行的动作。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    role = normalize_role(x_operator_role)
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size, role=role)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出仪器设备清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "instrument", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int, x_operator_role: str | None = Header(default=None)) -> dict:
    """读取单条仪器设备明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id, role=normalize_role(x_operator_role))
    if entry is None:
        raise HTTPException(status_code=404, detail=f"仪器设备 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload, x_operator_role: str | None = Header(default=None)) -> ActionResult:
    """登记一条仪器设备；仅设备管理员可登记，越权或缺字段时说明原因。"""
    entry, message = service.create_entry(payload.values, role=normalize_role(x_operator_role))
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def update_entry(
    entry_id: int,
    payload: EntryPayload,
    x_operator_role: str | None = Header(default=None),
) -> ActionResult:
    """维护设备编号、设备型号、量程范围等档案字段；仅设备管理员可维护。"""
    entry, message = service.update_entry(entry_id, payload.values, role=normalize_role(x_operator_role))
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    x_operator_role: str | None = Header(default=None),
) -> ActionResult:
    """对单条仪器设备执行提交校准、恢复在运、停用设备；越权或状态不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    confirm = bool(payload.values.get("confirm"))
    entry, message = service.run_action(
        entry_id,
        action,
        role=normalize_role(x_operator_role),
        confirm=confirm,
    )
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
