from __future__ import annotations
import re
from typing import Any

from .models import MIRecord, MIParseError


def _unescape_string(s: str) -> str:
    result = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt == 'n':
                result.append('\n')
            elif nxt == 't':
                result.append('\t')
            elif nxt == 'r':
                result.append('\r')
            elif nxt == '"':
                result.append('"')
            elif nxt == '\\':
                result.append('\\')
            elif nxt == "'":
                result.append("'")
            elif nxt == 'x' and i + 3 < len(s):
                hex_str = s[i + 2:i + 4]
                try:
                    result.append(chr(int(hex_str, 16)))
                    i += 4
                    continue
                except ValueError:
                    result.append(s[i])
            else:
                result.append(s[i])
                result.append(nxt)
            i += 2
        else:
            result.append(s[i])
            i += 1
    return ''.join(result)


def _parse_value(s: str, start: int) -> tuple[Any, int]:
    if start >= len(s):
        return None, start

    ch = s[start]

    if ch == '"':
        end = start + 1
        while end < len(s):
            if s[end] == '\\' and end + 1 < len(s):
                end += 2
            elif s[end] == '"':
                break
            else:
                end += 1
        raw_str = s[start + 1:end]
        return _unescape_string(raw_str), end + 1

    if ch == '{':
        return _parse_tuple(s, start)

    if ch == '[':
        return _parse_list(s, start)

    end = start
    while end < len(s) and s[end] not in ',}]':
        end += 1
    token = s[start:end].strip()
    if token == '':
        return None, end
    return token, end


def _parse_tuple(s: str, start: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    i = start + 1
    while i < len(s) and s[i] != '}':
        while i < len(s) and s[i] in ' \t':
            i += 1
        if i >= len(s) or s[i] == '}':
            break
        key_end = i
        while key_end < len(s) and s[key_end] != '=':
            key_end += 1
        key = s[i:key_end].strip()
        i = key_end + 1
        value, i = _parse_value(s, i)
        if key in result:
            if isinstance(result[key], list):
                result[key].append(value)
            else:
                result[key] = [result[key], value]
        else:
            result[key] = value
        while i < len(s) and s[i] in ' \t,':
            i += 1
    return result, i + 1


def _parse_list(s: str, start: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    i = start + 1
    while i < len(s) and s[i] != ']':
        while i < len(s) and s[i] in ' \t,':
            i += 1
        if i >= len(s) or s[i] == ']':
            break
        if s[i] in '{["':
            value, i = _parse_value(s, i)
            result.append(value)
        else:
            eq_idx = i
            while eq_idx < len(s) and s[eq_idx] not in '=,]}':
                eq_idx += 1
            if eq_idx < len(s) and s[eq_idx] == '=':
                key = s[i:eq_idx].strip()
                i = eq_idx + 1
                value, i = _parse_value(s, i)
                result.append({key: value})
            else:
                value, i = _parse_value(s, i)
                result.append(value)
        while i < len(s) and s[i] in ' \t,':
            i += 1
    return result, i + 1


def _parse_payload(s: str) -> dict[str, Any]:
    if not s:
        return {}
    result: dict[str, Any] = {}
    i = 0
    while i < len(s):
        while i < len(s) and s[i] in ' \t,':
            i += 1
        if i >= len(s):
            break
        key_end = i
        while key_end < len(s) and s[key_end] != '=':
            key_end += 1
        if key_end >= len(s):
            break
        key = s[i:key_end].strip()
        i = key_end + 1
        value, i = _parse_value(s, i)
        if key in result:
            if isinstance(result[key], list):
                result[key].append(value)
            else:
                result[key] = [result[key], value]
        else:
            result[key] = value
        while i < len(s) and s[i] in ' \t,':
            i += 1
    return result


_TOKEN_RE = re.compile(r'^(\d+)(.*)$')


def parse_record(line: str) -> MIRecord | None:
    if not line or line.strip() == '':
        return None

    stripped = line.rstrip('\r\n')

    if stripped == '(gdb)':
        return MIRecord(kind='prompt', raw=line)

    m = _TOKEN_RE.match(stripped)
    token: int | None = None
    rest = stripped
    if m:
        token = int(m.group(1))
        rest = m.group(2)

    if not rest:
        return MIRecord(token=token, kind='unknown', raw=line)

    ch = rest[0]

    if ch == '^':
        comma_idx = rest.find(',')
        if comma_idx == -1:
            klass = rest[1:]
            payload = {}
        else:
            klass = rest[1:comma_idx]
            payload = _parse_payload(rest[comma_idx + 1:])
        return MIRecord(token=token, kind='result', klass=klass, payload=payload, raw=line)

    if ch == '*':
        comma_idx = rest.find(',')
        if comma_idx == -1:
            klass = rest[1:]
            payload = {}
        else:
            klass = rest[1:comma_idx]
            payload = _parse_payload(rest[comma_idx + 1:])
        return MIRecord(token=token, kind='exec', klass=klass, payload=payload, raw=line)

    if ch == '=':
        comma_idx = rest.find(',')
        if comma_idx == -1:
            klass = rest[1:]
            payload = {}
        else:
            klass = rest[1:comma_idx]
            payload = _parse_payload(rest[comma_idx + 1:])
        return MIRecord(token=token, kind='notify', klass=klass, payload=payload, raw=line)

    if ch == '~':
        return _parse_stream_record(line, token, 'console')
    if ch == '@':
        return _parse_stream_record(line, token, 'target')
    if ch == '&':
        return _parse_stream_record(line, token, 'log')

    return MIRecord(token=token, kind='unknown', raw=line)


def _parse_stream_record(line: str, token: int | None, kind: str) -> MIRecord:
    stripped = line.rstrip('\r\n')
    if len(stripped) < 2 or stripped[1] != '"':
        return MIRecord(token=token, kind=kind, payload={'text': stripped[1:]}, raw=line)
    end = len(stripped) - 1
    if stripped[end] == '"':
        text = _unescape_string(stripped[2:end])
    else:
        text = _unescape_string(stripped[2:])
    return MIRecord(token=token, kind=kind, payload={'text': text}, raw=line)