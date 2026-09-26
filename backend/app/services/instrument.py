"""仪器设备业务规则：角色权限、状态流转、字段校验与筛选口径。"""
from __future__ import annotations

from typing import Any

from app.auth import ROLE_EQUIPMENT_ADMIN, ROLE_INSPECTOR, Operator
from app.services.calibration import CalibrationService
from app.store import store

MODULE = "instrument"
REQUIRED_FIELDS = ["设备编号", "设备名称", "设备型号", "量程范围"]
ADMIN_EDITABLE_FIELDS = ["设备编号", "设备名称", "设备型号", "量程范围"]
STATUS_ORDER = ["待校准", "在运正常", "故障停机", "已停用"]
ACTION_RULES = {
    "提交校准": "待校准",
    "提交校准申请": "待校准",
    "恢复在运": "在运正常",
    "确认正常": "在运正常",
    "停用设备": "已停用",
}
ADMIN_ACTIONS = {"恢复在运", "确认正常", "停用设备"}
INSPECTOR_ACTIONS = {"提交校准", "提交校准申请"}


class PermissionDenied(Exception):
    """当前角色无权执行该操作。"""


class BusinessConflict(Exception):
    """数据状态或唯一性约束不允许本次操作。"""


class InstrumentService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
        operator: Operator | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("设备编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._serialize(row, operator) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int, operator: Operator | None = None) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._serialize(entry, operator) if entry is not None else None

    def create_entry(self, values: dict[str, Any], operator: Operator) -> tuple[dict[str, Any] | None, list[str]]:
        self._require_admin(operator)
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        code = str(values["设备编号"]).strip()
        if self._find_by_code(code):
            raise BusinessConflict(f"设备编号「{code}」已存在，不能重复登记")
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ADMIN_EDITABLE_FIELDS:
            entry[field] = str(values.get(field) or "").strip()
        entry.update({
            "校准周期": str(values.get("校准周期") or "12 个月"),
            "校准到期日": str(values.get("校准到期日") or "—"),
            "责任人": operator.name,
            "status": STATUS_ORDER[0],
            "pending": True,
            "abnormal": False,
        })
        rows.append(entry)
        return self._serialize(entry, operator), []

    def update_entry(
        self,
        entry_id: int,
        values: dict[str, Any],
        operator: Operator,
    ) -> tuple[dict[str, Any] | None, str]:
        self._require_admin(operator)
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"仪器设备 {entry_id} 不存在或已归档"

        unknown_fields = [field for field in values if field not in ADMIN_EDITABLE_FIELDS]
        if unknown_fields:
            return None, f"字段「{'、'.join(unknown_fields)}」不属于设备管理员可维护范围"
        if not values:
            return None, "没有需要维护的设备字段"

        next_values = {field: str(values[field]).strip() for field in values if field in ADMIN_EDITABLE_FIELDS}
        blank_fields = [field for field, value in next_values.items() if not value]
        if blank_fields:
            return None, f"设备字段不能为空：{'、'.join(blank_fields)}"

        code = next_values.get("设备编号")
        if code:
            existing = self._find_by_code(code)
            if existing is not None and existing is not entry:
                return None, f"设备编号「{code}」已被其他设备占用"

        entry.update(next_values)
        entry["责任人"] = operator.name
        return self._serialize(entry, operator), "仪器设备资料已更新"

    def run_action(
        self,
        entry_id: int,
        action: str,
        operator: Operator,
        *,
        confirm: bool = False,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"仪器设备 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于仪器设备可执行范围"

        if action in INSPECTOR_ACTIONS:
            if operator.role != ROLE_INSPECTOR:
                raise PermissionDenied("只有检测人员可以提交校准申请")
            return self._submit_calibration(entry, operator)

        if operator.role != ROLE_EQUIPMENT_ADMIN:
            raise PermissionDenied("只有设备管理员可以执行设备状态管理操作")
        if action in ADMIN_ACTIONS:
            return self._run_admin_action(entry, action, operator, confirm=confirm)
        return None, f"动作「{action}」不属于仪器设备可执行范围"

    def _run_admin_action(
        self,
        entry: dict[str, Any],
        action: str,
        operator: Operator,
        *,
        confirm: bool,
    ) -> tuple[dict[str, Any] | None, str]:
        status = str(entry.get("status") or "")
        if action in {"恢复在运", "确认正常"}:
            if status == "在运正常":
                return None, "设备已在运，无需重复恢复"
            if status != "故障停机":
                return None, f"当前状态为「{status}」，只有故障停机设备需要恢复在运"
            self._apply_status(entry, "在运正常", operator.name)
            return self._serialize(entry, operator), "故障设备已恢复在运"

        if action == "停用设备":
            if status == "已停用":
                return None, "设备已停用，同一设备重复提交停用只生效一次"
            if status == "故障停机":
                return None, "故障停机设备须先由设备管理员恢复在运，不能直接停用"
            if not confirm:
                return None, "停用设备必须由设备管理员二次确认，请勾选确认后再次提交"
            self._apply_status(entry, "已停用", operator.name)
            return self._serialize(entry, operator), "设备已二次确认并停用"

        return None, f"动作「{action}」不属于仪器设备可执行范围"

    def _submit_calibration(
        self,
        entry: dict[str, Any],
        operator: Operator,
    ) -> tuple[dict[str, Any] | None, str]:
        status = str(entry.get("status") or "")
        if status == "故障停机":
            return None, "故障停机设备不能提交校准，须先由设备管理员恢复在运"
        if status == "已停用":
            return None, "已停用设备不能提交校准，请先联系设备管理员恢复"
        if status == "待校准":
            return None, "该设备已有待处理校准申请，请勿重复提交"
        if status != "在运正常":
            return None, f"设备当前为「{status}」，暂不能提交校准"

        calibration, message = CalibrationService().submit_for_instrument(entry, operator)
        if calibration is None:
            return None, message
        return self._serialize(entry, operator), "校准申请已提交"

    def _apply_status(self, entry: dict[str, Any], status: str, owner: str) -> None:
        entry["status"] = status
        entry["设备状态"] = status
        entry["pending"] = status == "待校准"
        entry["abnormal"] = status in {"故障停机", "已停用"}
        entry["责任人"] = owner

    def _allowed_actions(self, entry: dict[str, Any], operator: Operator) -> list[str]:
        status = str(entry.get("status") or "")
        if operator.role == ROLE_EQUIPMENT_ADMIN:
            if status == "故障停机":
                return ["恢复在运"]
            if status in {"待校准", "在运正常"}:
                return ["停用设备"]
            return []
        if operator.role == ROLE_INSPECTOR and status == "在运正常":
            return ["提交校准申请"]
        return []

    def _serialize(self, entry: dict[str, Any], operator: Operator | None) -> dict[str, Any]:
        result = dict(entry)
        status = str(entry.get("status") or "")
        result["设备状态"] = status
        allowed = self._allowed_actions(entry, operator) if operator else []
        result["allowed_actions"] = allowed
        result["permissions"] = {
            "can_edit": bool(operator and operator.role == ROLE_EQUIPMENT_ADMIN),
            "can_submit_calibration": "提交校准申请" in allowed,
            "can_restore": "恢复在运" in allowed,
            "can_disable": "停用设备" in allowed,
        }
        return result

    def _find_by_code(self, code: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if str(row.get("设备编号") or "").strip() == code:
                return row
        return None

    @staticmethod
    def _require_admin(operator: Operator) -> None:
        if operator.role != ROLE_EQUIPMENT_ADMIN:
            raise PermissionDenied("设备编号、设备型号与量程范围只能由设备管理员维护")
