import sys
sys.path.insert(0, "backend")

from app.debugger.mi_parser import parse_record
from app.debugger.models import MIParseError


def test_parse_done():
    r = parse_record('2^done')
    assert r.kind == "result"
    assert r.klass == "done"
    assert r.token == 2


def test_parse_done_with_payload():
    r = parse_record('3^done,value="42"')
    assert r.kind == "result"
    assert r.klass == "done"
    assert r.payload["value"] == "42"


def test_parse_error():
    r = parse_record('3^error,msg="No symbol"')
    assert r.klass == "error"
    assert "No symbol" in r.payload["msg"]


def test_parse_stopped():
    r = parse_record('*stopped,reason="breakpoint-hit",bkptno="1"')
    assert r.kind == "exec"
    assert r.klass == "stopped"
    assert r.payload["reason"] == "breakpoint-hit"


def test_parse_stopped_with_frame():
    r = parse_record('*stopped,reason="end-stepping-range",frame={func="main",line="22"}')
    assert r.payload["reason"] == "end-stepping-range"
    frame = r.payload["frame"]
    assert frame["func"] == "main"
    assert frame["line"] == "22"


def test_parse_thread_created():
    r = parse_record('=thread-created,id="1",group-id="i1"')
    assert r.kind == "notify"
    assert r.klass == "thread-created"
    assert r.payload["id"] == "1"


def test_parse_console_stream():
    r = parse_record('~"GNU gdb 9.2\\n"')
    assert r.kind == "console"
    assert "GNU gdb" in r.payload["text"]
    assert "\n" in r.payload["text"]


def test_parse_log_stream():
    r = parse_record('&"warning: some warning\\n"')
    assert r.kind == "log"


def test_parse_target_stream():
    r = parse_record('@"target output"')
    assert r.kind == "target"


def test_parse_prompt():
    r = parse_record('(gdb)')
    assert r.kind == "prompt"


def test_parse_empty_line():
    assert parse_record('') is None
    assert parse_record('   ') is None


def test_parse_nested_tuple():
    r = parse_record('5^done,bkpt={number="1",addr="0x401000",enabled="y"}')
    assert r.klass == "done"
    bkpt = r.payload["bkpt"]
    assert bkpt["number"] == "1"
    assert bkpt["addr"] == "0x401000"


def test_parse_list():
    r = parse_record('6^done,stack=[frame={level="0",func="main"},frame={level="1",func="add"}]')
    stack = r.payload["stack"]
    assert isinstance(stack, list)
    assert len(stack) == 2
    assert stack[0]["frame"]["func"] == "main"


def test_parse_empty_list():
    r = parse_record('7^done,variables=[]')
    assert r.payload["variables"] == []


def test_parse_string_with_commas():
    r = parse_record('8^done,msg="a, b, c"')
    assert r.payload["msg"] == "a, b, c"


def test_parse_string_with_braces():
    r = parse_record('9^done,value="{x = 3, y = 7}"')
    assert r.payload["value"] == "{x = 3, y = 7}"


def test_parse_escaped_quotes():
    r = parse_record('~"He said \\"hello\\"\\n"')
    assert '\\"hello\\"' in r.payload["text"] or '"hello"' in r.payload["text"]


def test_parse_repeated_keys():
    r = parse_record('10^done,frame={func="main"},frame={func="add"}')
    frames = r.payload["frame"]
    assert isinstance(frames, list)
    assert len(frames) == 2


def test_parse_unknown_record():
    r = parse_record('???unknown')
    assert r.kind == "unknown"