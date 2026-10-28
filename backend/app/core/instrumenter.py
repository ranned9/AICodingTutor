import re

RUNTIME_HEADER = r"""#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* === 内存采集运行时库 === */
typedef struct __mem_heap_record {
    void *addr;
    size_t size;
    int freed;
    struct __mem_heap_record *next;
} __mem_heap_record_t;

static __mem_heap_record_t *__heap_head = NULL;
static int __step_counter = 0;

#define __MAX_STACK_DEPTH 64
static const char *__call_stack[__MAX_STACK_DEPTH];
static char __call_args[__MAX_STACK_DEPTH][256];
static int __call_lines[__MAX_STACK_DEPTH];
static int __stack_depth = 0;
static int __last_trace_line = 0;
static char __locals_bufs[__MAX_STACK_DEPTH][2048];

static void __mem_enter(const char *func, const char *args) {
    if (__stack_depth < __MAX_STACK_DEPTH) {
        __call_stack[__stack_depth] = func;
        __call_lines[__stack_depth] = __last_trace_line;
        if (args) {
            strncpy(__call_args[__stack_depth], args, 255);
            __call_args[__stack_depth][255] = '\0';
        } else {
            __call_args[__stack_depth][0] = '\0';
        }
        __locals_bufs[__stack_depth][0] = '[';
        __locals_bufs[__stack_depth][1] = ']';
        __locals_bufs[__stack_depth][2] = '\0';
    }
    __stack_depth++;
}

static void __mem_exit(void) {
    if (__stack_depth > 0) __stack_depth--;
}

static void __mem_trace(int line);
static void __print_globals(void);

static void __mem_cleanup(int *marker) {
    if (__stack_depth > 1) {
        __mem_trace(__call_lines[__stack_depth - 1]);
    }
    __mem_exit();
}
#define __MEM_CLEANUP int __cleanup_marker __attribute__((cleanup(__mem_cleanup)))

static void __mem_trace(int line) {
    int i, first;
    __mem_heap_record_t *r;
    __last_trace_line = line;
    __step_counter++;
    printf("__SNAP__:{\"step\":%d,\"line\":%d,\"stack_frames\":[", __step_counter, line);
    for (i = 0; i < __stack_depth && i < __MAX_STACK_DEPTH; i++) {
        if (i > 0) printf(",");
        printf("{\"function\":\"%s\",\"args\":\"%s\",\"locals\":%s}", __call_stack[i], __call_args[i], __locals_bufs[i]);
    }
    printf("],\"heap_objects\":[");
    r = __heap_head;
    first = 1;
    int __heap_cnt = 0;
    while (r && __heap_cnt < 256) {
        if (!first) printf(",");
        first = 0;
        printf("{\"address\":\"0x%lx\",\"size\":%d,\"is_freed\":%s,\"content\":[",
               (unsigned long)r->addr, (int)r->size, r->freed ? "true" : "false");
        if (!r->freed && r->size >= (int)sizeof(int)) {
            int *__hp = (int*)r->addr;
            int __hn = (int)(r->size / sizeof(int));
            if (__hn > 8) __hn = 8;
            int __hc = 1;
            int __hj;
            for (__hj = 0; __hj < __hn; __hj++) {
                if (!__hc) printf(",");
                __hc = 0;
                printf("%d", __hp[__hj]);
            }
        }
        printf("]}");
        r = r->next;
        __heap_cnt++;
    }
    printf("],\"globals\":");
    __print_globals();
    printf("}\n");
    fflush(stdout);
}

static void *__tracked_malloc(size_t sz) {
    void *p = malloc(sz);
    if (p) {
        __mem_heap_record_t *r = (__mem_heap_record_t *)malloc(sizeof(__mem_heap_record_t));
        r->addr = p; r->size = sz; r->freed = 0; r->next = __heap_head;
        __heap_head = r;
    }
    return p;
}

static void __tracked_free(void *p) {
    __mem_heap_record_t *r = __heap_head;
    int __cnt = 0;
    while (r && __cnt < 256) {
        if (r->addr == p) { r->freed = 1; break; }
        r = r->next;
        __cnt++;
    }
    free(p);
}
#define malloc(sz) __tracked_malloc(sz)
#define free(ptr) __tracked_free(ptr)
/* === 运行时库结束 === */
"""


