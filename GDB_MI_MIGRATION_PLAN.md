# 从正则插桩迁移到真实 C 编译与调试：实施方案

## 目标

把当前“Python 正则识别 C 代码 → 改写源码插入采集代码 → 一次性运行并回放”的核心链路，逐步迁移为：

> GCC/Clang 编译原始源码并生成调试信息 → GDB/LLDB 真正控制程序执行 → 后端读取调试器提供的源码位置、栈帧、变量、结构体和数组 → 前端展示暂停点及历史轨迹。

这不是自己实现 C 编译器。C 语法和语言语义交给成熟编译器，调试符号和变量展开交给调试器；Python 负责启动/管理进程、发送调试命令、解析调试协议并转换为项目快照模型。

本项目当前机器已能通过命令查找到 `gcc.exe` 和 `gdb.exe`，适合先做 Windows + MinGW 的技术验证。正式实施前仍要确认两者版本、位数和目标架构兼容，并验证 GDB MI 接口可用。

## 当前架构为什么需要替换

目前 `backend/app/core/instrumenter.py` 用正则按行识别函数、局部变量和结构体字段，再生成 C 代码；数组、多行声明、复杂作用域、宏、函数指针等都可能超出它能可靠理解的范围。此类问题不是继续增加几个正则就能根治的：正则并没有完整 C 语法树、类型信息和作用域语义。

目前 `SessionManager.start_debug` 会立即完成编译和运行，再把 stdout 解析成完整快照。因此现有“单步/继续/停止”实质上主要是浏览预采集结果，并非暂停真实运行进程。

## 推荐架构

```text
浏览器
  │ HTTP：start / step / next / continue / stop / snapshots
  ▼
FastAPI 路由
  ▼
DebugSessionManager（管理会话状态和历史帧）
  ├── Compiler：原始源码 → 带调试信息的可执行文件
  ├── DebuggerSession：每个会话一个 GDB/MI 子进程
  ├── MI transport/parser：命令 token、响应、异步停止事件
  ├── VariableReader：递归读取局部/全局变量及聚合类型
  └── SnapshotAdapter：统一转换为前端使用的快照 JSON
```

建议把“MI 协议适配层”和“业务会话逻辑”分开。不要在 FastAPI 路由里直接拼 GDB 命令，也不要把 MI 文本解析塞进现有 `SessionManager`。

目录可以按现有风格增加：

```text
backend/app/debugger/
  mi_transport.py       # 子进程读写、token 对应、异步记录队列
  mi_parser.py          # GDB/MI 语法解析器
  gdb_session.py        # 一次调试会话的 GDB 命令封装
  compiler.py           # 编译命令和诊断信息
  variable_reader.py    # MI 变量对象递归展开
  snapshot_adapter.py   # GDB 停止状态 -> MemorySnapshot
```

文件名只是建议，可以贴合项目已有结构，但模块边界应保留。

## 一次真实调试会话的工作流

### 1. 编译原始 C 源码

- 不对用户源码做正则插桩，编译器输入应尽可能保持原样。
- 使用调试友好选项，例如 GCC/MinGW：`-g3 -O0 -fno-inline`；建议同时启用合适的 C 标准，例如 `-std=c11`。具体参数需按安装的 GCC 验证。
- 需要捕获编译器 stderr、退出码和超时，并把诊断文件名/行列号转换为现有错误响应格式。
- 为每个会话创建独立的临时工作目录，源码路径固定，编译后保留到会话结束；结束、异常或过期清理时删除整个会话目录。
- 不要在全局共享固定的 `program.exe` 文件名，避免并发会话互相覆盖。

### 2. 启动 GDB/MI

以 MI2 模式启动独立子进程，大致形态：

```text
gdb --quiet --nx --interpreter=mi2
```

通过标准输入发送 MI 命令，持续读取 stdout 与 stderr。编译出的程序路径应使用正确的 Windows 路径引用/转义方式。

初始化命令可包括：

```text
-gdb-set pagination off
-gdb-set confirm off
-file-exec-and-symbols ".../program.exe"
-gdb-set print pretty on
```

然后在 `main` 或用户断点处运行。GDB 对源码断点可能会调整到下一条可执行指令；后端应读取 GDB 返回的实际断点位置，不要假设请求行一定能停住。

