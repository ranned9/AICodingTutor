from app.services.case_library import CaseLibrary


def test_list_cases_returns_8_cases():
    cases = CaseLibrary.list_cases()
    assert len(cases) == 8


def test_list_cases_has_required_fields():
    cases = CaseLibrary.list_cases()
    for c in cases:
        assert "case_id" in c
        assert "title" in c
        assert "category" in c


def test_list_cases_ids():
    cases = CaseLibrary.list_cases()
    ids = {c["case_id"] for c in cases}
    expected = {"basic_var", "stack_demo", "malloc_free", "pointer_basic",
                "pointer_array", "struct_demo", "wild_pointer", "global_var"}
    assert ids == expected


def test_get_case_existing():
    case = CaseLibrary.get_case("basic_var")
    assert case is not None
    assert case.case_id == "basic_var"
    assert case.title == "基础变量与栈帧"
    assert "int main" in case.code


def test_get_case_nonexistent():
    case = CaseLibrary.get_case("nonexistent")
    assert case is None


def test_wild_pointer_case_content():
    case = CaseLibrary.get_case("wild_pointer")
    assert case is not None
    assert "malloc" in case.code
    assert "free" in case.code
    assert "*p = 200" in case.code


def test_stack_demo_case_has_recursion():
    case = CaseLibrary.get_case("stack_demo")
    assert case is not None
    assert "factorial" in case.code
    assert "factorial(n - 1)" in case.code