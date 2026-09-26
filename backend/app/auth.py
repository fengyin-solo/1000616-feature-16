"""接口访问身份与角色校验。"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

ROLE_EQUIPMENT_ADMIN = "设备管理员"
ROLE_INSPECTOR = "检测人员"
ROLES = (ROLE_EQUIPMENT_ADMIN, ROLE_INSPECTOR)


@dataclass(frozen=True)
class Operator:
    role: str
    name: str


def _operator(role: str | None, name: str | None) -> Operator | None:
    if not role:
        return None
    if role not in ROLES:
        raise HTTPException(status_code=403, detail=f"未知角色「{role}」，无权操作仪器设备")
    display_name = (name or "").strip() or role
    return Operator(role=role, name=display_name)


def get_optional_operator(
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    x_user_name: str | None = Header(default=None, alias="X-User-Name"),
) -> Operator | None:
    """读取当前登录人；查询接口允许匿名访问，但不返回任何操作权限。"""
    return _operator(x_user_role, x_user_name)


def get_operator(
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    x_user_name: str | None = Header(default=None, alias="X-User-Name"),
) -> Operator:
    operator = _operator(x_user_role, x_user_name)
    if operator is None:
        raise HTTPException(status_code=403, detail="缺少当前用户角色信息，请求已拒绝")
    return operator


def require_equipment_admin(operator: Operator = Depends(get_operator)) -> Operator:
    """仅允许设备管理员执行设备维护类操作。"""
    if operator.role != ROLE_EQUIPMENT_ADMIN:
        raise HTTPException(status_code=403, detail="只有设备管理员可以维护仪器设备")
    return operator


def require_inspector(operator: Operator = Depends(get_operator)) -> Operator:
    """检测人员可提交校准申请。"""
    if operator.role != ROLE_INSPECTOR:
        raise HTTPException(status_code=403, detail="只有检测人员可以提交校准申请")
    return operator