### 3. 从运行/停止事件构造快照

每次 GDB 返回停止事件（例如断点命中、单步完成、程序退出或信号）时：

1. 从停止记录取得原因、线程、帧和源码位置。
2. 查询当前栈帧。
3. 查询当前帧局部变量及参数。
4. 查询全局变量（先用 MI 符号查询命令做版本验证；若目标 GDB MI 版本不支持，再设计兼容方案，不能静默漏掉全局变量）。
5. 对结构体、数组等聚合变量建立 GDB variable object，并递归获取子项。
6. 转换为统一的 `MemorySnapshot`，追加到会话历史并落盘。
7. 将最新快照返回前端，更新代码行高亮和内存视图。

推荐验证和评估这些 MI 命令（命令具体可用性要通过目标 GDB 版本确认）：

- `-exec-run`、`-exec-next`、`-exec-step`、`-exec-continue`、`-exec-interrupt`
- `-stack-list-frames`、`-stack-list-variables --all-values`
- `-var-create`、`-var-list-children --all-values`、`-var-evaluate-expression`、`-var-delete`
- `-symbol-info-variables`（用于全局符号发现，先做兼容性验证）
- `-break-insert`、`-break-list`、`-break-delete`

注意：以 `*stopped` 等异步 MI 记录作为真正的停止信号。`-exec-continue` 一类命令的 token 响应不代表程序已经停下；必须等待对应停止事件后才能采样变量。

## MI 解析与异步管理要求

MI 输出不是“一行一个简单 JSON”。记录中有 token、结果类记录、异步执行/通知记录、流记录，以及可嵌套的 tuple/list 和 C 风格转义字符串。不要用一组正则从输出里抓变量值。

实现要求：

- 编写有限但符合 MI grammar 的 tokenizer/parser，至少支持 `^result`、`*exec`、`=notify`、`~console`、`@target`、`&log`、字符串转义、tuple/list、重复键值结果。
- 为每条发出的命令分配 token；只把对应 token 的 `^done`/`^error` 交给该命令等待者。
- 异步 `*stopped`、`=thread-created` 等记录进入独立事件队列，不得误认为命令结果。
- stdout reader 必须持续读取，不能等发送命令后才读，避免 GDB 管道阻塞。
- stderr 单独收集用于日志诊断；日志不得包含 AI 密钥等无关机密。
- 设置命令超时、会话超时和程序运行超时；发生协议错误时终止会话并返回可理解错误。
- MI 解析器用已知输出样例和边界字符串做单元测试，不以真实一次运行作为唯一保障。

## 前后端会话语义调整

真实调试会话需要保留活进程，和现有“开始时全部跑完”的后端模型不同。

- `POST /api/debug/start`：编译、启动 GDB、设置断点、运行至第一个可展示停止点，并返回初始快照与 session id。
- `POST /api/debug/{id}/step`：执行一步（明确是 step-over 还是 step-into；可先将现有“单步”定义为 step-over），等待停止事件，采集新快照。
- `POST /api/debug/{id}/continue`：继续到下一个断点、程序退出或运行错误，返回停止原因和快照。
- `POST /api/debug/{id}/stop`：中断/终止目标进程和 GDB，随后清理会话资源；必须能处理中断期间的竞态。
- 快照查询/时间线回放：用户拖动到过去步骤时读取历史快照，不应让 GDB 倒退执行。
- 会话状态至少区分 `starting/running/paused/completed/failed/stopped`；前端按钮根据服务器状态启用。
- 进程退出、正常结束、信号终止、超时、编译失败要有不同状态和提示。

可尽量沿用现有 API 路径，但需明确请求响应含义。若单步/继续改为异步长操作，FastAPI 路由不能阻塞事件循环；选用异步子进程或专门工作线程并做好会话串行化。

## 快照模型建议

当前 `LocalVariable` 只有 `name/type/address/value`，不足以表达数组和结构体。建议扩展而不破坏已有客户端字段：

```json
{
  "name": "p",
  "type": "struct Point",
  "kind": "struct",
  "value": "{...}",
  "address": "0x...",
  "children": [
    {"name": "x", "type": "int", "kind": "scalar", "value": "3", "children": []},
    {"name": "y", "type": "int", "kind": "scalar", "value": "7", "children": []}
  ],
  "available": true,
  "unavailable_reason": null
}
```

