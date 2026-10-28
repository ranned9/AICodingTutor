from fastapi import APIRouter

from app.api.response import ErrorCode, ok_response, error_response
from app.services.case_library import CaseLibrary

router = APIRouter(prefix="/api/cases", tags=["案例库"])


@router.get("")
async def list_cases():
    cases = CaseLibrary.list_cases()
    return ok_response(cases)


@router.get("/{case_id}")
async def get_case(case_id: str):
    case = CaseLibrary.get_case(case_id)
    if case is None:
        return error_response(ErrorCode.NOT_FOUND, "案例不存在")
    return ok_response({
        "case_id": case.case_id,
        "title": case.title,
        "category": case.category,
        "code": case.code,
    })