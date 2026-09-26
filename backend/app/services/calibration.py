"""校准记录业务规则：申请资格、状态流转与设备状态联动。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.auth import ROLE_EQUIPMENT_ADMIN, ROLE_INSPECTOR, Operator
from app.store import store

MODULE = "calibration"
INSTRUMENT_MODULE = "instrument"
STATUS_ORDER = ["待校准", "校准中", "已合格", "不合格"]
ACTION_RULES = {"开始校准": "校准中", "判定合格": "已合格", "判定不合格": "不合格"}


class PermissionDenied(Exception):
    """当前角色无权执行该操作。"""


class CalibrationService:
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
            rows = [row for row in rows if keyword in str(row.get("校准编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._serialize(row, operator) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int, operator: Operator | None = None) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._serialize(entry, operator) if entry is not None else None

    def create_entry(
        self,
        values: dict[str, Any],
        operator: Operator,
    ) -> tuple[dict[str, Any] | None, str]:
        if operator.role != ROLE_INSPECTOR:
            raise PermissionDenied("只有检测人员可以提交校准申请")
        device_key = str(values.get("关联设备") or values.get("设备编号") or "").strip()
        if not device_key:
            return None, "请选择需要校准的设备"
        instrument = self._find_instrument(device_key)
        if instrument is None:
            return None, f"关联设备「{device_key}」不存在"
        return self.submit_for_instrument(instrument, operator)

    def submit_for_instrument(
        self,
        instrument: dict[str, Any],
        operator: Operator,
    ) -> tuple[dict[str, Any] | None, str]:
        if operator.role != ROLE_INSPECTOR:
            raise PermissionDenied("只有检测人员可以提交校准申请")
        status = str(instrument.get("status") or "")
        device_code = str(instrument.get("设备编号") or "").strip()
        if status == "故障停机":
            return None, "故障停机设备不能提交校准，须先由设备管理员恢复在运"
        if status == "已停用":
            return None, "已停用设备不能提交校准，请先联系设备管理员恢复"
        if status == "待校准":
            return None, "该设备已有待处理校准申请，请勿重复提交"
        if status != "在运正常":
            return None, f"设备当前为「{status}」，暂不能提交校准"
        if self._active_application(device_code):
            return None, "该设备已有待处理校准申请，请勿重复提交"

        rows = store.rows(MODULE)
        entry = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "校准编号": self._next_code(rows),
            "关联设备": device_code,
            "校准方式": "待安排",
            "标准物质": "—",
            "校准结果": "待校准",
            "校准日期": date.today().isoformat(),
            "下次校准日": "—",
            "申请人": operator.name,
            "status": STATUS_ORDER[0],
            "pending": True,
            "abnormal": False,
        }
        rows.append(entry)
        instrument["status"] = STATUS_ORDER[0]
        instrument["设备状态"] = STATUS_ORDER[0]
        instrument["pending"] = True
        instrument["abnormal"] = False
        return self._serialize(entry, operator), "校准申请已提交"

    def run_action(
        self,
        entry_id: int,
        action: str,
        operator: Operator,
    ) -> tuple[dict[str, Any] | None, str]:
        if operator.role != ROLE_EQUIPMENT_ADMIN:
            raise PermissionDenied("只有设备管理员可以处理校准记录")
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"校准记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于校准记录可执行范围"
        status = str(entry.get("status") or "")
        if action == "开始校准" and status != "待校准":
            return None, "只有待校准记录可以开始校准"
        if action in {"判定合格", "判定不合格"} and status != "校准中":
            return None, "只有校准中的记录可以判定校准结果"

        target = ACTION_RULES[action]
        entry["status"] = target
        entry["校准状态"] = target
        entry["pending"] = target == "待校准"
        entry["abnormal"] = target == "不合格"
        if action == "判定合格":
            entry["校准结果"] = "合格"
        elif action == "判定不合格":
            entry["校准结果"] = "不合格"
        self._sync_instrument(entry, target, operator)
        return self._serialize(entry, operator), f"校准记录已{action}"

    def _sync_instrument(self, calibration: dict[str, Any], status: str, operator: Operator) -> None:
        device_code = str(calibration.get("关联设备") or "").strip()
        instrument = self._find_instrument(device_code)
        if instrument is None:
            return
        if status == "校准中":
            instrument["status"] = "待校准"
        elif status == "已合格":
            instrument["status"] = "在运正常"
        elif status == "不合格":
            instrument["status"] = "故障停机"
        else:
            return
        instrument["设备状态"] = instrument["status"]
        instrument["pending"] = instrument["status"] == "待校准"
        instrument["abnormal"] = instrument["status"] in {"故障停机", "已停用"}
        instrument["责任人"] = operator.name

    def _active_application(self, device_code: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if str(row.get("关联设备") or "").strip() == device_code and row.get("status") in {"待校准", "校准中"}:
                return row
        return None

    def _find_instrument(self, device_key: str) -> dict[str, Any] | None:
        if device_key.isdigit():
            entry = store.find(INSTRUMENT_MODULE, int(device_key))
            if entry is not None:
                return entry
        for row in store.rows(INSTRUMENT_MODULE):
            if str(row.get("设备编号") or "").strip() == device_key:
                return row
        return None

    def _next_code(self, rows: list[dict[str, Any]]) -> str:
        number = 1
        existing = {str(row.get("校准编号") or "") for row in rows}
        while f"CALI-{number:04d}" in existing:
            number += 1
        return f"CALI-{number:04d}"

    def _allowed_actions(self, entry: dict[str, Any], operator: Operator) -> list[str]:
        if operator.role != ROLE_EQUIPMENT_ADMIN:
            return []
        status = str(entry.get("status") or "")
        if status == "待校准":
            return ["开始校准"]
        if status == "校准中":
            return ["判定合格", "判定不合格"]
        return []

    def _serialize(self, entry: dict[str, Any], operator: Operator | None) -> dict[str, Any]:
        result = dict(entry)
        status = str(entry.get("status") or "")
        result["校准状态"] = status
        allowed = self._allowed_actions(entry, operator) if operator else []
        result["allowed_actions"] = allowed
        result["permissions"] = {
            "can_process": bool(operator and operator.role == ROLE_EQUIPMENT_ADMIN),
            "can_submit": bool(operator and operator.role == ROLE_INSPECTOR),
        }
        return result