数组可以有 `kind: "array"`、长度/索引子项；指针要区分指针自身的地址、保存的目标地址、目标是否可读，以及目标展开的子项。递归展开要有最大深度、最大子项数量和总字节/时间预算，避免大型数组、循环指针或深链表拖垮界面/后端。

未初始化变量、优化后不可用变量、超出范围的变量，应以 `available=false` 和原因表示；不要为了填满 UI 读取未初始化内存，也不要把无法读取的值伪装成 `0` 或 `-`。

为兼容现有前端，可以在迁移早期同时保留扁平的 `locals` 字段和新增递归字段，然后分阶段让 Canvas 使用 `children` 树；完成后再决定是否清理旧字段。

## 内存地址和“真实内存图”的边界

调试器可以读取变量、类型和值，也通常能给出变量地址；这不代表能获得操作系统层面的完整物理内存快照。ASLR 会使地址每次运行变化；编译器和调试器可能无法提供某些不可寻址值。项目展示应称为“调试器可见变量/对象视图”或“程序状态快照”，不要承诺完整进程内存转储。

对栈和堆的归类应结合变量作用域、类型和调试信息；不要仅凭地址范围猜。GDB 对 `malloc` 返回对象未必能自动知道精确分配长度。第一版可先展示堆指针和可安全读取的目标类型，分配块大小作为后续能力或通过调试器 catchpoint/运行时拦截单独设计。

## Windows 与比赛环境验证

当前工作环境能找到 GCC 和 GDB，但 CodeArts 机器、评委电脑或部署服务器未必有相同配置。实施前应记录并检测：

- `gcc --version`、`gdb --version`、目标三元组/位数。
- GDB 是否启用 MI2、是否支持当前 GCC 生成的 DWARF 调试信息。
- Windows 路径、带空格路径、中文目录、临时路径和引号转义。
- GDB 是否能启动 MinGW 生成的程序；GDB 与 GCC 是否来自兼容的同一工具链。
- 调试器/编译器未安装或启动失败时给出启动页诊断，不要等到运行案例才暴露问题。

如果最终部署在 Linux/容器，建议把 Linux GCC + GDB 作为服务端统一运行环境，避免要求每台学生电脑装完整工具链。但不能只依赖 GDB 解决安全问题：不可信原生代码仍需容器/低权限账户隔离、网络/文件系统限制、资源限制和并发控制。

## 分阶段迁移计划

### 阶段 0：工具链探针（先做，不改现有主链路）

建立一个独立验证脚本或测试程序：编译并调试一个小型 C 文件，证明 MI2 可以启动、命中断点、单步，并读到局部变量/参数/全局变量。脚本只用于开发验证，不要把临时代码耦合进正式 API。

验证程序至少包含：数组、跨行声明、结构体、指针、循环、函数调用、全局变量。记录 GDB 原始 MI 输出，确认版本特性和目标变量的真实返回结构。

**阶段门槛：**未证明当前 Windows 工具链能够稳定读出变量和子项之前，不开始替换现有调试链路。

### 阶段 1：实现编译器和 MI 独立模块

- 新增编译器封装、MI parser、MI transport、GDB session。
- 单元测试编译错误映射、MI 字符串转义/嵌套解析、token 对应、异步停止事件。
- 通过集成测试启动 GDB、断点、next/step/continue、退出和超时。
- 旧 `Instrumenter` 仍保留，不接入新 API，保证现有版本仍可演示。

### 阶段 2：后端新执行模式

- 增加可显式切换的 `engine=gdb` 或开发配置开关；不要默认删除旧路径。
- 会话管理器实现活进程生命周期和串行命令队列。
- 首先支持标量、函数帧、断点、step-over、continue 和停止。
- 快照保存格式继续沿用 `SnapshotStore`，同时记录 engine/schema 版本。

### 阶段 3：数组/结构体/指针树

- 通过 GDB variable objects 递归展开聚合类型。
- 限制展开数量和深度；UI 使用可展开树，而不是把结构体所有子项平铺。
- 逐类增加数组、嵌套结构体、结构体数组、指针、空指针/不可用指针的测试。
- 校验变量在作用域内、离开作用域后消失；递归调用中同名局部变量属于不同栈帧。

### 阶段 4：前端新语义和切换

