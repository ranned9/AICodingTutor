from enum import IntEnum
from typing import Any, Optional

from pydantic import BaseModel


class ErrorCode(IntEnum):
    SUCCESS = 0
    SOURCE_EMPTY = 1001
    BREAKPOINT_INVALID = 1002
    INSTRUMENT_FAILED = 1003
    COMPILE_ERROR = 1004
    RUNTIME_ERROR = 1005
    SANDBOX_LIMIT = 1006
    NOT_FOUND = 1007
    SNAPSHOT_LOAD_FAILED = 1008
    AI_QUESTION_EMPTY = 2001
    AI_NO_SNAPSHOT = 2002
    AI_TIMEOUT = 2003
    AI_UNAVAILABLE = 2004
    UNKNOWN_ERROR = 9999


ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.SUCCESS: "成功",
    ErrorCode.SOURCE_EMPTY: "请先输入C代码",
    ErrorCode.BREAKPOINT_INVALID: "该行不可设置断点",
    ErrorCode.INSTRUMENT_FAILED: "代码预处理失败，请检查代码格式",
    ErrorCode.COMPILE_ERROR: "编译错误",
    ErrorCode.RUNTIME_ERROR: "代码运行异常，已采集快照可回溯",
    ErrorCode.SANDBOX_LIMIT: "代码执行超时或资源超限，已被强制终止",
    ErrorCode.NOT_FOUND: "请求的资源不存在",
    ErrorCode.SNAPSHOT_LOAD_FAILED: "快照加载失败，请重试",
    ErrorCode.AI_QUESTION_EMPTY: "请输入您的问题",
    ErrorCode.AI_NO_SNAPSHOT: "请先执行调试并选择快照节点",
    ErrorCode.AI_TIMEOUT: "AI答疑响应超时，请稍后重试",
    ErrorCode.AI_UNAVAILABLE: "AI服务暂时不可用，请稍后再试",
    ErrorCode.UNKNOWN_ERROR: "系统发生异常，请重试或刷新页面",
}


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "成功"
    data: Optional[Any] = None

    @classmethod
    def ok(cls, data: Any = None, message: str = "成功") -> "ApiResponse":
        return cls(code=ErrorCode.SUCCESS, message=message, data=data)

    @classmethod
    def error(cls, code: ErrorCode, message: Optional[str] = None, data: Any = None) -> "ApiResponse":
        msg = message if message is not None else ERROR_MESSAGES.get(code, "未知错误")
        return cls(code=int(code), message=msg, data=data)


def error_response(code: ErrorCode, message: Optional[str] = None, data: Any = None) -> dict:
    msg = message if message is not None else ERROR_MESSAGES.get(code, "未知错误")
    return {"code": int(code), "message": msg, "data": data}


def ok_response(data: Any = None, message: str = "成功") -> dict:
    return {"code": int(ErrorCode.SUCCESS), "message": message, "data": data}