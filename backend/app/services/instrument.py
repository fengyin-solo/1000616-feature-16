"""仪器设备业务规则：角色权限、状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "instrument"
CALIBRATION_MODULE = "calibration"
REQUIRED_FIELDS = ["设备编号", "设备名称", "设备型号"]
# 设备档案字段：设备编号、设备型号、量程范围等维护动作仅设备管理员可执行
MAINTAIN_FIELDS = ["设备编号", "设备名称", "设备型号", "量程范围", "校准周期", "校准到期日", "责任人"]
STATUS_ORDER = ["待校准", "在运正常", "故障停机", "已停用"]

ROLE_ADMIN = "admin"
ROLE_INSPECTOR = "inspector"
ROLE_LABELS = {ROLE_ADMIN: "设备管理员", ROLE_INSPECTOR: "检测人员"}
DEFAULT_ROLE = ROLE_INSPECTOR  # 未声明角色时按最小权限处理

# 动作 -> 目标状态、允许角色、允许的起始状态、是否需要二次确认
ACTION_RULES: dict[str, dict[str, Any]] = {
    "提交校准": {"target": "待校准", "roles": {ROLE_ADMIN, ROLE_INSPECTOR}, "from": {"在运正常", "待校准"}, "confirm": False},
    "恢复在运": {"target": "在运正常", "roles": {ROLE_ADMIN}, "from": {"故障停机"}, "confirm": False},
    "停用设备": {"target": "已停用", "roles": {ROLE_ADMIN}, "from": {"待校准", "在运正常", "故障停机"}, "confirm": True},
}
# 校准记录里视为"进行中"的状态：同一设备存在进行中申请时不重复生成
OPEN_CALIBRATION_STATUSES = {"待校准", "校准中"}


def normalize_role(raw: str | None) -> str:
    """把请求里的角色描述归一到 admin / inspector；识别不了就按最小权限。"""
    text = (raw or "").strip().lower()
    if text in {ROLE_ADMIN, "设备管理员", "管理员"}:
        return ROLE_ADMIN
    if text in {ROLE_INSPECTOR, "检测人员", "检测员"}:
        return ROLE_INSPECTOR
    return DEFAULT_ROLE


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, ROLE_LABELS[DEFAULT_ROLE])


class InstrumentService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
        role: str = DEFAULT_ROLE,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("设备编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._decorate(row, role) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int, *, role: str = DEFAULT_ROLE) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._decorate(entry, role)

    def create_entry(self, values: dict[str, Any], *, role: str) -> tuple[dict[str, Any] | None, str]:
        if role != ROLE_ADMIN:
            return None, f"设备档案（设备编号、设备型号、量程范围）的维护仅设备管理员可执行，当前角色为{role_label(role)}，越权请求已拒绝"
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        code = str(values.get("设备编号") or "").strip()
        if self._find_by_code(code) is not None:
            return None, f"设备编号 {code} 已存在，不能重复登记"
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in MAINTAIN_FIELDS:
            entry[field] = values.get(field)
        entry["status"] = "待校准"
        entry["设备状态"] = "待校准"
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._decorate(entry, role), "仪器设备已登记"

    def update_entry(self, entry_id: int, values: dict[str, Any], *, role: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"仪器设备 {entry_id} 不存在或已归档"
        if role != ROLE_ADMIN:
            return None, f"设备档案（设备编号、设备型号、量程范围）的维护仅设备管理员可执行，当前角色为{role_label(role)}，越权请求已拒绝"
        changes = {field: values[field] for field in MAINTAIN_FIELDS if field in values}
        if not changes:
            return None, f"未提供可维护的字段，设备档案仅支持修改：{'、'.join(MAINTAIN_FIELDS)}"
        new_code = str(changes.get("设备编号") or "").strip()
        if "设备编号" in changes:
            if not new_code:
                return None, "设备编号不能为空"
            existing = self._find_by_code(new_code)
            if existing is not None and int(existing.get("id", 0)) != entry_id:
                return None, f"设备编号 {new_code} 已被其他设备占用"
        entry.update(changes)
        return self._decorate(entry, role), "仪器设备档案已更新"

    def run_action(
        self,
        entry_id: int,
        action: str,
        *,
        role: str,
        confirm: bool = False,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"仪器设备 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于仪器设备可执行范围"
        rule = ACTION_RULES[action]
        if role not in rule["roles"]:
            allowed = "、".join(role_label(item) for item in sorted(rule["roles"]))
            return None, f"「{action}」仅{allowed}可执行，当前角色为{role_label(role)}，越权请求已拒绝"
        status = str(entry.get("status") or "")
        if status == "已停用":
            if action == "停用设备":
                return None, "设备已是已停用状态，重复提交的停用申请不生效"
            return None, "设备已停用，不能再执行校准或恢复操作"
        if action == "提交校准" and status == "故障停机":
            return None, "设备处于故障停机状态，任何人都不能提交校准，需设备管理员先恢复在运"
        if status not in rule["from"]:
            return None, f"设备当前状态为{status}，不能执行「{action}」"
        if action == "提交校准":
            open_record = self._open_calibration(entry)
            if open_record is not None:
                return None, f"设备已存在进行中的校准申请（{open_record.get('校准编号')}），不重复提交"
        if rule["confirm"] and not confirm:
            return None, "停用设备需设备管理员二次确认，请携带确认标记重新提交"

        target = str(rule["target"])
        entry["status"] = target
        entry["设备状态"] = target
        entry["pending"] = target in {"待校准", "故障停机"}
        entry["abnormal"] = target == "故障停机"

        if action == "提交校准":
            record = self._create_calibration_record(entry)
            return self._decorate(entry, role), f"校准申请已提交，校准记录 {record['校准编号']} 已生成"
        if action == "恢复在运":
            return self._decorate(entry, role), "设备已恢复在运，可以正常提交校准"
        return self._decorate(entry, role), "设备已停用"

    def visible_actions(self, entry: dict[str, Any], role: str) -> list[str]:
        """按角色与设备状态计算当前可执行的动作，前端据此渲染按钮。"""
        status = str(entry.get("status") or "")
        actions: list[str] = []
        for action, rule in ACTION_RULES.items():
            if role not in rule["roles"]:
                continue
            if status not in rule["from"]:
                continue
            if action == "提交校准" and self._open_calibration(entry) is not None:
                continue
            actions.append(action)
        return actions

    def _decorate(self, entry: dict[str, Any], role: str) -> dict[str, Any]:
        row = dict(entry)
        row["allowed_actions"] = self.visible_actions(entry, role)
        return row

    def _find_by_code(self, code: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if str(row.get("设备编号", "")) == code:
                return row
        return None

    def _open_calibration(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        code = str(entry.get("设备编号", ""))
        for row in store.rows(CALIBRATION_MODULE):
            if str(row.get("关联设备", "")) == code and row.get("status") in OPEN_CALIBRATION_STATUSES:
                return row
        return None

    def _create_calibration_record(self, entry: dict[str, Any]) -> dict[str, Any]:
        rows = store.rows(CALIBRATION_MODULE)
        record: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        record["校准编号"] = f"CALI-{int(record['id']):04d}"
        record["关联设备"] = entry.get("设备编号")
        record["校准方式"] = "周期校准"
        record["标准物质"] = ""
        record["校准结果"] = ""
        record["校准日期"] = ""
        record["下次校准日"] = ""
        record["校准状态"] = "待校准"
        record["status"] = "待校准"
        record["pending"] = True
        record["abnormal"] = False
        rows.append(record)
        return record