- 更新前端状态处理：运行中、暂停、完成、异常；单步/继续必须等待后端返回的新停止帧。
- 将“当前停止帧”与“历史回看位置”分开，时间线浏览过去时不要误触发调试器继续。
- 对比新旧引擎运行同一组案例；新引擎覆盖率达标后再把 GDB 设为默认。
- 旧正则插桩可先保留为实验/回滚模式，稳定后再单独移除。

## 必须覆盖的测试矩阵

### C 语言特性

- 单行函数、函数头跨行、声明跨行、多个变量声明。
- 一维/多维数组、数组初始化、数组参数。
- 结构体、嵌套结构体、结构体数组、结构体指针。
- 指针取址/解引用/空指针；无效指针不得让调试 UI 或后端崩溃。
- `for/while` 多轮循环、递归、同名局部变量、局部变量离开作用域。
- 全局变量和静态变量。
- 编译错误、运行时信号、正常 return、无限循环/超时。

### 调试和协议

- 断点实际解析行与请求行不同的情况。
- 连续 step、continue 到断点、continue 到程序退出。
- 同一会话连续操作、两个会话并行、停止与 step/continue 竞争。
- MI 字符串含引号、反斜杠、换行、UTF-8；异步输出穿插命令响应。
- GDB 意外退出、编译器缺失、版本不兼容、命令超时。
- 服务重启或会话过期后，子进程和临时目录能够回收。

## 不要这样迁移

- 不要把现有 Python 正则换成更多正则，也不要自己解析 C 声明和作用域。
- 不要把 GDB MI 原始输出直接返回前端。
- 不要假设 MI 输出始终按固定顺序、固定空格或固定键顺序出现。
- 不要在 `exec-continue` 返回后立即采样；等待 `*stopped`。
- 不要将所有数组无上限展开。
- 不要在正式切换前删除 `Instrumenter` 旧链路；保留回滚路径。
- 不要把调试器进程本身误认为代码沙箱。

## 可直接交给 CodeArts 的首轮任务

请先只完成“阶段 0：工具链探针”，不要修改当前产品的调试主链路。使用当前 GCC/GDB 编译一个测试 C 程序，并通过 `gdb --interpreter=mi2` 验证：启动、在指定源码行断点停止、单步继续、读取局部变量/全局变量、读取数组和结构体子项、正常退出。提交可重复执行的验证脚本/测试和一份简短结果报告，报告包含 GCC/GDB 版本、关键 MI 原始响应、未支持的命令或变量类型、Windows 路径注意事项。只有阶段 0 全部通过后，再提出阶段 1 的实现 PR/改造方案。

## 交付验收标准

迁移完成后，以下结果必须能现场复现：

1. 跨行定义和数组程序无需 Python 插桩即可由真实 C 编译器编译。
2. 点“单步”时真实被调试进程前进到下一源码位置，而不是只从已生成列表取下一项。
3. 结构体和数组由调试信息读取并能在前端树形展开。
4. 断点依据 GDB 实际停止位置反馈，代码高亮和快照行号一致。
5. 正常结束、编译错误、运行错误、超时、用户停止都有清晰状态，并释放 GDB/目标进程和临时文件。
6. 自动化单元/集成测试覆盖 MI parser 与上述代表性 C 案例。

---

## 附录 A：详细工程设计（供分任务实施）

本附录把迁移方向细化为模块职责、调用顺序、数据契约和测试要求。实现时如发现目标 GDB 版本的命令输出不同，应以阶段 0 保存的真实 MI 输出为准，并更新 parser/测试；不要为匹配单个输出样例而在业务代码里添加字符串特判。

### A1. 模块职责和建议接口

以下为接口草案，不要求类名逐字照抄，但职责需要分离。

#### `Compiler`

输入源码和会话目录，输出可执行文件路径或结构化诊断。

```python
@dataclass
class CompileDiagnostic:
    severity: str
    message: str
    file: str | None = None
    line: int | None = None
    column: int | None = None

@dataclass
class CompileOutcome:
    success: bool
    executable: Path | None
    diagnostics: list[CompileDiagnostic]
    duration_ms: int
```