class Instrumenter:
    _COMMENT_LINE = re.compile(r'^\s*(//|/\*)')
    _PREPROCESSOR = re.compile(r'^\s*#')
    _BRACE_ONLY = re.compile(r'^\s*[{};]\s*$')
    _INCLUDE_PATTERN = re.compile(r'^\s*#include\s*[<"]')
    _FUNCTION_DEF = re.compile(r'^\s*(?:static\s+)?(?:inline\s+)?(?:const\s+)?[\w\*]+\s+\**(\w+)\s*\(([^;]*)\)\s*\{?\s*$')
    _INLINE_FUNC_BODY = re.compile(
        r'^(\s*(?:static\s+)?(?:inline\s+)?(?:const\s+)?[\w\*]+\s+\**\w+\s*\([^;]*\)\s*\{)(.*)(\}\s*)$'
    )
    _RETURN_STMT = re.compile(r'^\s*return\b')
    _GLOBAL_VAR = re.compile(
        r'^(?:static\s+)?(?:const\s+)?(\w+)\s+(\w+)\s*(?:\[[^\]]*\])?\s*(?:=\s*.*)?;\s*$'
    )
    _TYPE_KEYWORDS = {'if', 'else', 'for', 'while', 'switch', 'return', 'typedef',
                      'struct', 'enum', 'union', 'void', 'unsigned', 'signed',
                      'sizeof', 'break', 'continue', 'case', 'default', 'goto',
                      'do', 'static', 'const', 'extern', 'register', 'auto',
                      'inline', 'volatile'}
    _LOCAL_VAR = re.compile(
        r'^(?:const\s+)?((?:struct\s+)?(?:unsigned\s+)?\w+)\s+(\w+)\s*(?:\[[^\]]*\])?\s*(?:=\s*.*)?;\s*$'
    )
    _MULTI_VAR = re.compile(
        r'^(?:const\s+)?((?:struct\s+)?(?:unsigned\s+)?\w+)\s+(.+);\s*$'
    )
    _STRUCT_FIELD = re.compile(r'^\s*((?:(?:unsigned|signed|long|short)\s+)*(?:int|char|float|double|long|short|_Bool))\s+(\w+)\s*;\s*$')
    _STRUCT_MEMBER_WRITE = re.compile(r'^\s*(\w+)\.(\w+)\s*(?:=|\+=|-=|\+\+|--)')

    @classmethod
    def _is_executable(cls, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if cls._COMMENT_LINE.match(stripped):
            return False
        if cls._PREPROCESSOR.match(stripped):
            return False
        if cls._BRACE_ONLY.match(stripped):
            return False
        return True

    @classmethod
    def _parse_globals(cls, lines: list[str]) -> list[tuple[str, str]]:
        globals_list = []
        in_function = False
        brace_depth = 0
        in_struct = False
        struct_brace = 0
        pending_func = False
        _STRUCT_START = re.compile(r'^(?:typedef\s+)?(?:struct|enum|union)\b')
        _FUNC_SIG = re.compile(r'^\s*[\w\*]+\s+\**\w+\s*\([^;]*\)\s*$')
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or stripped.startswith('//'):
                continue
            if in_struct:
                struct_brace += stripped.count('{') - stripped.count('}')
                if struct_brace <= 0:
                    in_struct = False
                continue
            if _STRUCT_START.match(stripped):
                in_struct = True
                struct_brace = stripped.count('{') - stripped.count('}')
                if struct_brace <= 0:
                    in_struct = False
                continue
            if pending_func:
                if '{' in stripped:
                    in_function = True
                    brace_depth = stripped.count('{') - stripped.count('}')
                pending_func = False
                continue
            if _FUNC_SIG.match(stripped) and '{' not in stripped:
                pending_func = True
                continue
            if '{' in stripped and '(' in stripped and not in_function:
                in_function = True
                brace_depth = stripped.count('{') - stripped.count('}')
                continue
            if in_function:
                brace_depth += stripped.count('{') - stripped.count('}')
                if brace_depth <= 0:
                    in_function = False
                continue
            m = cls._GLOBAL_VAR.match(stripped)
            if m:
                type_str = m.group(1)
                name = m.group(2)
                if type_str not in cls._TYPE_KEYWORDS and name not in cls._TYPE_KEYWORDS:
                    globals_list.append((name, type_str))
        return globals_list

    @classmethod
    def _parse_struct_fields(cls, lines: list[str]) -> dict[str, list[tuple[str, str]]]:
        """Collect simple scalar fields from named struct definitions."""
        structs: dict[str, list[tuple[str, str]]] = {}
        active_name: str | None = None
        brace_depth = 0
        start_pattern = re.compile(r'^\s*struct\s+(\w+)\s*\{')
        for line in lines:
            if active_name is None:
                match = start_pattern.match(line)
                if not match:
                    continue
                active_name = match.group(1)
                structs[active_name] = []
                brace_depth = line.count('{') - line.count('}')
            else:
                brace_depth += line.count('{') - line.count('}')

            if active_name is not None:
                field_match = cls._STRUCT_FIELD.match(line)
                if field_match:
                    structs[active_name].append((field_match.group(1).strip(), field_match.group(2)))
                if brace_depth <= 0:
                    active_name = None
        return structs

    @staticmethod
    def _gen_print_globals(globals_list: list[tuple[str, str]]) -> str:
        if not globals_list:
            return 'static void __print_globals(void) { printf("[]"); }'
        out = []
        for name, type_str in globals_list:
            out.append(f'extern {type_str} {name};')
        out.append('static void __print_globals(void) {')
        out.append('    int __gfirst = 1;')
        out.append('    printf("[");')
        for name, type_str in globals_list:
            if 'float' in type_str or 'double' in type_str:
                fmt = '%f'
            elif 'char' in type_str and '*' not in type_str:
                fmt = '%c'
            elif 'long' in type_str:
                fmt = '%ld'
            else:
                fmt = '%d'
            out.append('    if (!__gfirst) printf(",");')
            out.append('    __gfirst = 0;')
            out.append(
                f'    printf("{{\\"name\\":\\"{name}\\",\\"type\\":\\"{type_str}\\",'
                f'\\"address\\":\\"0x%lx\\",\\"value\\":\\"{fmt}\\"}}", '
                f'(unsigned long)&{name}, {name});'
            )
        out.append('    printf("]");')
        out.append('}')
        return '\n'.join(out)

    @staticmethod
    def _gen_locals_update(
        locals_list: list[tuple[str, str]],
        indent_str: str,
        struct_fields: dict[str, list[tuple[str, str]]] | None = None,
        initialized_struct_fields: dict[str, set[str]] | None = None,
    ) -> str | None:
        if not locals_list:
            return None
        json_parts = []
        fmt_args = []
        for name, type_str in locals_list:
            is_struct = type_str.startswith('struct ')
            is_ptr = '*' in type_str
            if is_struct and struct_fields:
                struct_name = type_str.split()[-1]
                fields = struct_fields.get(struct_name, [])
                initialized = (initialized_struct_fields or {}).get(name)
                for field_type, field_name in fields:
                    field_label = f'{name}.{field_name}'
                    is_initialized = initialized is not None and field_name in initialized
                    fmt_args.append(f'(unsigned long)&{name}.{field_name}')
                    if not is_initialized:
                        json_parts.append(
                            f'{{\\"name\\":\\"{field_label}\\",\\"type\\":\\"{field_type}\\",'
                            f'\\"address\\":\\"0x%lx\\",\\"value\\":\\"uninitialized\\"}}'
                        )
                        continue
                    tokens = field_type.split()
                    if any(kind in tokens for kind in ('float', 'double')):
                        value_fmt = '%f'
                    elif 'char' in tokens:
                        value_fmt = '%d'
                    elif 'long' in tokens:
                        value_fmt = '%ld'
                    else:
                        value_fmt = '%d'
                    json_parts.append(
                        f'{{\\"name\\":\\"{field_label}\\",\\"type\\":\\"{field_type}\\",'
                        f'\\"address\\":\\"0x%lx\\",\\"value\\":\\"{value_fmt}\\"}}'
                    )
                    fmt_args.append(f'{name}.{field_name}')
                if fields:
                    continue
            if is_struct or is_ptr:
                json_parts.append(
                    f'{{\\"name\\":\\"{name}\\",\\"type\\":\\"{type_str}\\",'
                    f'\\"address\\":\\"0x%lx\\",\\"value\\":\\"-\\"}}'
                )
                fmt_args.append(f'(unsigned long)&{name}')
            elif 'float' in type_str or 'double' in type_str:
                json_parts.append(
                    f'{{\\"name\\":\\"{name}\\",\\"type\\":\\"{type_str}\\",'
                    f'\\"address\\":\\"0x%lx\\",\\"value\\":\\"%f\\"}}'
                )
                fmt_args.append(f'(unsigned long)&{name}')
                fmt_args.append(name)
            elif 'char' in type_str:
                json_parts.append(
                    f'{{\\"name\\":\\"{name}\\",\\"type\\":\\"{type_str}\\",'
                    f'\\"address\\":\\"0x%lx\\",\\"value\\":\\"%c\\"}}'
                )
                fmt_args.append(f'(unsigned long)&{name}')
                fmt_args.append(name)
            else:
                json_parts.append(
                    f'{{\\"name\\":\\"{name}\\",\\"type\\":\\"{type_str}\\",'
                    f'\\"address\\":\\"0x%lx\\",\\"value\\":\\"%d\\"}}'
                )
                fmt_args.append(f'(unsigned long)&{name}')
                fmt_args.append(name)
        fmt_str = '[' + ','.join(json_parts) + ']'
        args_str = ', '.join(fmt_args)
        return f'{indent_str}snprintf(__locals_bufs[__stack_depth - 1], sizeof(__locals_bufs[0]), "{fmt_str}", {args_str});'

    @staticmethod
    def _gen_enter_code(func_name: str, params_str: str, indent_str: str) -> list[str]:
        params_str = params_str.strip()
        if not params_str or params_str == 'void':
            return [f'{indent_str}__mem_enter("{func_name}", "");']

        params = []
        for param in params_str.split(','):
            param = param.strip()
            if not param:
                continue
            parts = param.split()
            if len(parts) < 2:
                continue
            name = parts[-1].lstrip('*')
            type_str = ' '.join(parts[:-1])
            if '*' in param:
                fmt = '%p'
            elif 'char' in type_str and '*' not in param:
                fmt = '%c'
            elif 'float' in type_str or 'double' in type_str:
                fmt = '%f'
            else:
                fmt = '%d'
            params.append((name, fmt))

        if not params:
            return [f'{indent_str}__mem_enter("{func_name}", "");']

        lines = [f'{indent_str}char __args_buf[256];']
        fmt_parts = [f'{n}={f}' for n, f in params]
        arg_parts = [n for n, _ in params]
        fmt_str = ', '.join(fmt_parts)
        args_str = ', '.join(arg_parts)
        lines.append(f'{indent_str}snprintf(__args_buf, sizeof(__args_buf), "{fmt_str}", {args_str});')
        lines.append(f'{indent_str}__mem_enter("{func_name}", __args_buf);')
        return lines

    @classmethod
    def _split_inline_functions(cls, lines):
        split_lines = []
        line_numbers = []
        for i, line in enumerate(lines):
            m = cls._INLINE_FUNC_BODY.match(line)
            if m and m.group(2).strip():
                split_lines.append(m.group(1))
                line_numbers.append(i + 1)
                split_lines.append(m.group(2))
                line_numbers.append(i + 1)
                split_lines.append(m.group(3))
                line_numbers.append(i + 1)
            else:
                split_lines.append(line)
                line_numbers.append(i + 1)
        return split_lines, line_numbers

    @classmethod
    def instrument(cls, source_code: str) -> str:
        original_lines = source_code.splitlines()
        lines, line_numbers = cls._split_inline_functions(original_lines)
        globals_list = cls._parse_globals(original_lines)
        struct_fields = cls._parse_struct_fields(original_lines)
        print_globals_code = cls._gen_print_globals(globals_list)
        output_lines: list[str] = []
        includes_processed = False
        in_function = False
        brace_depth = 0
        func_brace_depth = 0
        globals_injected = False
        local_vars: list[tuple[str, str]] = []
        initialized_struct_fields: dict[str, set[str]] = {}
        pending_func = None

        for i, line in enumerate(lines):
            orig_line = line_numbers[i]
            stripped = line.strip()

            if cls._INCLUDE_PATTERN.match(stripped):
                output_lines.append(line)
                continue

            if not includes_processed and not cls._INCLUDE_PATTERN.match(stripped):
                if stripped.startswith('#'):
                    output_lines.append(line)
                    continue
                output_lines.append(RUNTIME_HEADER)
                output_lines.append(print_globals_code)
                includes_processed = True

            m = cls._FUNCTION_DEF.match(line)
            if m and not in_function and not pending_func:
                if '{' in stripped:
                    func_name = m.group(1)
                    params_str = m.group(2) if m.lastindex >= 2 else ''
                    output_lines.append(line)
                    indent = len(line) - len(line.lstrip())
                    indent_str = ' ' * (indent + 4)
                    output_lines.append(indent_str + '__MEM_CLEANUP;')
                    enter_lines = cls._gen_enter_code(func_name, params_str, indent_str)
                    output_lines.extend(enter_lines)
                    brace_depth = stripped.count('{') - stripped.count('}')
                    if brace_depth > 0:
                        in_function = True
                        func_brace_depth = brace_depth
                        local_vars = []
                        initialized_struct_fields = {}
                    else:
                        output_lines.append(indent_str + f'__mem_trace({orig_line});')
                    continue
                else:
                    pending_func = (m.group(1), m.group(2) if m.lastindex >= 2 else '', line)
                    output_lines.append(line)
                    continue

            if pending_func and '{' in stripped and not in_function:
                func_name, params_str, _ = pending_func
                pending_func = None
                output_lines.append(line)
                indent = len(line) - len(line.lstrip())
                indent_str = ' ' * (indent + 4)
                output_lines.append(indent_str + '__MEM_CLEANUP;')
                enter_lines = cls._gen_enter_code(func_name, params_str, indent_str)
                output_lines.extend(enter_lines)
                brace_depth = stripped.count('{') - stripped.count('}')
                in_function = True
                func_brace_depth = brace_depth
                local_vars = []
                initialized_struct_fields = {}
                continue

            is_return = cls._RETURN_STMT.match(stripped) and in_function


            if is_return:
                indent = len(line) - len(line.lstrip())
                locals_code = cls._gen_locals_update(local_vars, ' ' * indent, struct_fields, initialized_struct_fields)
                if locals_code:
                    output_lines.append(locals_code)
                output_lines.append(' ' * indent + f'__mem_trace({orig_line});')

            if '{' in stripped:
                brace_depth += stripped.count('{')
            if '}' in stripped:
                brace_depth -= stripped.count('}')
                if brace_depth <= 0 and in_function:
                    in_function = False
                    brace_depth = 0
                    func_brace_depth = 0
                    output_lines.append(line)
                    continue

            if is_return:
                output_lines.append(line)
            elif cls._is_executable(line) and in_function and brace_depth > 0:
                indent = len(line) - len(line.lstrip())
                locals_code = cls._gen_locals_update(local_vars, ' ' * indent, struct_fields, initialized_struct_fields)
                if locals_code:
                    output_lines.append(locals_code)
                output_lines.append(' ' * indent + f'__mem_trace({orig_line});')
                output_lines.append(line)
                for stmt in stripped.split(';'):
                    stmt = stmt.strip()
                    if not stmt:
                        continue
                    mm = cls._MULTI_VAR.match(stmt + ';')
                    if mm:
                        lt = mm.group(1)
                        if lt not in cls._TYPE_KEYWORDS:
                            for var_decl in mm.group(2).split(','):
                                var_decl = var_decl.strip()
                                name_match = re.match(r'(\w+)', var_decl)
                                if name_match:
                                    ln = name_match.group(1)
                                    if ln not in cls._TYPE_KEYWORDS and not any(ln == v[0] for v in local_vars):
                                        local_vars.append((ln, lt))
                                        if lt.startswith('struct '):
                                            if '=' in stmt:
                                                struct_name = lt.split()[-1]
                                                initialized_struct_fields[ln] = {
                                                    field_name for _, field_name in struct_fields.get(struct_name, [])
                                                }
                                            else:
                                                initialized_struct_fields[ln] = set()
                member_write = cls._STRUCT_MEMBER_WRITE.match(stripped)
                if member_write and member_write.group(1) in initialized_struct_fields:
                    initialized_struct_fields[member_write.group(1)].add(member_write.group(2))
            else:
                output_lines.append(line)

        if not includes_processed:
            output_lines.insert(0, RUNTIME_HEADER)
            output_lines.insert(1, print_globals_code)

        return '\n'.join(output_lines) + '\n'
