from __future__ import annotations

from typing import Any


class SOPReason(str):
    """兼容旧字符串接口，同时携带可供前端 i18n 使用的消息代码和参数。"""

    code: str
    params: dict[str, Any]

    def __new__(cls, text: Any = "", code: str = "", params: dict[str, Any] | None = None):
        instance = super().__new__(cls, str(text or ""));instance.code = str(code or "");instance.params = dict(params or {});return instance


EMPTY_REASON = SOPReason()


def sop_reason(code: str, text: Any, **params: Any) -> SOPReason:return SOPReason(text,code,params)


def ensure_sop_reason(value: Any) -> SOPReason:return value if isinstance(value,SOPReason) else SOPReason(value)


def reason_payload(value: Any, prefix: str = "reason") -> dict[str, Any]:
    normalized = ensure_sop_reason(value)
    return {prefix:str(normalized),f"{prefix}_code":normalized.code,f"{prefix}_params":dict(normalized.params)}


def nested_reason_params(value: Any) -> dict[str, Any]:
    normalized = ensure_sop_reason(value)
    return {"detail":str(normalized),"detailCode":normalized.code,"detailParams":dict(normalized.params)}