编译器路径、标准版本和参数由配置提供，不要在请求里允许用户任意传入编译参数。第一版建议固定 C11、`-g3 -O0 -fno-inline`，源码和产物均位于每会话目录。对 Windows 命令行使用 `subprocess` 参数数组，不经 shell 拼接。限制源码长度、编译时限和产物目录权限。

#### `MIParser`

提供纯函数式解析接口：

```python
parse_record(line: str) -> MIRecord | None
```

建议内部结构：

```python
MIRecord(
    token=12,                 # 可为空
    kind="result",            # result / exec / notify / console / target / log / prompt
    klass="done",             # 例如 done / running / error / stopped
    payload={...},             # 已解析的 tuple/list/value
    raw="12^done,..."
)
```

MI grammar 的字符串转义需要解码，但 `raw` 仍保留用于诊断。重复键值不能简单覆盖：如 MI 返回多项 `result`，保留列表或按 grammar 建模。解析错误应返回带原始行的协议异常，不要悄悄当空对象。

最小 parser 单测应覆盖：

- `12^done`、`12^error,msg="..."`、`*stopped,reason="end-stepping-range"`。
- `=thread-created,id="1",group-id="i1"`。
- `~"console text\\n"` 和含 UTF-8、转义引号、反斜线的字符串。
- 嵌套 tuple、list、空列表、字符串列表、混合 `result` 列表。
- 字符串中的逗号/括号不应被当成结构分隔符。
- 不完整/非法记录应报出可定位错误。

#### `MITransport`

职责是 GDB 子进程读写和命令/事件复用，不处理 C 变量的业务含义。

```python
await transport.start()
record = await transport.command("-gdb-version", timeout=3.0)
stop = await transport.wait_for_stop(timeout=10.0)
await transport.close(graceful=True)
```

实现要点：

1. 每个命令增加递增 token，例如 `17-stack-list-frames`。
2. 启动独立 reader 持续读取 stdout，按行解析 MI 记录。
3. 有 token 的 result 记录投递到对应 Future；无 token 的异步记录投递事件队列；流记录送日志/控制台通道。
4. 写命令需要有单一写锁，防止并发写入拼接。
5. `^running` 只表示命令已受理。执行类命令必须额外等待 `*stopped`，并要能区分本次操作等待到的停止事件。
6. 支持命令超时、GDB 提前退出、stdout EOF、取消请求。任何终止路径都唤醒等待中的 Future/队列消费者。
7. 单会话所有改变执行状态的命令必须串行。可用 `asyncio.Lock` 或会话 actor/mailbox；不能并发 step 和 continue。

GDB MI 的 prompt 和控制台 stream 可能出现在记录之间。测试应验证 reader 不会因为 prompt 或非 MI 行而卡住；必要时将无法识别行记录为诊断日志，而不是伪装成快照数据。

#### `GdbSession`

对业务层提供高层命令，不泄漏 MI 字符串：

```python
await gdb.launch(executable, cwd, source_path)
resolved = await gdb.insert_breakpoint(file, line)
stop = await gdb.run_to_first_stop()
stop = await gdb.step_over()
stop = await gdb.step_into()
stop = await gdb.continue_to_stop()
await gdb.interrupt()
await gdb.terminate()
```

每个 `StopInfo` 至少含 `reason`、`thread_id`、`frame_level`、`function`、`file`、`line`、`address`、`signal`、`exit_code`。字段可缺省，模型需允许程序退出时没有源码行。

断点响应可能带多个 locations（如模板/内联代码，或待解析断点），第一版可只接受单个已解析 location，但应把“未解析/多位置”状态明确返回给前端，而不是猜第一条。

#### `VariableReader`

输入停止帧和预算，输出带类型的递归变量树。业务层只调用 `read_frame(frame_level, limits)`，不自己拼 varobj 命令。

预算建议初始配置：

- 最大递归深度：5 层。
- 每个聚合值最多展开：100 个子项。
- 每次停止点最多变量数：500 个（达到上限返回 `truncated=true`）。
- 整帧变量采集软时限：1 秒；超时应保留已取得部分并标注 incomplete。

这些数值应配置化；实际产品可依据性能调整。指针可能形成循环引用，维护当前展开路径中的 `(type,address)` 或等价身份集合，遇到重复时输出 `cycle=true`，停止递归。

### A2. 递归变量读取的建议算法

