from app.api.response import ErrorCode, ok_response, error_response


def test_error_code_values():
    assert ErrorCode.SUCCESS == 0
    assert ErrorCode.SOURCE_EMPTY == 1001
    assert ErrorCode.COMPILE_ERROR == 1004
    assert ErrorCode.RUNTIME_ERROR == 1005
    assert ErrorCode.UNKNOWN_ERROR == 9999


def test_ok_response_format():
    r = ok_response({"key": "value"})
    assert r["code"] == 0
    assert r["message"] == "成功"
    assert r["data"] == {"key": "value"}


def test_ok_response_no_data():
    r = ok_response()
    assert r["code"] == 0
    assert r["data"] is None


def test_error_response_default_message():
    r = error_response(ErrorCode.COMPILE_ERROR)
    assert r["code"] == 1004
    assert r["message"] == "编译错误"
    assert r["data"] is None


def test_error_response_custom_message():
    r = error_response(ErrorCode.RUNTIME_ERROR, "自定义错误")
    assert r["code"] == 1005
    assert r["message"] == "自定义错误"


def test_error_response_with_data():
    r = error_response(ErrorCode.COMPILE_ERROR, "error", {"line": 5})
    assert r["data"] == {"line": 5}