1. 查询当前线程/选中帧的局部变量和参数名、原始值、类型信息。
2. 对每个变量创建临时 GDB varobj，保存返回的 `name`、`type`、`numchild`、`value` 等字段。
3. 若 `numchild > 0` 且未超过深度/数量预算，查询 children；child 自身可能还有 children，递归处理。
4. 若变量是数组，MI child 名称可能是 `[0]` 形式；转为节点的 `display_name`/index，不要误认为普通 C 标识符。
5. 若变量是结构体，child 名对应成员；保留 GDB 返回的字段顺序。
6. 若变量是指针，保存指针自身值；只有 GDB 报告可展开且用户启用指针展开时，再访问目标。空指针显示 `NULL`，不可访问显示 unavailable，不执行任意地址的裸读操作。
7. 尝试读取地址时，将 GDB 返回的表达式结果当字符串处理；地址可能不可用，不能将地址缺失视为读取失败。
8. 在 `finally` 路径删除临时 varobj，避免每一步调试都累积对象。若批量清理更高效，需验证不会误删用户会话所需的 varobj。
9. 在每个步骤采集后和下一条执行命令前，确保 varobj 仍对应当前停止状态；程序运行期间不能继续使用旧帧的变量对象。

第一版不需要支持所有 GDB varobj 动态行为。最初只需保证暂停状态下能够建立、读取、删除普通变量对象；变量随执行变化时，可在每次停止重新采集。`-var-update` 适合作为性能优化，不要让它成为正确性的前置条件。

### A3. 快照 JSON 契约建议

保持兼容性的策略：既有 `globals`、`stack_frames`、`heap_objects`、`pointers` 暂时不删除；新增递归节点字段。前端可先支持 `children`，平铺字段继续服务旧视图和旧测试。

```json
{
  "schema_version": 2,
  "session_id": "sess_xxx",
  "step": 4,
  "line": 12,
  "event": "none",
  "stop_reason": "end-stepping-range",
  "is_complete": true,
  "stack_frames": [{
    "function": "main",
    "file": "main.c",
    "line": 12,
    "args": "",
    "locals": [{
      "name": "points",
      "type": "struct Point[2]",
      "kind": "array",
      "value": "{...}",
      "address": "0x...",
      "children": [{
        "name": "[0]",
        "type": "struct Point",
        "kind": "struct",
        "children": [
          {"name": "x", "type": "int", "kind": "scalar", "value": "3", "children": []},
          {"name": "y", "type": "int", "kind": "scalar", "value": "7", "children": []}
        ]
      }],
      "available": true,
      "truncated": false,
      "unavailable_reason": null
    }]
  }]
}
```

字段定义：

- `kind`：`scalar`、`struct`、`union`、`array`、`pointer`、`enum`、`unknown`。
- `value`：GDB 返回的展示字符串；不是可靠的机器可计算类型值。后续如需要做差异计算，再增加类型化 `value_json`。
- `children`：递归节点，空数组表示已知没有子项；未采集则用 `available=false`，避免把两者混为一谈。
- `available`：当前停止点中能否读取。
- `unavailable_reason`：例如 `optimized_out`、`out_of_scope`、`unreadable`、`not_collected`。
- `truncated`：由于展开预算达到限制而省略了部分子项。
- `address`：可选；不具备可寻址位置时为空，不应强行制造地址。

对 `MemorySnapshot.step` 建议使用会话内单调递增的 0-based 快照索引，UI 展示用 `step + 1`。如果为了旧数据兼容暂保留 1-based，则 adapter 和 API 层必须有明确映射，不能让时间线、快照 API、AI 请求分别用不同编号。

### A4. Session Manager 状态机和清理

建议状态变化：

```text
CREATED → COMPILING → STARTING_GDB → RUNNING → PAUSED
                                       │           ├─ step/next → RUNNING → PAUSED
                                       │           ├─ continue  → RUNNING → PAUSED
                                       │           └─ stop      → STOPPING → STOPPED
                                       ├─ 正常退出 → COMPLETED
                                       ├─ 信号退出 → FAILED
                                       └─ 超时      → STOPPING → FAILED
```

规则：

- 状态只由 `DebugSessionManager` 改写；路由只调用 manager 并返回结构化结果。
- `step/continue/stop` 进入同一个会话锁/队列，保证不会同时向一个 GDB 进程发两个互斥执行命令。
- 每次从 `RUNNING` 等待停止时都要有截止时间。超时先请求 interrupt；无法中断时 terminate GDB 和目标进程。
- 关闭顺序：尝试 GDB `-gdb-exit` → 等待有限时间 → terminate → kill；同时回收目标进程组/Windows Job Object（若实现可行）。
- 使用 `try/finally` 清理 reader task、Future、临时 varobj、GDB 进程、目标进程、临时目录。
- 进程退出后保留已采集快照供时间线查看，但不再保留活进程；会话缓存需要 TTL 和最大总数。
- 应用 shutdown 时停止所有活动 debug session，避免服务退出后留下孤儿 GDB/目标程序。

Windows 上子进程树管理需要特别验证：`terminate()` 是否只终止 GDB 而留下被调试的程序。评估使用 Windows Job Object 或其他可靠的进程组管理办法；不能仅凭 Linux 上 `killpg` 的经验假设 Windows 行为相同。

### A5. API 响应示例和前端适配

建议统一成功响应的 `data` 内容，避免不同模式返回完全不同的状态结构：

```json
{
  "session_id": "sess_xxx",
  "status": "paused",
  "current_step": 0,
  "total_steps": 1,
  "stop": {"reason": "breakpoint-hit", "file": "main.c", "line": 8},
  "snapshot": {"...": "..."},
  "breakpoints": [{"requested_line": 8, "resolved_line": 8, "verified": true}]
}
```

`step`/`continue` 完成后返回同一结构，更新当前索引和累计快照数。程序已退出时 `snapshot` 可以为空，但 `status` 和 `stop.reason` 必须能解释原因。

前端需要注意：

- `isRunning` 不应只表示自动播放定时器状态。至少区分服务端 `running` 和“用户正在回看历史帧”。
- 只有 `paused` 时允许 step/continue；`completed/failed/stopped` 时禁用执行操作，可允许查看历史。
- full 模式可以继续自动执行到完成并保存每个停止点，也可以先只支持调试模式；产品语义应写清楚“自动连续运行到退出”还是“在每行都暂停采集”。
- 时间线选择历史快照只更改 `viewStep`，不改变 debugger 的真实暂停位置。用户再点 step 时，应继续从真实暂停位置执行，或在 UI 明确提示回到最新位置。
- Canvas 尺寸/滚动状态按树节点数量计算；树节点折叠/展开属于前端状态，不应改变后端快照。

### A6. 阶段 0 探针应具体怎么做

测试 C 文件可采用下列结构（文件本身应保持普通 C，不做插桩）：

```c
#include <stdio.h>

int g_total = 4;

struct Point {
    int x;
    int y;
};

int add(int a, int b) {
    int values[3] = {a, b, a + b};
    struct Point p = {
        .x = values[0],
        .y = values[2]
    };
    g_total += p.y;
    return p.x + p.y;
}

int main(void) {
    int result = add(2, 5);
    printf("%d %d\\n", result, g_total);
    return 0;
}
```

探针至少执行：

1. 编译并确认可执行文件含调试符号。
2. MI 启动后设置 `main.c` 对应行断点，检查 GDB 返回的 verified/address/file/line。
3. `-exec-run` 后等待 `*stopped`，记录原始记录和源码行。
4. 从 `main` step into `add`；读取 `a`、`b`、`values`、`p.x`、`p.y`、`g_total`。
5. step/next 几次，确认变量值随执行变化；continue 到退出，识别退出记录。
6. 删除断点、退出 GDB，确认进程结束、临时目录可删除。
7. 用含空格的临时目录重复运行；若项目要求中文路径，再单独验证中文路径。

探针结果报告要附：完整工具版本、完整编译命令、GDB 启动命令、关键 MI 输入/输出、各节点观察到的源码位置和值、失败命令及结论。报告中不能只写“正常”。

### A7. 建议代码任务拆分及 Definition of Done

每个阶段独立提交，方便 CodeArts 审核和回滚。

#### Task 0 — Toolchain smoke test

- 新增可重复运行的探针脚本和测试 C 文件。
- 不动现有 API、`SessionManager`、`Instrumenter`。
- DoD：在当前 Windows 工具链完整跑通数组/结构体/全局/局部/断点，并保存结果报告和 MI 样例。

#### Task 1 — MI parser

- 新增 MI record/parser 模块和纯单元测试。
- 不启动 GDB也能用 fixtures 覆盖嵌套语法和转义。
- DoD：测试覆盖率重点放在 parser 的分支/边界，不以项目总体覆盖率代替；非法输入有稳定错误。

#### Task 2 — MI transport + GDB process lifecycle

- 启动/读写/Token 路由/异步停止事件/退出清理。
- DoD：fake MI subprocess 测试穿插结果记录和异步记录，验证多个命令 Future 不串线；真实 smoke test 能退出无残留。

#### Task 3 — variable tree reader

- 在固定停止点读取标量、结构体和数组树。
- DoD：类型和值符合 GDB；展开预算和循环检测测试通过；不可用变量不让整帧采集失败。

#### Task 4 — Parallel backend engine

- 新增 `engine=gdb` 内部开关；现有引擎仍可运行。
- DoD：新旧模式接口兼容性测试通过，真实 GDB 模式可以 start/step/continue/stop。

#### Task 5 — Frontend state + tree view

- 接入新状态机及递归 JSON；在栈帧里树形展开数组和结构体。
- DoD：运行状态、服务端暂停位置、历史回看位置不混淆；窄屏树内容可滚动且不裁切。

#### Task 6 — Default switch and legacy retirement decision

- 汇总代表性 C 案例和压力/安全测试；由项目负责人决定默认引擎。
- DoD：新引擎在目标部署环境可复现，存在明确回滚办法；旧插桩模块只有在另行确认后才移除。

### A8. 风险表与决策点

| 风险/决策 | 可能影响 | 处理建议 |
|---|---|---|
| Windows GDB/MI 与 MinGW GCC 版本不兼容 | 启动失败、变量类型信息缺失 | 阶段 0 先检查工具链同源性；记录并锁定支持版本 |
| 某些 MI 命令在旧版 GDB 不存在 | 全局变量/类型树查询中断 | capability probe；准备版本化适配，缺能力时明确降级 |
| 优化或作用域导致变量不可见 | AI/视图缺变量值 | `-O0 -g3 -fno-inline`；UI 展示 unavailable 原因 |
| 大数组/指针链展开过多 | 延迟、内存高、UI卡顿 | 分页/按需展开、数量和深度预算、采集时限 |
| 继续/停止竞态 | 死锁、孤儿进程、错误快照 | 每会话串行队列、明确状态转换、超时和强制清理 |
| 快照结构变化 | 旧前端和持久化文件不兼容 | schema version、adapter、保留旧字段的过渡期 |
| 任意 C 程序运行风险 | 访问主机文件/网络或资源耗尽 | GDB 不是沙箱；部署前需要 OS 级隔离和资源限制 |
| “堆区”可视化数据不足 | GDB 未必知道 malloc 块大小 | 第一版先准确展示指针/变量对象；堆块追踪另立任务 |

需在项目负责人确认的产品语义：

1. “单步”默认 step-over 还是 step-into？建议默认 step-over，另加“进入函数”。
2. 完整执行模式是每个源码位置采样，还是只在断点/关键位置采样？前者可能快照很多。
3. 是否只支持本地 Windows 演示，还是需要统一 Linux 服务部署？工具链打包策略取决于此。
4. 第一版是否需要堆分配块大小和 malloc/free 事件？若需要，应设计专门追踪方案，不要把变量树误当堆分配器。
5. 用户代码输入是否开放给公网用户？若是，隔离、安全和并发控制必须在发布前完成。

## CodeArts 后续阶段任务模板

在阶段 0 通过后，可把以下提示发给 CodeArts：

> 请严格按 `GDB_MI_MIGRATION_PLAN.md` 的阶段 1 实现 MI parser 和独立 MI transport。先阅读该文档，不修改现有 `Instrumenter`、`SessionManager` API 和前端，不切换默认引擎。parser 必须有 fixture 单元测试，覆盖 token、结果记录、异步记录、嵌套 tuple/list、C 风格转义及含逗号/括号的字符串；transport 必须以 token 路由命令结果，并把 `*stopped` 放到单独事件队列。提交后汇报模块边界、测试命令及结果、尚未支持的 MI grammar/行为。若当前 GDB 原始输出与文档假设不一致，先增加 fixture 并说明，不要用业务层字符串特判。


